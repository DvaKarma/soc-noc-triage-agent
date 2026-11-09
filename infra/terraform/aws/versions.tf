terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state (recommended). Create the bucket and table once, then uncomment.
  # backend "s3" {
  #   bucket         = "my-tfstate-bucket"
  #   key            = "soc-noc-triage-agent/terraform.tfstate"
  #   region         = "sa-east-1"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "soc-noc-triage-agent"
      ManagedBy = "terraform"
    }
  }
}
