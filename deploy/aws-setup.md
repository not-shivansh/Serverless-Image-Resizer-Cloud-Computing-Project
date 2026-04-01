# AWS Deployment Guide — Serverless Image Resizer

This guide walks you through setting up all AWS resources for the production deployment.

> **Region**: `ap-south-1` (Mumbai, India)  
> **Prerequisites**: AWS CLI configured with admin credentials

---

## 1. Create S3 Buckets

### Input Bucket (receives original uploads)

```bash
aws s3api create-bucket \
  --bucket serverless-image-resizer-buckets-input \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1

# Enable CORS for direct browser uploads
aws s3api put-bucket-cors \
  --bucket serverless-image-resizer-buckets-input \
  --cors-configuration '{
    "CORSRules": [{
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["PUT", "POST", "GET"],
      "AllowedOrigins": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3600
    }]
  }'
```

### Output Bucket (stores processed images)

```bash
aws s3api create-bucket \
  --bucket serverless-image-resizer-buckets-output \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1

# Make output bucket publicly readable (for CloudFront origin)
aws s3api put-bucket-policy \
  --bucket serverless-image-resizer-buckets-output \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [{
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::serverless-image-resizer-buckets-output/*"
    }]
  }'
```

---

## 2. Create IAM Role for Lambda

```bash
# Create the execution role
aws iam create-role \
  --role-name serverless-image-resizer-lambda-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach the custom policy
aws iam put-role-policy \
  --role-name serverless-image-resizer-lambda-role \
  --policy-name image-resizer-permissions \
  --policy-document file://deploy/iam-policy.json

# Attach basic Lambda execution role
aws iam attach-role-policy \
  --role-name serverless-image-resizer-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

---

## 3. Package and Deploy Lambda Function

```bash
# Navigate to backend directory
cd backend

# Create a deployment package directory
mkdir -p lambda_package

# Install Pillow for Linux (Lambda runtime)
pip install pillow -t lambda_package/ --platform manylinux2014_x86_64 --only-binary=:all:

# Copy the handler
cp app/lambda_handler.py lambda_package/

# Create the ZIP
cd lambda_package
zip -r ../lambda_function.zip .
cd ..

# Deploy to AWS Lambda
aws lambda create-function \
  --function-name serverless-image-resizer \
  --runtime python3.12 \
  --handler lambda_handler.handler \
  --role arn:aws:iam::<YOUR_ACCOUNT_ID>:role/serverless-image-resizer-lambda-role \
  --zip-file fileb://lambda_function.zip \
  --timeout 30 \
  --memory-size 512 \
  --region ap-south-1 \
  --environment Variables="{
    IMAGE_RESIZER_S3_OUTPUT_BUCKET=serverless-image-resizer-buckets-output,
    IMAGE_RESIZER_CLOUDFRONT_DOMAIN=<YOUR_CLOUDFRONT_DOMAIN>
  }"
```

> **Note**: Replace `<YOUR_ACCOUNT_ID>` and `<YOUR_CLOUDFRONT_DOMAIN>` with your actual values.

---

## 4. Configure S3 → Lambda Trigger

```bash
# Allow S3 to invoke the Lambda function
aws lambda add-permission \
  --function-name serverless-image-resizer \
  --statement-id s3-trigger \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::serverless-image-resizer-buckets-input \
  --region ap-south-1

# Add the S3 event notification
aws s3api put-bucket-notification-configuration \
  --bucket serverless-image-resizer-buckets-input \
  --notification-configuration '{
    "LambdaFunctionConfigurations": [{
      "LambdaFunctionArn": "arn:aws:lambda:ap-south-1:<YOUR_ACCOUNT_ID>:function:serverless-image-resizer",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [{
            "Name": "prefix",
            "Value": "uploads/"
          }]
        }
      }
    }]
  }'
```

---

## 5. Create API Gateway

```bash
# Create the REST API
aws apigateway create-rest-api \
  --name "Serverless Image Resizer API" \
  --description "Production API for the Serverless Image Resizer" \
  --region ap-south-1 \
  --endpoint-configuration types=REGIONAL

# Note the returned API ID and configure resources/methods
# For a full setup, import the OpenAPI spec or use AWS Console
```

> **Recommended**: For complex API Gateway setup, use the AWS Console or AWS SAM/CloudFormation templates. The backend FastAPI app can be deployed behind API Gateway using a Lambda proxy integration with `mangum`.

---

## 6. Create CloudFront Distribution

```bash
aws cloudfront create-distribution \
  --distribution-config '{
    "CallerReference": "serverless-image-resizer-'$(date +%s)'",
    "Origins": {
      "Quantity": 1,
      "Items": [{
        "Id": "S3-output-bucket",
        "DomainName": "serverless-image-resizer-buckets-output.s3.ap-south-1.amazonaws.com",
        "S3OriginConfig": {
          "OriginAccessIdentity": ""
        }
      }]
    },
    "DefaultCacheBehavior": {
      "TargetOriginId": "S3-output-bucket",
      "ViewerProtocolPolicy": "redirect-to-https",
      "AllowedMethods": {
        "Quantity": 2,
        "Items": ["GET", "HEAD"]
      },
      "ForwardedValues": {
        "QueryString": false,
        "Cookies": {"Forward": "none"}
      },
      "MinTTL": 86400,
      "DefaultTTL": 604800,
      "MaxTTL": 31536000,
      "Compress": true
    },
    "Comment": "CDN for Serverless Image Resizer processed images",
    "Enabled": true
  }'
```

> After creation, note the CloudFront domain (e.g., `d1234abcdef.cloudfront.net`) and update your `.env` file.

---

## 7. Set Up CloudWatch Monitoring

```bash
# Create a CloudWatch alarm for Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name "ImageResizer-LambdaErrors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions Name=FunctionName,Value=serverless-image-resizer \
  --alarm-actions arn:aws:sns:ap-south-1:<YOUR_ACCOUNT_ID>:<YOUR_SNS_TOPIC> \
  --region ap-south-1

# Create alarm for high duration
aws cloudwatch put-metric-alarm \
  --alarm-name "ImageResizer-HighLatency" \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Average \
  --period 300 \
  --threshold 5000 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions Name=FunctionName,Value=serverless-image-resizer \
  --region ap-south-1
```

---

## 8. Verify Deployment

1. Upload a test image to S3:
   ```bash
   aws s3 cp test-image.jpg s3://serverless-image-resizer-buckets-input/uploads/test123/original.jpg
   ```

2. Check Lambda logs:
   ```bash
   aws logs tail /aws/lambda/serverless-image-resizer --follow --region ap-south-1
   ```

3. Verify output:
   ```bash
   aws s3 ls s3://serverless-image-resizer-buckets-output/processed/test123/
   ```

4. Access via CloudFront:
   ```
   https://<YOUR_CLOUDFRONT_DOMAIN>/processed/test123/thumbnail.jpg
   ```
