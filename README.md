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

---

# Class 9: Observability (CloudWatch)

This section implements production-grade observability using **structured logs**, CloudWatch log groups + retention, and error alerting.

## Structured logging format
The Lambda logs are written as **JSON lines** (one event per line) with consistent fields:

- `timestamp` (UTC ISO-8601)
- `level` (`INFO`, `WARNING`, `ERROR`)
- `request_id` (AWS Lambda request id)
- `message_id` (Telegram message_id or update_id)
- `user_id` (Telegram user id)
- `command` (e.g. `/save`, `/get`, `/files`)
- `action` (e.g. `incoming_update`, `ddb_put_item`, `s3_put_object`)
- `outcome` (`success`, `received`, `error`)
- On errors: `error_type`, `error_message`, `stack_trace`

### Intentional error trigger
Use:
```
/error
```
to generate an intentional exception. This is used for alarm verification.

## Log group retention
CloudWatch log group is managed via Terraform:
- Log group name: `/aws/lambda/<lambda_function_name>`
- Retention: **14 days** (finite retention)

**Note:** Lambda may auto-create the log group on first execution. If so, import it once:
```
terraform import 'aws_cloudwatch_log_group.telegram_lambda' '/aws/lambda/<function_name>'
```

## Error metric filter + alarm
Terraform creates:
- Metric filter pattern: match structured error logs:
  - `{ $.level = "ERROR" }`
- Metric: `CloudSolutionBot/TelegramLambdaErrorCount`
- Alarm threshold:
  - **>= 1 error** within **5 minutes**
  - period: 300 seconds
  - evaluation periods: 1
  - treat_missing_data: notBreaching

## How to view logs
AWS Console:
- CloudWatch → Logs → Log groups
- Select `/aws/lambda/<function_name>`
- Open latest log stream

CLI:
```
aws logs tail "/aws/lambda/<function_name>" --follow
```

## How to view alarm state
AWS Console:
- CloudWatch → Alarms → find `<project>-<env>-telegram-lambda-errors`

---

## Evidence
Screenshots are stored under:
- `task 8 evidence/` (Class 8 proof)
- `evidence/` (Class 9 proof)

Required evidence:
- Log stream showing structured INFO entry
- Log stream showing structured ERROR entry with stack trace
- Metric filter showing datapoints
- Alarm transitioning to ALARM and back to OK
