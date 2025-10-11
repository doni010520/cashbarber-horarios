"""
Script completo para automatizar o login no painel Cashbarber, navegar até a
página de agendamentos, ir para uma data específica via os botões de navegação
do calendário e extrair a agenda dos profissionais (compromissos e horários
livres) para a data solicitada.

Para usar:
  python cashbarber_agenda_extractor.py <email> <senha> --date YYYY-MM-DD [--headless]

Dependências:
  pip install selenium

Observações:
  - O script utiliza seletores CSS baseados na estrutura atual do painel.
    Caso a interface mude, os seletores podem precisar de ajustes.
  - Para datas muito distantes, serão executados vários cliques nos botões de
    navegação; isso pode levar alguns segundos dependendo da responsividade
    do site.
  - As agendas são agrupadas pelo nome do profissional e apresentam tanto
    os compromissos quanto os intervalos de tempo livres entre os
    compromissos (considerando apenas o intervalo coberto pelas marcações
    existentes). Não presume um horário de expediente fixo.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
import os
import time
from typing import Dict, List, Tuple, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service

# URL base
LOGIN_URL = "https://painel.cashbarber.com.br/login"
AGENDA_URL = "https://painel.cashbarber.com.br/agendamento"

# Mapeamento de abreviações de meses em português para números
MONTHS_PT = {
    'Jan': 1,
    'Fev': 2,
    'Mar': 3,
    'Abr': 4,
    'Mai': 5,
    'Jun': 6,
    'Jul': 7,
    'Ago': 8,
    'Set': 9,
    'Out': 10,
    'Nov': 11,
    'Dez': 12,
}


# ---------------------------------------------------------------------------
# Funções auxiliares para datas e horários
# ---------------------------------------------------------------------------

def parse_header_date(text: str) -> _dt.date:
    """Converte a string de data do cabeçalho do calendário em um objeto date.

    A string é algo como "Segunda-feira, 29 Set. 2025". Extraímos o dia,
    a abreviação do mês e o ano, removendo o ponto final do mês.
    """
    # Extrai a parte depois da vírgula
    try:
        date_part = text.split(',')[1].strip()
    except IndexError:
        raise ValueError(f"Formato inesperado de data no cabeçalho: {text!r}")
    # Remove ponto final do mês e divide
    date_part = date_part.replace('.', '')
    parts = date_part.split()
    if len(parts) != 3:
        raise ValueError(f"Formato inesperado de data no cabeçalho: {text!r}")
    day_str, month_abbrev, year_str = parts
    day = int(day_str)
    month = MONTHS_PT.get(month_abbrev)
    if not month:
        raise ValueError(f"Mês desconhecido: {month_abbrev}")
    year = int(year_str)
    return _dt.date(year, month, day)


def parse_time_range(time_text: str) -> Tuple[int, int]:
    """Converte um texto de intervalo "HH:MM - HH:MM" ou "HH:MM – HH:MM" em
    uma tupla de minutos (início, fim).

    Aceita diferentes tipos de travessões (hífens) usados na página.
    """
    # Normaliza travessões longos para hífen simples
    normalized = re.sub(r'[\u2013\u2014]', '-', time_text)
    if '-' not in normalized:
        raise ValueError(f"Formato de horário inesperado: {time_text!r}")
    start_str, end_str = [s.strip() for s in normalized.split('-')]
    start_min = int(start_str.split(':')[0]) * 60 + int(start_str.split(':')[1])
    end_min = int(end_str.split(':')[0]) * 60 + int(end_str.split(':')[1])
    return start_min, end_min


def minutes_to_hhmm(minutes: int) -> str:
    """Converte minutos inteiros desde 00:00 para uma string HH:MM."""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def compute_free_slots(events: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Dado uma lista de intervalos ocupados (minutos), retorna os intervalos
    livres entre eles.

    Assume que os intervalos estão dentro do intervalo mínimo/máximo
    determinado pelos próprios eventos.
    """
    if not events:
        return []
    # Ordena pelo início
    events = sorted(events)
    free = []
    # Início do primeiro evento
    start_day = events[0][0]
    cur_end = events[0][1]
    for start, end in events[1:]:
        if start > cur_end:
            free.append((cur_end, start))
        cur_end = max(cur_end, end)
    return free


