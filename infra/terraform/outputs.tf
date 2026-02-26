output "alb_dns_name" {
  value = aws_lb.api.dns_name
}

output "s3_bucket_name" {
  value = aws_s3_bucket.uploads.bucket
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}
