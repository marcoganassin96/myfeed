output "state_bucket" {
  value = aws_s3_bucket.tfstate.bucket
}

output "lock_table" {
  value = aws_dynamodb_table.tfstate_lock.name
}

output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}
