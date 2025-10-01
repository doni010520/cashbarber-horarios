"""
API Flask para extrair agenda do Cashbarber.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime as _dt
import os
from cashbarber_agenda_extractor import (
    login_cashbarber,
    navigate_to_date,
    extract_agenda,
    AGENDA_URL
)

app = Flask(__name__)
CORS(app)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'message': 'API is running'}), 200


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
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'JSON payload é obrigatório'}), 400
        
        email = data.get('email')
        password = data.get('password')
        date_str = data.get('date')
        
        if not all([email, password, date_str]):
            return jsonify({
                'error': 'Campos obrigatórios: email, password, date'
            }), 400
        
        # Valida formato da data
        try:
            target_date = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({
                'error': 'Formato de data inválido. Use YYYY-MM-DD'
            }), 400
        
        # Executa scraping
        driver = None
        try:
            driver = login_cashbarber(email, password, headless=True)
            driver.get(AGENDA_URL)
            navigate_to_date(driver, target_date)
            agenda = extract_agenda(driver)
            
            return jsonify({
                'success': True,
                'date': date_str,
                'agenda': agenda
            }), 200
            
        finally:
            if driver:
                driver.quit()
                
    except Exception as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


@app.route('/', methods=['GET'])
def index():
    """Página inicial com documentação."""
    return jsonify({
        'name': 'Cashbarber Agenda API',
        'version': '1.0.0',
        'endpoints': {
            '/health': 'GET - Health check',
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
        }
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5300))
    app.run(host='0.0.0.0', port=port, debug=False)
