#!/bin/bash
#
# Deploy Flask UI to EC2 instance
#

set -e

REGION="us-east-1"
INSTANCE_TYPE="t3.micro"  # x86_64, free tier eligible
AMI_ID="ami-0453ec754f44f9a4a"  # Amazon Linux 2023 x86_64
KEY_NAME="hearth-demo-key"
SECURITY_GROUP_NAME="hearth-ui-sg"

echo "=== Deploying Hearth UI to EC2 ==="
echo ""

# 1. Create security group if it doesn't exist
echo "Step 1: Creating security group..."
SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SECURITY_GROUP_NAME" \
    --query "SecurityGroups[0].GroupId" \
    --output text \
    --region $REGION 2>/dev/null)

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    SG_ID=$(aws ec2 create-security-group \
        --group-name $SECURITY_GROUP_NAME \
        --description "Security group for Hearth UI demo" \
        --region $REGION \
        --query 'GroupId' \
        --output text)

    # Allow HTTP (port 80)
    aws ec2 authorize-security-group-ingress \
        --group-id $SG_ID \
        --protocol tcp \
        --port 80 \
        --cidr 0.0.0.0/0 \
        --region $REGION

    # Allow SSH (port 22) for setup
    aws ec2 authorize-security-group-ingress \
        --group-id $SG_ID \
        --protocol tcp \
        --port 22 \
        --cidr 0.0.0.0/0 \
        --region $REGION

    echo "✓ Created security group: $SG_ID"
else
    echo "✓ Using existing security group: $SG_ID"
fi

# 2. Create key pair if it doesn't exist
echo ""
echo "Step 2: Checking SSH key..."
if ! aws ec2 describe-key-pairs --key-names $KEY_NAME --region $REGION &>/dev/null; then
    aws ec2 create-key-pair \
        --key-name $KEY_NAME \
        --region $REGION \
        --query 'KeyMaterial' \
        --output text > ${KEY_NAME}.pem
    chmod 400 ${KEY_NAME}.pem
    echo "✓ Created SSH key: ${KEY_NAME}.pem"
else
    echo "✓ Using existing key: $KEY_NAME"
fi

# 3. Launch EC2 instance
echo ""
echo "Step 3: Launching EC2 instance..."
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --instance-type $INSTANCE_TYPE \
    --key-name $KEY_NAME \
    --security-group-ids $SG_ID \
    --region $REGION \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=hearth-demo-ui}]" \
    --user-data file://ec2_setup.sh \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "✓ Instance launched: $INSTANCE_ID"

# 4. Wait for instance to be running
echo ""
echo "Step 4: Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION
echo "✓ Instance is running"

# 5. Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --region $REGION \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "=========================================="
echo "✓ Deployment Complete!"
echo "=========================================="
echo ""
echo "Instance ID: $INSTANCE_ID"
echo "Public IP:   $PUBLIC_IP"
echo ""
echo "The UI will be available at:"
echo "  http://$PUBLIC_IP"
echo ""
echo "Note: It may take 2-3 minutes for the app to fully start."
echo "      The setup script is installing dependencies and starting Flask."
echo ""
echo "To check status:"
echo "  ssh -i ${KEY_NAME}.pem ec2-user@$PUBLIC_IP"
echo "  sudo systemctl status hearth-ui"
echo ""
echo "To stop the instance (to save costs):"
echo "  aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $REGION"
echo ""
echo "To terminate the instance:"
echo "  aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION"
echo ""
