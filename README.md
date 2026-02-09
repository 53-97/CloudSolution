# Telegram Bot on AWS (Terraform)

This repository deploys a **fully serverless Telegram bot** on AWS using **Terraform**.  
The project demonstrates **Infrastructure as Code**, **secure serverless design**, **observability**, and **runtime integration with external web APIs**.

---

## Architecture Overview

The system follows a fully managed serverless architecture:

- **Telegram** – user interface
- **API Gateway (HTTP API)** – webhook endpoint
- **AWS Lambda** – bot logic and API integration
- **DynamoDB** – persistent user notes
- **S3** – user-uploaded file storage
- **CloudWatch** – logs, metrics, alarms
- **Terraform** – infrastructure provisioning

No servers or virtual machines are provisioned or managed.

---

## Academic Context

This project is the **final assignment for the Cloud Solutions course** and satisfies all mandatory requirements:

- Fully serverless deployment on AWS
- Infrastructure provisioned and destroyed using Terraform
- Runtime integration with multiple external HTTP APIs
- Observability using CloudWatch logs, metrics, and alarms
- Secure handling of secrets and IAM permissions

---

## What Changed After Gap Analysis (Class 8)

Key improvements introduced:

- Modular Terraform structure (Lambda, API Gateway, DynamoDB, S3, CloudWatch, State)
- Remote Terraform state using S3 + DynamoDB locking
- Least-privilege IAM policy for Lambda
- Environment-based naming and tagging
- CloudWatch metric filters and alarms
- Improved UX for bot commands
- Robust error handling and structured logging

---

## Repository Structure

```
.
├── handler.py
├── main.tf
├── variables.tf
├── outputs.tf
├── versions.tf
├── cloudwatch.tf
├── modules/
│   ├── api_gateway/
│   ├── lambda/
│   ├── dynamodb/
│   ├── s3/
│   └── state/
└── bootstrap/
```

---

## Prerequisites

- Terraform ≥ 1.3
- AWS CLI configured
- Telegram bot token (via @BotFather)

---

## Secrets Handling

The Telegram bot token is **never committed**.

PowerShell:
```
$env:TF_VAR_telegram_token="YOUR_TOKEN"
```

Terraform injects it into Lambda securely.

---

## Remote Terraform State (One-Time)

```
cd bootstrap
terraform init
terraform apply
```

Creates S3 state bucket and DynamoDB lock table.

---

## Deploy Infrastructure

```
terraform init
terraform apply -var="use_labrole=true"
```

---

## Bot Commands

- /hello
- /help
- /echo <text>
- /save <text>
- /get
- Upload file → S3
- /files
- /download <file>
- /weather <city>
- /news <topic>
- /trivia
- /card

---

## External APIs

| Feature | API |
|------|----|
| Weather | Open-Meteo |
| News | Google News RSS |
| Trivia | Open Trivia DB |
| Game | Deck of Cards API |

---

## Observability

- CloudWatch structured logs
- Metric filter for ERROR logs
- Alarm when errors ≥ 1 in 5 minutes

---

## Destroy

```
terraform destroy -var="use_labrole=true"
```

---

## Evidence

- Video demo
- Terraform logs
- CloudWatch logs, metrics, alarms
- Telegram bot interaction screenshots

---

## Conclusion

This project demonstrates a **production-ready serverless Telegram bot** with secure IaC, observability, and external API integrations.
