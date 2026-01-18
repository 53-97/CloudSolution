variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Name of the S3 bucket to store Terraform state"
}

variable "lock_table_name" {
  type        = string
  description = "Name of the DynamoDB table used for Terraform state locking"
}

variable "project" {
  type        = string
  description = "Project tag value"
  default     = "CloudSolutionProject"
}

variable "team" {
  type        = string
  description = "Team tag value"
  default     = "CloudSolution"
}

variable "environment" {
  type        = string
  description = "Environment tag value (e.g., dev, prod)"
  default     = "dev"
}

variable "tags" {
  type    = map(string)
  default = {}
}
