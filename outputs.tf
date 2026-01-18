output "webhook_url" {
  description = "Telegram webhook URL (set this in Telegram)"
  value       = module.webhook_api.webhook_url
}

output "api_endpoint" {
  description = "API Gateway endpoint"
  value       = module.webhook_api.api_endpoint
}

output "s3_bucket_name" {
  description = "Bot S3 bucket name"
  value       = module.storage_s3.bucket_name
}

output "dynamodb_table_name" {
  description = "User notes DynamoDB table name"
  value       = module.storage_dynamodb.table_name
}

output "lambda_role_arn" {
  description = "Lambda execution role ARN"
  value       = module.telegram_lambda.role_arn
}
