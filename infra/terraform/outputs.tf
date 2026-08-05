output "alb_dns_name" {
  value = aws_lb.api.dns_name
}

output "api_https_url" {
  value = var.api_domain_name == "" ? null : "https://${var.api_domain_name}"
}

output "s3_bucket_name" {
  value = aws_s3_bucket.uploads.bucket
}

output "ecr_repository_url" {
  value = local.ecr_repository_url
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}
