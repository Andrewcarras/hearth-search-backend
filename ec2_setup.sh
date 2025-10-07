#!/bin/bash
#
# EC2 User Data script to setup Flask UI
#

# Update system
yum update -y

# Install Python 3.11 and dependencies
yum install -y python3.11 python3.11-pip git

# Install AWS CLI v2 if not present
if ! command -v aws &> /dev/null; then
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    ./aws/install
fi

# Create app directory
mkdir -p /opt/hearth-ui
cd /opt/hearth-ui

# Create Flask app
cat > app.py << 'EOF'
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
    data = request.json
    query = data.get('q', '').strip()
    size = int(data.get('size', 20))

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
    app.run(host='0.0.0.0', port=80, debug=False)
EOF

# Create templates directory and HTML
mkdir -p templates
cat > templates/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hearth Search - Demo</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; color: white; margin-bottom: 30px; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { font-size: 1.1em; opacity: 0.9; }
        .search-card {
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }
        .search-box input[type="text"] {
            width: 100%;
            padding: 15px 20px;
            font-size: 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            transition: border-color 0.3s;
        }
        .search-box input[type="text"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .filters {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .filter-group { display: flex; flex-direction: column; }
        .filter-group label {
            font-size: 14px;
            color: #666;
            margin-bottom: 5px;
            font-weight: 500;
        }
        .filter-group input {
            padding: 10px;
            font-size: 14px;
            border: 2px solid #e0e0e0;
            border-radius: 6px;
        }
        .search-button {
            width: 100%;
            padding: 15px;
            font-size: 16px;
            font-weight: 600;
            color: white;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 8px;
            cursor: pointer;
        }
        .listing-card {
            background: white;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .listing-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
        }
        .listing-title h3 { color: #333; font-size: 1.4em; margin-bottom: 5px; }
        .listing-location { color: #666; font-size: 0.95em; }
        .listing-score {
            background: #f0f0f0;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.9em;
            font-weight: 600;
        }
        .listing-score.boosted { background: #ffd700; }
        .listing-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 15px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            margin-bottom: 15px;
        }
        .detail-item { text-align: center; }
        .detail-label {
            font-size: 12px;
            color: #888;
            text-transform: uppercase;
        }
        .detail-value { font-size: 1.2em; font-weight: 600; color: #333; }
        .zillow-link {
            display: inline-block;
            padding: 10px 20px;
            background: #006aff;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
        }
        .loading { text-align: center; padding: 40px; color: white; font-size: 1.2em; }
        .tag {
            background: #667eea;
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            margin: 5px;
            display: inline-block;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏠 Hearth Search</h1>
            <p>AI-powered natural language property search</p>
        </div>
        <div class="search-card">
            <div class="search-box">
                <input type="text" id="searchQuery" placeholder="Try: 3 bedroom house with pool under 500k" value="3 bedroom house with pool">
            </div>
            <div class="filters">
                <div class="filter-group">
                    <label>Min Price</label>
                    <input type="number" id="priceMin" placeholder="e.g. 200000">
                </div>
                <div class="filter-group">
                    <label>Max Price</label>
                    <input type="number" id="priceMax" placeholder="e.g. 500000">
                </div>
                <div class="filter-group">
                    <label>Min Bedrooms</label>
                    <input type="number" id="bedsMin" placeholder="e.g. 3">
                </div>
                <div class="filter-group">
                    <label>Min Bathrooms</label>
                    <input type="number" id="bathsMin" placeholder="e.g. 2">
                </div>
            </div>
            <button class="search-button" onclick="performSearch()">Search Properties</button>
        </div>
        <div id="results"></div>
    </div>
    <script>
        async function performSearch() {
            const query = document.getElementById('searchQuery').value.trim();
            if (!query) { alert('Please enter a search query'); return; }

            const resultsDiv = document.getElementById('results');
            resultsDiv.innerHTML = '<div class="loading">Searching...</div>';

            const payload = { q: query, size: 20 };
            const priceMin = document.getElementById('priceMin').value;
            const priceMax = document.getElementById('priceMax').value;
            const bedsMin = document.getElementById('bedsMin').value;
            const bathsMin = document.getElementById('bathsMin').value;

            if (priceMin) payload.price_min = priceMin;
            if (priceMax) payload.price_max = priceMax;
            if (bedsMin) payload.beds_min = bedsMin;
            if (bathsMin) payload.baths_min = bathsMin;

            try {
                const response = await fetch('/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (data.error) {
                    resultsDiv.innerHTML = '<div style="color:white;padding:20px;">Error: ' + data.error + '</div>';
                    return;
                }
                displayResults(data);
            } catch (error) {
                resultsDiv.innerHTML = '<div style="color:white;padding:20px;">Error: ' + error.message + '</div>';
            }
        }

        function displayResults(data) {
            const resultsDiv = document.getElementById('results');
            if (!data.results || data.results.length === 0) {
                resultsDiv.innerHTML = '<div style="text-align:center;color:white;padding:40px;"><h3>No results found</h3></div>';
                return;
            }

            let html = '<div style="background:white;border-radius:12px;padding:20px;margin-bottom:20px;"><h2>Found ' + data.total + ' results</h2>';
            if (data.must_have && data.must_have.length > 0) {
                html += '<p style="margin:10px 0;">Must-have features:</p>';
                data.must_have.forEach(tag => html += '<span class="tag">' + tag + '</span>');
            }
            html += '</div>';

            data.results.forEach(listing => {
                const zillowUrl = 'https://www.zillow.com/homedetails/' + listing.id + '_zpid/';
                html += '<div class="listing-card"><div class="listing-header"><div class="listing-title">';
                html += '<h3>' + (listing.address || 'Address Not Available') + '</h3>';
                html += '<p class="listing-location">' + (listing.city || 'N/A') + ', ' + (listing.state || 'N/A') + ' ' + (listing.zip_code || '') + '</p>';
                html += '</div><div class="listing-score' + (listing.boosted ? ' boosted' : '') + '">Score: ' + listing.score.toFixed(2) + (listing.boosted ? ' ⭐' : '') + '</div></div>';
                html += '<div class="listing-details">';
                html += '<div class="detail-item"><div class="detail-label">Price</div><div class="detail-value">' + (listing.price ? '$' + listing.price.toLocaleString() : 'N/A') + '</div></div>';
                html += '<div class="detail-item"><div class="detail-label">Beds</div><div class="detail-value">' + (listing.beds || 'N/A') + '</div></div>';
                html += '<div class="detail-item"><div class="detail-label">Baths</div><div class="detail-value">' + (listing.baths || 'N/A') + '</div></div>';
                html += '</div>';
                html += '<a href="' + zillowUrl + '" target="_blank" class="zillow-link">View on Zillow →</a></div>';
            });

            resultsDiv.innerHTML = html;
        }

        document.getElementById('searchQuery').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') performSearch();
        });
    </script>
</body>
</html>
HTMLEOF

# Install Python dependencies
python3.11 -m pip install flask boto3

# Create systemd service
cat > /etc/systemd/system/hearth-ui.service << 'SERVICEEOF'
[Unit]
Description=Hearth UI Flask App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/hearth-ui
ExecStart=/usr/bin/python3.11 app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Start the service
systemctl daemon-reload
systemctl enable hearth-ui
systemctl start hearth-ui

# Wait a moment then check status
sleep 5
systemctl status hearth-ui --no-pager
