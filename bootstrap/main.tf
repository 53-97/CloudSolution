provider "aws" {
  region = var.aws_region
}

locals {
  tags = {
    Project     = var.project
    Team        = var.team
    Environment = var.environment
  }
}

module "state" {
  source            = "../modules/state"
  state_bucket_name = var.state_bucket_name
  lock_table_name   = var.lock_table_name
  tags              = local.tags
}

output "state_bucket_name" { value = module.state.state_bucket_name }
output "lock_table_name" { value = module.state.lock_table_name }
