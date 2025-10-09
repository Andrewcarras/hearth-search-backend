#!/bin/bash
set -e

INSTANCE_IP="54.163.59.108"

echo "Creating temporary update package..."

# Create a simple update script that EC2 will download
cat > /tmp/ui_update.sh << 'UPDATEEOF'
#!/bin/bash
cd /opt/hearth-ui

# Backup current files
sudo cp app.py app.py.backup 2>/dev/null || true
sudo cp templates/index.html templates/index.html.backup 2>/dev/null || true

# Download new files from S3
aws s3 cp s3://demo-hearth-data/ui/app.py app.py
aws s3 cp s3://demo-hearth-data/ui/index.html templates/index.html

# Restart service
sudo systemctl restart hearth-ui
echo "UI updated successfully"
UPDATEEOF

echo "Uploading files to S3..."
aws s3 cp app.py s3://demo-hearth-data/ui/app.py
aws s3 cp templates/index.html s3://demo-hearth-data/ui/index.html
aws s3 cp /tmp/ui_update.sh s3://demo-hearth-data/ui/ui_update.sh

echo ""
echo "Files uploaded to S3. Now execute the update on EC2:"
echo ""
echo "Run this command on the EC2 instance:"
echo "  curl -s https://demo-hearth-data.s3.amazonaws.com/ui/ui_update.sh | sudo bash"
echo ""
echo "Or use AWS Systems Manager Session Manager to connect and run the update."