# ---------------------------------------------------------------------------
# Fluxo principal de automação
# ---------------------------------------------------------------------------

def login_cashbarber(email: str, password: str, headless: bool = False) -> webdriver.Chrome:
    """Realiza o login e retorna o driver autenticado."""
    print(f"[DEBUG] Iniciando login para: {email}")
    
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")  # Novo modo headless
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
    
    # Argumentos adicionais para evitar detecção de automação
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    
    # User agent realista
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Usar o ChromeDriver do caminho especificado ou do PATH
    chromedriver_path = os.environ.get('CHROMEDRIVER_PATH', 'chromedriver')
    
    try:
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        print("[DEBUG] Chrome iniciado com sucesso")
    except Exception as e:
        print(f"[DEBUG] Erro ao iniciar Chrome com service: {e}")
        # Fallback: tentar sem especificar o service (usa PATH)
        driver = webdriver.Chrome(options=options)
        print("[DEBUG] Chrome iniciado com fallback")
    
    # Remove propriedades que denunciam automação
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    try:
        print(f"[DEBUG] Acessando URL: {LOGIN_URL}")
        driver.get(LOGIN_URL)
        
        # Aguarda um pouco para página carregar completamente
        time.sleep(2)
        
        print(f"[DEBUG] Página carregada. URL atual: {driver.current_url}")
        print(f"[DEBUG] Título da página: {driver.title}")

        wait = WebDriverWait(driver, 30)  # Aumentado para 30 segundos
        
        print("[DEBUG] Aguardando campo de email...")
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        print("[DEBUG] Campo de email encontrado")
        
        print("[DEBUG] Aguardando campo de senha...")
        password_input = wait.until(EC.presence_of_element_located((By.NAME, "password")))
        print("[DEBUG] Campo de senha encontrado")

        # Aguarda elementos serem clicáveis
        email_input = wait.until(EC.element_to_be_clickable((By.NAME, "email")))
        password_input = wait.until(EC.element_to_be_clickable((By.NAME, "password")))

        # Simula digitação humana com pequenos delays
        email_input.clear()
        time.sleep(0.1)
        email_input.send_keys(email)
        print("[DEBUG] Email preenchido")
        
        time.sleep(0.2)
        password_input.clear()
        time.sleep(0.1)
        password_input.send_keys(password)
        print("[DEBUG] Senha preenchida")
        
        time.sleep(0.3)

        # Botão de login pode ser identificado por id ou texto
        print("[DEBUG] Procurando botão de login...")
        try:
            login_button = driver.find_element(By.ID, "kt_login_signin_submit")
            print("[DEBUG] Botão encontrado por ID")
        except NoSuchElementException:
            print("[DEBUG] Botão não encontrado por ID, tentando por XPATH...")
            try:
                login_button = driver.find_element(By.XPATH, "//button[contains(., 'Acessar')]")
                print("[DEBUG] Botão encontrado por XPATH")
            except NoSuchElementException:
                # Tenta outros seletores comuns
                login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                print("[DEBUG] Botão encontrado por CSS selector")
        
        # Aguarda botão ser clicável
        login_button = wait.until(EC.element_to_be_clickable(login_button))
        
        login_button.click()
        print("[DEBUG] Botão de login clicado")

        # Aguarda sair da URL de login
        print("[DEBUG] Aguardando redirecionamento...")
        try:
            wait.until(lambda drv: "/login" not in drv.current_url)
            print(f"[DEBUG] Login bem-sucedido! URL atual: {driver.current_url}")
            
            # Aguarda um pouco para garantir que a página carregou
            time.sleep(2)
            
            return driver
            
        except TimeoutException:
            print(f"[ERROR] Timeout ao aguardar redirecionamento. URL atual: {driver.current_url}")
            print(f"[ERROR] Título da página: {driver.title}")
            
            # Verifica se há mensagens de erro na página
            try:
                error_elements = driver.find_elements(By.CSS_SELECTOR, ".alert, .error, .alert-danger, [role='alert']")
                if error_elements:
                    print(f"[ERROR] Mensagens de erro encontradas na página:")
                    for elem in error_elements:
                        if elem.text.strip():
                            print(f"  - {elem.text.strip()}")
            except:
                pass
            
            # Captura screenshot se possível
            try:
                screenshot_path = "/tmp/login_error.png"
                driver.save_screenshot(screenshot_path)
                print(f"[DEBUG] Screenshot salvo em {screenshot_path}")
            except Exception as e:
                print(f"[DEBUG] Não foi possível salvar screenshot: {e}")
            
            # Captura página HTML para debug
            try:
                html_path = "/tmp/login_error.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print(f"[DEBUG] HTML da página salvo em {html_path}")
            except Exception as e:
                print(f"[DEBUG] Não foi possível salvar HTML: {e}")
            
            driver.quit()
            raise RuntimeError("Falha no login: verifique as credenciais ou se o site está acessível.")
    
    except Exception as e:
        print(f"[ERROR] Exceção durante login: {type(e).__name__}: {e}")
        driver.quit()
        raise


