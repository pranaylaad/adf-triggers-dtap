locals {
  # This notation is copied in from an ADF UI generated trigger
  time_zone = "W. Europe Standard Time"

  datastore_path    = "${var.env_path}/datastores"
  datastore_pattern = "^(?P<datastore>[0-9A-Za-z_]+)/trigger_info\\.yaml"

  environment = replace(var.env_path, "env/", "")

  datastore_configs = {
    for filename in fileset(local.datastore_path, "**/trigger_info.yaml") :
    filename => yamldecode(file("${local.datastore_path}/${filename}"))
  }

  triggers = merge(flatten([
    for filename, datastore in local.datastore_configs : [
      for dataset in datastore.datasets : {
        # spaargids_be/trigger_info.yaml -> spaargids_be__rentes_nibc_all
        "${replace(replace(filename, "/trigger_info.yaml", ""), "/", "_")}__${dataset.name}" = {

          "pipeline_name" = try(dataset.pipeline_name, datastore.pipeline_name)
          "schedule"      = try(dataset.schedule, datastore.schedule)

          "datastore_name" = regex(local.datastore_pattern, filename).datastore
          "environment"    = local.environment
          "dataset_name"   = dataset.name

          "datastore_parameters" = try(datastore.datastore_parameters, {})
          "dataset_parameters"   = try(dataset.dataset_parameters, {})

          # If there is a column_mapping JSON, provide it as a parameter
          "mapping" = try(
            { "column_mapping" = file(
              # Mappings live in the same directory as the trigger_info.yaml, in the mappings subdirectory
              "${local.datastore_path}/${replace(filename, "trigger_info.yaml", "mappings/${dataset.name}.json")}"
            ) }, {}
          )
        }
      }
    ]
  ])...)
}

data "azurerm_data_factory" "this" {
  name                = var.adf_name
  resource_group_name = var.adf_resource_group_name
}


resource "azurerm_data_factory_trigger_schedule" "this" {
  for_each = local.triggers

  name            = each.key
  data_factory_id = data.azurerm_data_factory.this.id

  # can be added later to add tags to the trigger
  # annotations = [each.value.tags]

  time_zone = local.time_zone
  interval  = each.value.schedule.interval
  frequency = each.value.schedule.frequency

  schedule {
    days_of_month = lookup(each.value.schedule, "days_of_month", null)
    days_of_week  = lookup(each.value.schedule, "days_of_week", null)
    hours         = lookup(each.value.schedule, "hours", [0])
    minutes       = lookup(each.value.schedule, "minutes", [0])
  }

  pipeline {
    name = each.value.pipeline_name
    parameters = merge([
      {
        "datastore_name" = each.value.datastore_name,
        "environment"    = each.value.environment,
        "dataset_name"   = each.value.dataset_name,
      },
      each.value.datastore_parameters,
      each.value.dataset_parameters,
      each.value.mapping,
    ]...)
  }
}
