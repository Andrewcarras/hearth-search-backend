# UI Update Instructions

The new UI files have been uploaded to S3. To update the EC2 instance, you have two options:

## Option 1: Terminate and recreate (RECOMMENDED - Fresh deployment)

```bash
# Get current instance ID
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=hearth-demo-ui" "Name=instance-state-name,Values=running" \
    --query "Reservations[0].Instances[0].InstanceId" \
    --output text \
    --region us-east-1)

# Terminate old instance
aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region us-east-1

# Wait for termination
aws ec2 wait instance-terminated --instance-ids $INSTANCE_ID --region us-east-1

# Deploy new instance with updated UI
cd scripts
./deploy_ec2.sh
```

## Option 2: Manual SSH Update (if you have SSH access)

If you have the hearth-demo-key.pem file:

```bash
# Copy files
scp -i hearth-demo-key.pem app.py ec2-user@54.163.59.108:/tmp/
scp -i hearth-demo-key.pem templates/index.html ec2-user@54.163.59.108:/tmp/

# SSH and update
ssh -i hearth-demo-key.pem ec2-user@54.163.59.108
sudo cp /tmp/app.py /opt/hearth-ui/app.py
sudo cp /tmp/index.html /opt/hearth-ui/templates/index.html
sudo systemctl restart hearth-ui
```

## Option 3: Update ec2_setup.sh and redeploy

Update the ec2_setup.sh script to download from S3 instead of inline:

```bash
# Edit scripts/ec2_setup.sh to add these lines after creating /opt/hearth-ui:
aws s3 cp s3://demo-hearth-data/ui/app.py /opt/hearth-ui/app.py
aws s3 cp s3://demo-hearth-data/ui/index.html /opt/hearth-ui/templates/index.html

# Then run the deployment script
cd scripts
./deploy_ec2.sh
```

The UI files are ready at:
- s3://demo-hearth-data/ui/app.py
- s3://demo-hearth-data/ui/index.html
