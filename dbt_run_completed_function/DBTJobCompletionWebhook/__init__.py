"""This script triggers an ADF pipeline when a dbt run completes successfully.

To trigger the ADF pipeline, pipeline parameters are required. Those are expected to be
provided in a `config.yaml` file in the same directory as this script. The `config.yaml`
file should have the following structure:
    pipeline_name: <pipeline_name>
    pipeline_parameters:
        <parameter_name>: <parameter_value>
        ...
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import azure.functions as func
import yaml
from azure.identity import DefaultAzureCredential
from azure.mgmt.datafactory import DataFactoryManagementClient, models
from opencensus.ext.azure.log_exporter import AzureLogHandler

logger = logging.getLogger(__name__)
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    logger.addHandler(
        AzureLogHandler(
            connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
        )
    )
logger.setLevel(logging.INFO)


def _is_authentic(auth_header: str, request_body: bytes) -> bool:
    """Authenticate the request using dbt token."""
    if not os.environ.get("DBT_CLOUD_AUTH_TOKEN"):
        logger.warning("DBT Cloud auth token not set")
        return False

    app_secret = os.environ["DBT_CLOUD_AUTH_TOKEN"].encode("utf-8")
    signature = hmac.new(app_secret, request_body, hashlib.sha256).hexdigest()
    return signature == auth_header


def _get_env_var_with_readable_error(var_name: str) -> str:
    """Get the env var and print a readable error if it is not set"""
    var = os.environ.get(var_name)
    if not var:
        raise ValueError(f"Environment variable {var_name} is not set")
    return var


def _create_pipeline_run(
    client: DataFactoryManagementClient,
    resource_group_name: str,
    factory_name: str,
    pipeline_name: str,
    parameters: dict[str, Any],
):
    """Trigger the ADF trigger."""
    logger.info(f"Triggering pipeline {pipeline_name} with parameters {parameters}")

    response = client.pipelines.create_run(
        resource_group_name=resource_group_name,
        factory_name=factory_name,
        pipeline_name=pipeline_name,
        parameters=parameters,
    )

    return response


def load_config():
    """Load the config file."""
    current_dir = os.path.dirname(__file__)

    # Construct the full path to the config.yaml file
    config_path = os.path.join(current_dir, "config.yaml")

    with open(config_path, "r") as file:
        config = yaml.safe_load(file)

    logger.debug(f"Config:\n{config}")

    return config


def _is_pipeline_running(
    client: DataFactoryManagementClient,
    resource_group_name: str,
    factory_name: str,
    pipeline_name: str,
    annotations: str,
) -> bool:
    """Check if the pipeline is already running.

    This check is done in order to avoid triggering the pipeline multiple times which
    might happen if the Azure Function takes too long to start up. The dbt webhook has
    a retry mechanism which fires off after a timeout if the Azure Function does not
    respond in time. If this happens, we do not want to trigger the ADF pipeline twice.

    Args:
        client: The ADF client to use for querying the pipeline existing pipeline runs
        resource_group_name: The resource group name.
        factory_name: The factory name where the pipeline is triggered
        pipeline_name: The pipeline name to check for
        annotations: The annotations to check for in the running pipeline

    Returns:
        True if the pipeline is already running, False otherwise

    """
    logger.info("Checking if pipeline is already running")

    # Try to filter out the runs that were updated in the last 2 minutes
    # to catch the edge case where the Azure Function was triggered twice
    # before it fully started.
    filter_parameters = models.RunFilterParameters(
        last_updated_after=datetime.now() - timedelta(minutes=15),
        last_updated_before=datetime.now(),
        filters=[
            models.RunQueryFilter(
                operand=models.RunQueryFilterOperand.PIPELINE_NAME,
                operator=models.RunQueryFilterOperator.EQUALS,
                values=[pipeline_name],
            ),
            models.RunQueryFilter(
                operand=models.RunQueryFilterOperand.STATUS,
                operator=models.RunQueryFilterOperator.IN,
                values=["Queued", "InProgress"],
            ),
        ],
    )

    runs = client.pipeline_runs.query_by_factory(
        resource_group_name=resource_group_name,
        factory_name=factory_name,
        filter_parameters=filter_parameters,
    )

    logger.info(f"Found {len(runs.value)} runs for pipeline {pipeline_name}")

    # Check if the running pipeline was triggered by the same dbt job by dbt job id
    # which are stored in the annotations. The annotations str contains dbt run id and
    # dbt job id which we can use to check if the same job fired off the function.
    for run in runs.value:
        if run.additional_properties:
            # In ADF, the annotations are stored as a list of strings in the
            # additional_properties rather than simple strings as seen in the
            # main function of this code.
            if "annotations" in run.additional_properties:
                pipeline_annotations = run.additional_properties["annotations"]
                if (
                    len(pipeline_annotations) == 1
                    and pipeline_annotations[0] == annotations
                ):
                    logger.warning(
                        f"Pipeline is already running with annotations {annotations}"
                    )
                    return True
    logger.info(f"Pipeline is not running with annotations {annotations}")
    return False


def _get_adf_client(subscription_id: str) -> DataFactoryManagementClient:
    """Instantiate the ADF client."""
    logger.info(f"Creating ADF management client for subscription {subscription_id}")
    return DataFactoryManagementClient(
        credential=DefaultAzureCredential(), subscription_id=subscription_id
    )


def main(req: func.HttpRequest):
    auth_header = req.headers.get("authorization", None)
    request_body = req.get_body()

    if not _is_authentic(auth_header, request_body):
        logger.warning("DBT Webhook, not authenticated")
        return

    request_json = req.get_json()
    run_data = request_json["data"]
    run_state = run_data["runStatus"]

    dbt_run_id = run_data["runId"]
    dbt_job_id = run_data["jobId"]

    logger.info(f"DBT run state: {run_state}")

    if run_state != "Success":
        logger.warning(f"DBT run not successful, run state: {run_state}")
        return

    config = load_config()

    # some variables are stored in the environment
    subscription_id = _get_env_var_with_readable_error("SUBSCRIPTION_ID")
    if subscription_id.startswith("/subscriptions/"):
        subscription_id = subscription_id.strip("/subscriptions/")
    resource_group_name = _get_env_var_with_readable_error("RESOURCE_GROUP")
    factory_name = _get_env_var_with_readable_error("FACTORY_NAME")

    # some variables are stored in the config file
    pipeline_name: str = config["pipeline_name"]
    parameters: dict[str, str] = config.get("pipeline_parameters", {})
    annotations = f"RunId={dbt_run_id}, JobId={dbt_job_id}"
    parameters["annotations"] = annotations

    client = _get_adf_client(subscription_id=subscription_id)

    if _is_pipeline_running(
        client=client,
        resource_group_name=resource_group_name,
        factory_name=factory_name,
        pipeline_name=pipeline_name,
        annotations=annotations,
    ):
        logger.warning("ADF pipeline is already running")
        return

    result = _create_pipeline_run(
        client=client,
        resource_group_name=resource_group_name,
        factory_name=factory_name,
        pipeline_name=pipeline_name,
        parameters=parameters,
    )

    logger.info(f"ADF pipeline triggered, result: {result}")
