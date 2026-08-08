variable "project_name" {
  type    = string
  default = "valueai-mvp"
}

variable "app_env" {
  type    = string
  default = "prod"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type        = string
  default     = null
  description = "Optional AWS CLI profile name for deploying to a specific account."
}

variable "aws_assume_role_arn" {
  type        = string
  default     = null
  description = "Optional IAM role ARN to assume in the target account."
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

variable "api_domain_name" {
  type        = string
  description = "Public HTTPS hostname for the API."
  default     = "api.jouft.com"
}

variable "api_certificate_arn" {
  type        = string
  description = "ACM certificate ARN for api_domain_name. Must be in the same region as the ALB."
  default     = ""
}

variable "route53_zone_id" {
  type        = string
  description = "Optional Route 53 hosted zone ID for creating the API alias record."
  default     = ""
}

variable "create_api_dns_record" {
  type        = bool
  description = "Whether Terraform should create the Route 53 alias record for api_domain_name."
  default     = false
}

variable "create_ecr_repository" {
  type    = bool
  default = true
}

variable "existing_ecr_repository_url" {
  type    = string
  default = ""
}

variable "create_cloudwatch_log_group" {
  type    = bool
  default = true
}

variable "existing_cloudwatch_log_group_name" {
  type    = string
  default = ""
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

variable "openai_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "gemini_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "photoroom_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "image_staging_photoroom_enabled" {
  type    = bool
  default = true
}

variable "photoroom_background_color" {
  type    = string
  default = "#FFFFFF"
}

variable "photoroom_output_format" {
  type    = string
  default = "jpg"
}

variable "photoroom_output_size" {
  type    = string
  default = "full"
}

variable "clerk_enabled" {
  type    = bool
  default = false
}

variable "clerk_issuer" {
  type    = string
  default = ""
}

variable "clerk_jwks_url" {
  type    = string
  default = ""
}

variable "clerk_audience" {
  type    = string
  default = ""
}

variable "clerk_authorized_parties" {
  type    = string
  default = ""
}

variable "cors_allow_origins" {
  type        = string
  description = "Comma-separated browser origins allowed to call the API."
  default     = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175"
}

variable "brand_enable_gpt_vision" {
  type    = bool
  default = true
}

variable "gpt_item_profile_enabled" {
  type    = bool
  default = true
}

variable "gpt_item_profile_provider_order" {
  type    = string
  default = "hybrid,gemini,openai"
}

variable "gpt_item_profile_model" {
  type    = string
  default = "gpt-5"
}

variable "gpt_item_profile_gemini_model" {
  type    = string
  default = "gemini-2.5-flash"
}

variable "gpt_item_profile_timeout_s" {
  type    = number
  default = 25
}

variable "gpt_item_profile_max_images" {
  type    = number
  default = 6
}

variable "gpt_item_profile_image_detail" {
  type    = string
  default = "auto"
}

variable "gpt_item_profile_reasoning_effort" {
  type    = string
  default = "low"
}

variable "gpt_item_profile_vertex_search_enabled" {
  type    = bool
  default = false
}

variable "gpt_item_profile_vertex_search_project_id" {
  type    = string
  default = ""
}

variable "gpt_item_profile_vertex_search_location" {
  type    = string
  default = "global"
}

variable "gpt_item_profile_vertex_search_model" {
  type    = string
  default = ""
}

variable "gpt_item_profile_vertex_search_datastore" {
  type    = string
  default = ""
}

variable "gpt_item_profile_vertex_search_access_token" {
  type      = string
  default   = ""
  sensitive = true
}

variable "gpt_item_profile_vertex_search_max_results" {
  type    = number
  default = 10
}

variable "firecrawl_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "ebay_app_id" {
  type      = string
  default   = ""
  sensitive = true
}

variable "valuation_providers" {
  type    = string
  default = "stub"
}

variable "valuation_use_firecrawl" {
  type    = bool
  default = true
}

variable "valuation_enabled" {
  type    = bool
  default = true
}

variable "valuation_min_comps" {
  type    = number
  default = 3
}

variable "valuation_max_comps" {
  type    = number
  default = 25
}

variable "valuation_currency" {
  type    = string
  default = "USD"
}

variable "valuation_provider_timeout_s" {
  type    = number
  default = 12
}

variable "valuation_provider_user_agent" {
  type    = string
  default = ""
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

variable "stripe_secret_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "stripe_publishable_key" {
  type      = string
  default   = ""
  sensitive = true
}
