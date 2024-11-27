terraform {
  // For local development (eg running plan), comment out this line
  backend "azurerm" {}
}

provider "azurerm" {
  storage_use_azuread = true
  features {}
}
