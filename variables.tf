variable "adf_name" {
  description = "Name of data factory instance to deploy schedules"
  type        = string
}

variable "adf_resource_group_name" {
  description = "Resource group name of data factory instance to deploy schedules"
  type        = string
}

variable "env_path" {
  description = "The path where vars and configs are. Eg, prd/cdp-prd etc."
  type        = string
}
