terraform {
  required_version = ">= 1.3"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  backend "s3" {
    bucket         = "telebucket-abhishek-2026-01"
    key            = "telegram-bot/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "telebot-tflock"
    encrypt        = true
  }
}

