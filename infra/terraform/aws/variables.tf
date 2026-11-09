variable "region" {
  description = "AWS region"
  type        = string
  default     = "sa-east-1"
}

variable "name" {
  description = "Name prefix for every resource"
  type        = string
  default     = "triage-agent"
}

variable "instance_type" {
  description = "Single-node k3s host. t3.small is enough for the API + pgvector."
  type        = string
  default     = "t3.small"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "ingress_cidrs" {
  description = "CIDRs allowed to reach HTTPS (monitoring servers sending webhooks)"
  type        = list(string)
}

variable "admin_cidrs" {
  description = "CIDRs allowed to reach the Kubernetes API (6443). Shell access is via SSM only."
  type        = list(string)
  default     = []
}

variable "k3s_version" {
  type    = string
  default = "v1.31.4+k3s1"
}