def navigate_to_date(driver: webdriver.Chrome, target_date: _dt.date) -> None:
    """Navega até a data desejada no calendário usando as setas de navegação.

    O alvo é ``target_date``; o script lê a data atual do cabeçalho
    (classe ``date-text``) e clica no botão de avanço ou retrocesso
    conforme necessário. Pode executar vários cliques se a data estiver distante.
    """
    wait = WebDriverWait(driver, 30)
    print(f"[DEBUG] Navegando para data: {target_date}")
    
    # Localiza o elemento de texto da data
    date_label = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".date-text")))
    current_date = parse_header_date(date_label.text)
    print(f"[DEBUG] Data atual no calendário: {current_date}")
    
    # Navega até a data alvo
    clicks = 0
    max_clicks = 365  # Proteção contra loop infinito
    
    while current_date != target_date and clicks < max_clicks:
        # Determina direção: 1 para futuro (próximo), -1 para passado (anterior)
        direction = 1 if target_date > current_date else -1
        
        # Localiza setas (assume que existem dois SVGs dentro do contêiner .arrow-buttons)
        arrow_buttons = driver.find_elements(By.CSS_SELECTOR, ".arrow-buttons svg")
        if len(arrow_buttons) < 2:
            raise RuntimeError("Não foi possível localizar os botões de navegação do calendário.")
        
        # Seleciona a seta: índice 1 para avançar (direita), 0 para voltar (esquerda)
        idx = 1 if direction > 0 else 0
        arrow_buttons[idx].click()
        clicks += 1
        
        # Pequeno delay para dar tempo da animação
        time.sleep(0.3)
        
        # Aguarda a data mudar
        try:
            wait.until(lambda drv: parse_header_date(drv.find_element(By.CSS_SELECTOR, ".date-text").text) != current_date)
        except TimeoutException:
            raise RuntimeError("Data não mudou após clicar no botão de navegação. Seletores podem estar incorretos.")
        
        date_label = driver.find_element(By.CSS_SELECTOR, ".date-text")
        current_date = parse_header_date(date_label.text)
        
        if clicks % 10 == 0:
            print(f"[DEBUG] Progresso: {clicks} cliques, data atual: {current_date}")
    
    if clicks >= max_clicks:
        raise RuntimeError(f"Número máximo de cliques atingido ({max_clicks}). Data alvo pode estar muito distante.")
    
    print(f"[DEBUG] Navegação concluída. Data final: {current_date}")


