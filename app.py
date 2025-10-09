from flask import Flask, render_template, request, jsonify
import requests
import json

app = Flask(__name__)

# Use API Gateway endpoint (production, always up-to-date)
API_ENDPOINT = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('q', '').strip()
    size = int(data.get('size', 30))

    filters = {}
    if data.get('price_min'):
        filters['price_min'] = int(data['price_min'])
    if data.get('price_max'):
        filters['price_max'] = int(data['price_max'])
    if data.get('beds_min'):
        filters['beds_min'] = int(data['beds_min'])
    if data.get('baths_min'):
        filters['baths_min'] = int(data['baths_min'])

    payload = {'q': query, 'size': size}
    if filters:
        payload['filters'] = filters

    try:
        # Use API Gateway endpoint for latest backend features
        response = requests.post(
            API_ENDPOINT,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
