"""
API Flask para extrair agenda do Cashbarber.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime as _dt
import os
import sys
import traceback
from cashbarber_agenda_extractor import (
    login_cashbarber,
    navigate_to_date,
    extract_agenda,
    AGENDA_URL
)

app = Flask(__name__)
CORS(app)

# Configurar logging
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'API is running'}), 200


@app.route('/api/debug/chrome', methods=['GET'])
def debug_chrome():
    """
    Endpoint para verificar se o Chrome e ChromeDriver estão funcionando.
    Útil para diagnóstico de problemas.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        
        debug_info = {
            'chrome_bin': os.environ.get('CHROME_BIN', 'not set'),
            'chromedriver_path': os.environ.get('CHROMEDRIVER_PATH', 'not set'),
            'python_version': sys.version,
            'selenium_version': None
        }
        
        # Tenta importar selenium e pegar versão
        try:
            import selenium
            debug_info['selenium_version'] = selenium.__version__
        except:
            pass
        
        # Tenta iniciar Chrome
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            
            chromedriver_path = os.environ.get('CHROMEDRIVER_PATH', 'chromedriver')
            service = Service(executable_path=chromedriver_path)
            
            driver = webdriver.Chrome(service=service, options=options)
            driver.get("about:blank")
            
            debug_info['chrome_status'] = 'OK'
            debug_info['chrome_version'] = driver.capabilities.get('browserVersion', 'unknown')
            debug_info['chromedriver_version'] = driver.capabilities.get('chrome', {}).get('chromedriverVersion', 'unknown')
            
            driver.quit()
            
        except Exception as e:
            debug_info['chrome_status'] = 'ERROR'
            debug_info['chrome_error'] = str(e)
        
        return jsonify({
            'success': True,
            'debug_info': debug_info
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/agenda', methods=['POST'])
def get_agenda():
    """
    Endpoint para extrair agenda.
    
    Payload JSON esperado:
    {
        "email": "seu-email@example.com",
        "password": "sua-senha",
        "date": "2025-10-15"
    }
    """
    try:
        logger.info("Recebida requisição para /api/agenda")
        
        data = request.get_json()
        
        if not data:
            logger.error("JSON payload não fornecido")
            return jsonify({'error': 'JSON payload é obrigatório'}), 400
        
        email = data.get('email')
        password = data.get('password')
        date_str = data.get('date')
        
        logger.info(f"Parâmetros recebidos - Email: {email}, Date: {date_str}")
        
        if not all([email, password, date_str]):
            logger.error("Campos obrigatórios ausentes")
            return jsonify({
                'error': 'Campos obrigatórios: email, password, date'
            }), 400
        
        # Valida formato da data
        try:
            target_date = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
            logger.info(f"Data validada: {target_date}")
        except ValueError as e:
            logger.error(f"Formato de data inválido: {e}")
            return jsonify({
                'error': 'Formato de data inválido. Use YYYY-MM-DD'
            }), 400
        
        # Executa scraping
        driver = None
        try:
            logger.info("Iniciando processo de login...")
            driver = login_cashbarber(email, password, headless=True)
            
            logger.info(f"Navegando para página de agendamento: {AGENDA_URL}")
            driver.get(AGENDA_URL)
            
            logger.info(f"Navegando para data: {target_date}")
            navigate_to_date(driver, target_date)
            
            logger.info("Extraindo agenda...")
            agenda = extract_agenda(driver)
            
            logger.info(f"Agenda extraída com sucesso. {len(agenda)} profissionais encontrados")
            
            return jsonify({
                'success': True,
                'date': date_str,
                'agenda': agenda,
                'professionals_count': len(agenda)
            }), 200
            
        except Exception as e:
            logger.error(f"Erro durante extração: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            
            # Retorna erro detalhado
            return jsonify({
                'error': str(e),
                'error_type': type(e).__name__,
                'success': False,
                'traceback': traceback.format_exc()
            }), 500
            
        finally:
            if driver:
                logger.info("Fechando driver")
                try:
                    driver.quit()
                except:
                    pass
                
    except Exception as e:
        logger.error(f"Erro não tratado: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        
        return jsonify({
            'error': str(e),
            'error_type': type(e).__name__,
            'success': False,
            'traceback': traceback.format_exc()
        }), 500


@app.route('/', methods=['GET'])
def index():
    """Página inicial com documentação."""
    return jsonify({
        'name': 'Cashbarber Agenda API',
        'version': '1.0.1',
        'endpoints': {
            '/health': 'GET - Health check',
            '/api/debug/chrome': 'GET - Verificar status do Chrome/ChromeDriver',
            '/api/agenda': 'POST - Extrair agenda (requer email, password, date)'
        },
        'example': {
            'url': '/api/agenda',
            'method': 'POST',
            'body': {
                'email': 'seu-email@example.com',
                'password': 'sua-senha',
                'date': '2025-10-15'
            }
        },
        'debug': {
            'url': '/api/debug/chrome',
            'description': 'Use este endpoint para verificar se o Chrome está funcionando corretamente'
        }
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5300))
    logger.info(f"Iniciando servidor na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