def extract_agenda(driver: webdriver.Chrome) -> Dict[str, Dict[str, List[str]]]:
    """Extrai agenda dos profissionais para a data atual.

    Retorna um dicionário onde as chaves são os nomes dos profissionais e os
    valores contêm duas listas: ``events`` (compromissos) e ``free``
    (intervalos livres no formato HH:MM - HH:MM).
    """
    wait = WebDriverWait(driver, 30)
    print("[DEBUG] Extraindo agenda...")
    
    # Aguarda carregar cabeçalho de recursos
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".rbc-row-resource .rbc-header span")))
    
    # Aguarda um pouco para garantir que todos os eventos carregaram
    time.sleep(2)
    
    # Obtém nomes dos profissionais
    prof_elems = driver.find_elements(By.CSS_SELECTOR, ".rbc-row-resource .rbc-header span")
    prof_names = [e.text.strip() for e in prof_elems if e.text.strip()]
    print(f"[DEBUG] Profissionais encontrados: {prof_names}")
    
    # Obtém colunas de agenda (deve corresponder ao número de profissionais)
    day_slots = driver.find_elements(By.CSS_SELECTOR, ".rbc-day-slot.rbc-time-column")
    print(f"[DEBUG] Colunas de agenda encontradas: {len(day_slots)}")
    
    agenda: Dict[str, Dict[str, List[str]]] = {}
    
    for name, slot in zip(prof_names, day_slots):
        # Cada slot contém vários eventos
        events = []  # lista de (inicio_min, fim_min, descricao)
        # Encontrar eventos, intervalos e bloqueios
        event_elements = slot.find_elements(By.CSS_SELECTOR, ".rbc-event, .break, .blocked")
        
        print(f"[DEBUG] Profissional {name}: {len(event_elements)} eventos encontrados")
        
        for ev in event_elements:
            # Extrai horário
            time_text = ''
            descr = ''
            try:
                descr = ev.find_element(By.CLASS_NAME, "title").text.strip()
            except Exception:
                # Para intervalos e bloqueios, a classe pode não existir; usamos o atributo title ou texto do elemento
                descr = (ev.get_attribute("title") or ev.text or '').strip()
            
            # Extrai horário a partir de subelementos ou atributo title
            try:
                # Classe "horario"
                time_text = ev.find_element(By.CLASS_NAME, "horario").text.strip()
            except Exception:
                try:
                    time_text = ev.find_element(By.CLASS_NAME, "rbc-event-label").text.strip()
                except Exception:
                    # Extrai do atributo title
                    attr = ev.get_attribute("title") or ''
                    # Procura padrão HH:MM – HH:MM (ou com hífen)
                    m = re.search(r"\d{1,2}:\d{2}\s*[–-]\s*\d{1,2}:\d{2}", attr)
                    if m:
                        time_text = m.group(0)
            
            if not time_text:
                continue  # Ignora se não há horário
            
            try:
                start_min, end_min = parse_time_range(time_text)
            except ValueError:
                continue
            
            events.append((start_min, end_min, descr))
        
        # Ordena eventos por início
        events_sorted = sorted(events, key=lambda x: x[0])
        busy_intervals = [(s, e) for s, e, _ in events_sorted]
        free_intervals = compute_free_slots(busy_intervals)
        
        # Formata para strings
        events_str = [f"{minutes_to_hhmm(s)} - {minutes_to_hhmm(e)}: {d}" for s, e, d in events_sorted]
        free_str = [f"{minutes_to_hhmm(s)} - {minutes_to_hhmm(e)}" for s, e in free_intervals]
        
        agenda[name] = {
            'events': events_str,
            'free': free_str,
        }
    
    print(f"[DEBUG] Extração concluída. {len(agenda)} profissionais processados")
    return agenda


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extrai agenda do Cashbarber para uma data específica.")
    parser.add_argument("email", help="E‑mail de acesso")
    parser.add_argument("password", help="Senha de acesso")
    parser.add_argument(
        "--date",
        required=True,
        help="Data no formato YYYY-MM-DD para a qual extrair a agenda",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Executa o navegador em modo headless (sem interface gráfica)",
    )
    args = parser.parse_args(argv)

    try:
        target_date = _dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        print("Formato de data inválido. Use YYYY-MM-DD.")
        return 1

    driver: Optional[webdriver.Chrome] = None
    try:
        driver = login_cashbarber(args.email, args.password, headless=args.headless)
        # Navega para a página de agendamento
        driver.get(AGENDA_URL)
        # Navega até a data desejada
        navigate_to_date(driver, target_date)
        # Extrai agenda
        agenda = extract_agenda(driver)
        # Imprime o resultado de forma legível
        print(f"\nAgenda para {target_date.strftime('%d/%m/%Y')}:")
        for prof, data in agenda.items():
            print(f"\nProfissional: {prof}")
            print(" Compromissos:")
            if data['events']:
                for ev in data['events']:
                    print(f"  - {ev}")
            else:
                print("  (Nenhum compromisso)")
            print(" Horários livres:")
            if data['free']:
                for fr in data['free']:
                    print(f"  - {fr}")
            else:
                print("  (Sem intervalos livres)")
    except Exception as exc:
        print(f"Erro: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if driver:
            driver.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
