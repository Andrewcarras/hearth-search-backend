# EC2 UI Update Instructions

## Current Status

**EC2 Instance**: `i-0fe9543d2f7726bf5` (newly deployed - October 8, 2025)
**Public IP**: `54.163.59.108`
**URL**: http://54.163.59.108/

**Configuration**: ✅ Using API Gateway endpoint (production method)
**Previous Instance**: `i-046852330992c2005` (terminated)

---

**Note**: The EC2 instance has been redeployed with the latest configuration. The information below is kept for reference in case you need to update future instances.

## Why Update?

The EC2 UI is currently using the old Lambda-based backend which requires:
- AWS SDK (boto3) on the EC2 instance
- IAM permissions to invoke Lambda directly
- More dependencies and complexity

The **API Gateway endpoint** is better because:
- ✅ Always uses the latest deployed Lambda code
- ✅ Simpler (just HTTP requests, no AWS SDK needed)
- ✅ Better performance (API Gateway caching)
- ✅ More reliable (managed service)
- ✅ Same endpoint as frontend developers will use

## Manual Update Instructions

Since the EC2 instance doesn't have SSM agent configured, you'll need to SSH in and update manually.

### Option 1: Quick SSH Update (if you have the key)

```bash
# SSH into the instance (requires hearth-demo-key.pem)
ssh -i hearth-demo-key.pem ec2-user@54.234.160.86

# Switch to root
sudo su -

# Navigate to app directory
cd /opt/hearth-ui

# Backup current app
cp app.py app.py.backup

# Update app.py
cat > app.py << 'EOF'
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
EOF

# Install requests library (replacing boto3)
python3.11 -m pip install requests

# Restart the service
systemctl restart hearth-ui

# Verify it's running
systemctl status hearth-ui

# Test locally
curl -X POST http://localhost/search -H "Content-Type: application/json" -d '{"q": "3 bedroom house with pool", "size": 5}'

# Exit
exit
exit
```

### Option 2: Redeploy EC2 Instance (Clean Start)

If you don't have the SSH key, redeploy the instance with the updated scripts:

```bash
cd scripts

# The deployment script now uses API Gateway by default
./deploy_ec2.sh
```

The new instance will automatically use the API Gateway endpoint.

## Verification

After updating, test that the UI is using the API Gateway:

```bash
# From your local machine
curl -s "http://54.234.160.86/" | grep -o '<title>.*</title>'

# Test search endpoint
curl -X POST "http://54.234.160.86/search" \
  -H "Content-Type: application/json" \
  -d '{"q": "modern homes with a pool", "size": 5}' | python3 -m json.tool
```

If you see results with proper structure (results array, total count, etc.), the update was successful!

## What Changed?

### Old Code (Lambda-based)
```python
import boto3
lambda_client = boto3.client('lambda', region_name='us-east-1')

response = lambda_client.invoke(
    FunctionName='hearth-search',
    Payload=json.dumps(payload)
)
result = json.loads(response['Payload'].read())
body = json.loads(result['body'])
```

### New Code (API Gateway)
```python
import requests

API_ENDPOINT = 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search'

response = requests.post(
    API_ENDPOINT,
    json=payload,
    headers={'Content-Type': 'application/json'},
    timeout=30
)
return jsonify(response.json())
```

Much simpler! No AWS SDK needed, just standard HTTP requests.

## Future Deployments

All future EC2 deployments will automatically use the API Gateway endpoint. The deployment scripts have been updated:

- ✅ [scripts/ec2_setup.sh](../scripts/ec2_setup.sh) - Updated to use API Gateway
- ✅ [scripts/deploy_ec2.sh](../scripts/deploy_ec2.sh) - No changes needed
- ✅ [scripts/update_ec2_ui.sh](../scripts/update_ec2_ui.sh) - New script for updates

## Troubleshooting

### Service won't start after update

```bash
# Check logs
sudo journalctl -u hearth-ui -n 50 --no-pager

# Common issue: requests library not installed
sudo python3.11 -m pip install requests

# Restart
sudo systemctl restart hearth-ui
```

### Getting errors about Lambda permissions

This means the app is still using the old Lambda code. Make sure you updated app.py correctly and restarted the service.

### UI loads but search returns errors

Check that the API Gateway endpoint is correct:
```bash
curl -X POST "https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/search" \
  -H "Content-Type: application/json" \
  -d '{"q": "test", "size": 1}'
```

If this works, the issue is in the EC2 app.py file.

## Benefits After Update

Once updated, the EC2 UI will:

1. ✅ **Always use latest backend**: No need to update EC2 when Lambda changes
2. ✅ **Better proximity search**: Geocoding fixes are live
3. ✅ **Comprehensive features**: All 100 example queries work
4. ✅ **Better flooring detection**: Re-indexed data with all images processed
5. ✅ **Architecture classification**: High-quality style detection
6. ✅ **Simpler maintenance**: No AWS SDK dependencies on EC2

## Next Steps

1. Update the EC2 instance using Option 1 or Option 2 above
2. Test the search functionality with various queries
3. Monitor for any issues
4. Consider setting up auto-scaling if needed

---

**Updated**: October 8, 2025
**Status**: Documentation ready, manual update required
