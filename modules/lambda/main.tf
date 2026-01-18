############################################
# modules/lambda/main.tf
# - Packages handler.py into a zip
# - Creates least-privilege IAM (unless an existing role ARN is provided)
# - Creates the Lambda function
############################################

locals {
  # If an existing role ARN is provided (e.g., LabRole), we do NOT create IAM resources
  create_iam = var.use_existing_role_arn == null
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = var.source_file
  output_path = "${path.module}/lambda_function.zip"
}

# Trust policy so Lambda service can assume the role
data "aws_iam_policy_document" "assume_lambda" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Least-privilege policy for this bot:
# - CloudWatch Logs (needed for Lambda runtime)
# - DynamoDB limited to your table ARN
# - S3 limited to your bucket ARN (+ objects)
data "aws_iam_policy_document" "lambda_least_priv" {
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem"
    ]
    resources = [
      var.dynamodb_table_arn,
      "${var.dynamodb_table_arn}/*"
    ]
  }

  statement {
    sid       = "S3BucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.s3_bucket_arn]
  }

  statement {
    sid       = "S3ObjectRW"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${var.s3_bucket_arn}/*"]
  }
}

resource "aws_iam_role" "this" {
  count              = local.create_iam ? 1 : 0
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
  tags               = var.tags
}

resource "aws_iam_policy" "least_priv" {
  count  = local.create_iam ? 1 : 0
  name   = "${var.function_name}-least-priv"
  policy = data.aws_iam_policy_document.lambda_least_priv.json
  tags   = var.tags
}

resource "aws_iam_role_policy_attachment" "least_priv" {
  count      = local.create_iam ? 1 : 0
  role       = aws_iam_role.this[0].name
  policy_arn = aws_iam_policy.least_priv[0].arn
}

# Guard: if we are using LabRole/existing role, it must be provided
resource "null_resource" "validate_existing_role" {
  count = local.create_iam ? 0 : 1

  lifecycle {
    precondition {
      condition     = var.use_existing_role_arn != null && var.use_existing_role_arn != ""
      error_message = "use_existing_role_arn must be set when use_labrole=true."
    }
  }
}

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  role          = local.create_iam ? aws_iam_role.this[0].arn : var.use_existing_role_arn
  runtime       = var.runtime
  handler       = var.handler
  timeout       = var.timeout

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = var.environment_variables
  }

  tags = var.tags
}
