#!/bin/bash
# Deploy Hearth UI with Admin Panel to EC2

set -e

INSTANCE_ID="i-03ff1ef6cfad509e0"
REGION="us-east-1"
S3_UI_URL="https://demo-hearth-data.s3.amazonaws.com/ui/index.html"

echo "🚀 Deploying Hearth UI with Admin Panel..."

# Create temporary deployment script
cat > /tmp/deploy_ui_remote.sh << 'EOF'
#!/bin/bash
set -e

echo "📥 Downloading new UI from S3..."
cd /var/www/html
curl -s https://demo-hearth-data.s3.amazonaws.com/ui/index.html -o index.html.new

echo "✅ Backing up old UI..."
if [ -f index.html ]; then
    cp index.html index.html.backup
fi

echo "🔄 Installing new UI..."
mv index.html.new index.html

echo "🔃 Reloading nginx..."
systemctl reload nginx || systemctl restart nginx

echo "✅ UI deployment complete!"
echo "🌐 Access at: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
EOF

chmod +x /tmp/deploy_ui_remote.sh

echo ""
echo "⚠️  Manual Deployment Required"
echo "================================"
echo ""
echo "This instance doesn't have SSH access configured."
echo ""
echo "Option 1: Access via EC2 Console"
echo "  1. Go to EC2 Console: https://console.aws.amazon.com/ec2/"
echo "  2. Select instance: $INSTANCE_ID"
echo "  3. Click 'Connect' → 'Session Manager'"
echo "  4. Run these commands:"
echo ""
echo "  sudo su -"
echo "  cd /var/www/html"
echo "  curl -s $S3_UI_URL -o index.html"
echo "  systemctl reload nginx"
echo ""
echo "Option 2: Recreate Instance with SSH Key"
echo "  Run: bash scripts/create_ui_instance.sh"
echo ""
echo "Option 3: The UI is already in S3 - it will auto-update on next instance restart"
echo ""
echo "✅ UI uploaded to S3: $S3_UI_URL"
echo "🌐 Current UI: http://34.228.111.56"
