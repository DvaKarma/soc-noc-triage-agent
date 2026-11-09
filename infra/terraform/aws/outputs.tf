output "instance_id" {
  value = aws_instance.node.id
}

output "public_ip" {
  value = aws_instance.node.public_ip
}

output "ssm_session" {
  description = "Open a shell without SSH"
  value       = "aws ssm start-session --target ${aws_instance.node.id} --region ${var.region}"
}
