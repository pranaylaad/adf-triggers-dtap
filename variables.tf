variable "adf_name" {
  description = "Name of data factory instance to deploy schedules"
  type        = string
}

variable "adf_resource_group_name" {
  description = "Resource group name of data factory instance to deploy schedules"
  type        = string
}

variable "env_path" {
  description = "The path where vars and configs are. Eg, env/prd etc."
  type        = string
}

variable "storage_account_resource_group_name" {
  description = "Name of resource group containing storage account used for storage triggers"
  type        = string
}

variable "storage_account_name" {
  description = "Name of storage account used for storage triggers"
  type        = string
}
