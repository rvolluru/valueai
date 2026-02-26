variable "project_name" {
  type    = string
  default = "valueai-mvp"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "api_key" {
  type      = string
  sensitive = true
}

variable "container_image" {
  type        = string
  description = "ECR image URI to deploy"
  default     = "public.ecr.aws/docker/library/python:3.11-slim"
}

variable "db_name" {
  type    = string
  default = "valueai"
}

variable "db_username" {
  type    = string
  default = "valueai"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "brand_accept_score" {
  type    = number
  default = 78
}

variable "brand_accept_score_low" {
  type    = number
  default = 70
}

variable "brand_gap_min" {
  type    = number
  default = 8
}
