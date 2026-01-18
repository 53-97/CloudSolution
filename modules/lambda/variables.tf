#variable "create_iam" {
#  type        = bool
#  description = "Whether to create IAM role/policy for Lambda"
#  default     = true
#}

variable "function_name" {
  type = string
}

variable "runtime" {
  type = string
}

variable "handler" {
  type = string
}

variable "timeout" {
  type    = number
  default = 30
}

variable "source_file" {
  type = string
}

variable "environment_variables" {
  type    = map(string)
  default = {}
}

variable "dynamodb_table_arn" {
  type = string
}

variable "s3_bucket_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

# NEW: When set, we use this role and do NOT create IAM resources
variable "use_existing_role_arn" {
  type        = string
  default     = null
  description = "Existing IAM role ARN (e.g., LabRole). If set, module will not create IAM role/policy."
}

