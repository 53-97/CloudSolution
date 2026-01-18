provider "aws" {
  region = var.aws_region
}

data "aws_iam_role" "lab_role" {
  count = var.use_labrole ? 1 : 0
  name  = "LabRole"
}

resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  name_prefix = "${var.project}-${var.environment}"

  default_tags = {
    Project     = var.project
    Team        = var.team
    Environment = var.environment
  }

  bucket_name = coalesce(var.s3_bucket_name, "${local.name_prefix}-bot-${random_id.suffix.hex}")
  table_name  = coalesce(var.dynamodb_table_name, "${local.name_prefix}-user-notes")
}

module "storage_s3" {
  source        = "./modules/s3"
  bucket_name   = local.bucket_name
  force_destroy = true
  tags          = local.default_tags
}

module "storage_dynamodb" {
  source       = "./modules/dynamodb"
  table_name   = local.table_name
  hash_key     = "user_id"
  range_key    = "item_id"
  billing_mode = "PAY_PER_REQUEST"
  tags         = local.default_tags
}

module "telegram_lambda" {
  source = "./modules/lambda"

  function_name = "${local.name_prefix}-telegram-bot"
  runtime       = "python3.10"
  handler       = "handler.lambda_handler"
  timeout       = 30

  source_file = "${path.module}/handler.py"

  # If use_labrole=true, skip role creation and use LabRole
  use_existing_role_arn = var.use_labrole ? data.aws_iam_role.lab_role[0].arn : null

  environment_variables = {
    TELEGRAM_BOT_TOKEN   = var.telegram_token
    USER_DATA_TABLE_NAME = module.storage_dynamodb.table_name
    S3_BUCKET            = module.storage_s3.bucket_name
  }

  dynamodb_table_arn = module.storage_dynamodb.table_arn
  s3_bucket_arn      = module.storage_s3.bucket_arn
  tags               = local.default_tags
}

module "webhook_api" {
  source = "./modules/api_gateway"

  api_name             = "${local.name_prefix}-telegram-webhook-api"
  route_key            = "POST /webhook"
  lambda_function_name = module.telegram_lambda.function_name
  lambda_invoke_arn    = module.telegram_lambda.invoke_arn
  tags                 = local.default_tags
}



