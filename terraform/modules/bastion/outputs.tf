output "instance_id" {
  value       = aws_instance.bastion.id
  description = "Use with: aws ssm start-session --target <instance_id> --document-name AWS-StartPortForwardingSessionToRemoteHost"
}
