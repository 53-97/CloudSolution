############################################
# cloudwatch.tf (Class 9 - Observability)
#
# What this file creates:
# 1) CloudWatch Log Group for the Lambda with finite retention (e.g., 14 days)
# 2) Metric filter that counts ERROR logs (structured JSON logs)
# 3) CloudWatch alarm when >= 1 error occurs within 5 minutes
#
# IMPORTANT (first-time setup):
# Lambda often auto-creates the log group on first invocation.
# If the log group already exists, Terraform will fail with
# ResourceAlreadyExistsException unless you IMPORT it first:
#
#   terraform import 'aws_cloudwatch_log_group.telegram_lambda' '/aws/lambda/<FUNCTION_NAME>'
#
# Example (your function name from terraform output):
#   terraform import 'aws_cloudwatch_log_group.telegram_lambda' '/aws/lambda/telegram-bot-dev-telegram-bot'
############################################

# --- Log group + retention (managed in Terraform) ---
resource "aws_cloudwatch_log_group" "telegram_lambda" {
  name              = "/aws/lambda/${module.telegram_lambda.function_name}"
  retention_in_days = 14
  tags              = local.default_tags

  # Avoid accidentally deleting logs during terraform destroy
  skip_destroy = true
}

# --- Metric filter: count structured ERROR logs ---
# This matches JSON logs like:
# {"timestamp":"...","level":"ERROR", ...}
resource "aws_cloudwatch_log_metric_filter" "telegram_lambda_errors" {
  name           = "${local.name_prefix}-telegram-errors"
  log_group_name = aws_cloudwatch_log_group.telegram_lambda.name

  # JSON filter pattern (CloudWatch Logs supports this format)
  pattern = "{ $.level = \"ERROR\" }"

  metric_transformation {
    name      = "TelegramLambdaErrorCount"
    namespace = "CloudSolutionBot"
    value     = "1"
    unit      = "Count"
  }
}

# --- Alarm: >= 1 error in 5 minutes ---
resource "aws_cloudwatch_metric_alarm" "telegram_lambda_error_alarm" {
  alarm_name        = "${local.name_prefix}-telegram-lambda-errors"
  alarm_description = "Triggers when Lambda logs ERROR level entries (>=1 in 5 minutes)."

  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1

  namespace   = aws_cloudwatch_log_metric_filter.telegram_lambda_errors.metric_transformation[0].namespace
  metric_name = aws_cloudwatch_log_metric_filter.telegram_lambda_errors.metric_transformation[0].name
  statistic   = "Sum"
  period      = 300

  treat_missing_data = "notBreaching"
  tags               = local.default_tags
}

# (Optional) useful outputs
output "cloudwatch_log_group_name" {
  value = aws_cloudwatch_log_group.telegram_lambda.name
}

output "cloudwatch_error_alarm_name" {
  value = aws_cloudwatch_metric_alarm.telegram_lambda_error_alarm.alarm_name
}
