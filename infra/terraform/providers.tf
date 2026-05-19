terraform {
  required_version = ">= 1.5.0"
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 5.31.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  dynamic "assume_role" {
    for_each = var.aws_assume_role_arn != null ? [1] : []
    content {
      role_arn = var.aws_assume_role_arn
    }
  }
}
