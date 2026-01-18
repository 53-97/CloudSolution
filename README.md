# Telegram Bot on AWS (Terraform)

This repository deploys a **serverless Telegram bot** on AWS using Terraform:
- **Lambda** for bot logic
- **API Gateway (HTTP API)** for the Telegram webhook
- **DynamoDB** for user notes
- **S3** for user-uploaded files

## What changed in the refactor (Class 8 gap analysis)
See `CHANGELOG.md` for a concise summary.

---

## Repo structure (modules)
```
.
├── handler.py
├── main.tf
├── variables.tf
├── outputs.tf
├── versions.tf
├── modules/
│   ├── api_gateway/
│   ├── lambda/
│   ├── dynamodb/
│   ├── s3/
│   └── state/          # remote state bootstrap module
└── bootstrap/          # one-time remote state setup
```

---

## Prerequisites
- Terraform >= 1.3
- AWS CLI configured (`aws sts get-caller-identity` should work)
- A Telegram bot token (from @BotFather)

### AWS Academy Learner Lab note
Some labs restrict IAM changes. By default this project **creates a least-privilege Lambda role**.
If IAM role creation is blocked in your environment, set:
```
use_labrole = true
```
This attaches Lambda to the pre-created `LabRole` (least-privilege cannot be guaranteed).

---

## Remote state (S3 + DynamoDB lock)
Terraform cannot use a backend bucket/table that it creates in the same run.
Use the included **bootstrap** folder once, then switch the main project to the S3 backend.

### 1) One-time bootstrap
From `./bootstrap`:
```
terraform init
terraform apply \
  -var="state_bucket_name=<globally-unique-bucket>" \
  -var="lock_table_name=<tf-lock-table>"
```

### 2) Enable the backend
In the root `versions.tf`, uncomment the `backend "s3" { ... }` block and fill in:
- bucket
- dynamodb_table
- region

Then re-init from the root:
```
terraform init -reconfigure
```

---

## Deploy
From the repo root:
```
terraform init
terraform apply -var="telegram_token=<YOUR_TOKEN>"
```

Terraform outputs:
- `webhook_url` – set this as your Telegram webhook
- `s3_bucket_name`
- `dynamodb_table_name`

### Set Telegram webhook
```
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<WEBHOOK_URL>
```

---

## Destroy
```
terraform destroy -var="telegram_token=<YOUR_TOKEN>"
```

---

## Key variables
- `aws_region` (default `us-east-1`)
- `project`, `team`, `environment` (used for naming + tags)
- `telegram_token` (sensitive)
- `use_labrole` (default `false`)

---

## Outputs
- `webhook_url`
- `api_endpoint`
- `s3_bucket_name`
- `dynamodb_table_name`
- `lambda_role_arn`
