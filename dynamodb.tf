resource "aws_dynamodb_table" "user_data" {
  name         = "telegram_user_data"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "user_id"
  range_key = "item_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "item_id"
    type = "S"
  }
}
