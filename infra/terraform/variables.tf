variable "project_name" {
  type    = string
  default = "valueai-mvp"
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
  default = "gemini,openai"
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
  default = 2
}

variable "gpt_item_profile_image_detail" {
  type    = string
  default = "auto"
}

variable "gpt_item_profile_reasoning_effort" {
  type    = string
  default = "low"
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
