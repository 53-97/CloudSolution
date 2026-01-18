resource "aws_s3_bucket" "bot_bucket" {
  bucket        = "telegram-bot-storage-${random_id.suffix.hex}"
  force_destroy = true
}
