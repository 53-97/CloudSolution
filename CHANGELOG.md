# Changelog (Refactor Summary)

## 2026-01-18
- Split Terraform into reusable **modules** (`lambda`, `api_gateway`, `dynamodb`, `s3`) to improve readability and reuse.
- Introduced `project/team/environment` variables + `locals` to standardize naming and **consistent tags** across all resources.
- Added **least-privilege IAM** for the Lambda execution role:
  - DynamoDB access restricted to the single notes table
  - S3 access restricted to the single bucket (bucket list + object read/write)
  - CloudWatch Logs permissions included for Lambda runtime
- Added a `use_labrole` escape hatch for AWS Academy environments that block custom IAM role creation.
- Added meaningful **outputs** (webhook URL, API endpoint, bucket name, table name, Lambda role ARN).
- Added a one-time **remote state bootstrap** (`bootstrap/` + `modules/state`) for S3 backend + DynamoDB state locking.
- Updated `handler.py` to rely on the runtime region configuration (removed hard-coded `us-east-1`).
- Updated README with deploy/destroy, module structure, variables, and remote state prerequisites.
