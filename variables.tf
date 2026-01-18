variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project tag/name (used in resource naming + tags)"
  type        = string
  default     = "telegram-bot"
}

variable "team" {
  description = "Team tag"
  type        = string
  default     = "cloud-solution"
}

variable "environment" {
  description = "Environment tag (dev/stage/prod)"
  type        = string
  default     = "dev"
}

variable "telegram_token" {
  description = "Telegram Bot Token"
  type        = string
  sensitive   = true
}

variable "use_labrole" {
  description = "If true, attach Lambda to pre-existing LabRole instead of creating a new least-privilege role"
  type        = bool
  default     = false
}

variable "s3_bucket_name" {
  description = "Optional override for the S3 bucket name"
  type        = string
  default     = null
}

variable "dynamodb_table_name" {
  description = "Optional override for the DynamoDB table name"
  type        = string
  default     = null
}
