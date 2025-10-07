#!/usr/bin/env python3
"""
Flask app for testing the Hearth search backend.

Usage:
    python3 app.py

Then open http://localhost:5000 in your browser.
"""

from flask import Flask, render_template, request, jsonify
import boto3
import json

app = Flask(__name__)
lambda_client = boto3.client('lambda', region_name='us-east-1')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    """Execute search and return results."""
    data = request.json
    query = data.get('q', '').strip()
    size = int(data.get('size', 20))

    # Build filters
    filters = {}
    if data.get('price_min'):
        filters['price_min'] = int(data['price_min'])
    if data.get('price_max'):
        filters['price_max'] = int(data['price_max'])
    if data.get('beds_min'):
        filters['beds_min'] = int(data['beds_min'])
    if data.get('baths_min'):
        filters['baths_min'] = int(data['baths_min'])

    # Invoke Lambda
    payload = {
        'q': query,
        'size': size
    }
    if filters:
        payload['filters'] = filters

    try:
        response = lambda_client.invoke(
            FunctionName='hearth-search',
            Payload=json.dumps(payload)
        )

        result = json.loads(response['Payload'].read())
        body = json.loads(result['body'])

        return jsonify(body)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
