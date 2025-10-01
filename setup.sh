#!/bin/bash

# Script para configurar o projeto e fazer o primeiro deploy

echo "🚀 Configurando Cashbarber API..."
echo ""

# Verificar se Git está instalado
if ! command -v git &> /dev/null; then
    echo "❌ Git não está instalado. Instale o Git primeiro."
    exit 1
fi

# Solicitar informações do repositório
read -p "Digite a URL do seu repositório GitHub (ex: https://github.com/usuario/repo.git): " REPO_URL

if [ -z "$REPO_URL" ]; then
    echo "❌ URL do repositório é obrigatória!"
    exit 1
fi

# Inicializar repositório Git
echo ""
echo "📦 Inicializando repositório Git..."
git init

# Adicionar todos os arquivos
echo "📝 Adicionando arquivos..."
git add .

# Fazer commit inicial
echo "💾 Fazendo commit inicial..."
git commit -m "Initial commit: Cashbarber API setup"

# Renomear branch para main
git branch -M main

# Adicionar remote
echo "🔗 Conectando ao GitHub..."
git remote add origin "$REPO_URL"

# Push para GitHub
echo "⬆️  Enviando código para GitHub..."
git push -u origin main

echo ""
echo "✅ Repositório configurado com sucesso!"
echo ""
echo "📋 Próximos passos no Easypanel:"
echo ""
echo "1. Acesse seu Easypanel"
echo "2. Crie um novo projeto chamado 'cashbarber-api'"
echo "3. Adicione um service do tipo 'App'"
echo "4. Conecte ao GitHub e selecione seu repositório"
echo "5. Configure:"
echo "   - Build Type: Dockerfile"
echo "   - Container Port: 5300"
echo "   - Publish Port: 5300"
echo "6. Clique em 'Deploy'"
echo ""
echo "🎉 Pronto! Sua API estará disponível em breve."
echo ""
