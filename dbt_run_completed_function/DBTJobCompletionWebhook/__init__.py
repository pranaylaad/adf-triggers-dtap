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
from typing import Any

import azure.functions as func
import yaml
from azure.identity import DefaultAzureCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
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
    subscription_id: str,
    resource_group_name: str,
    factory_name: str,
    pipeline_name: str,
    parameters: dict[str, Any],
):
    """Trigger the ADF trigger."""
    logger.info(f"Triggering pipeline {pipeline_name} with parameters {parameters}")

    client = DataFactoryManagementClient(
        credential=DefaultAzureCredential(), subscription_id=subscription_id
    )

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


def main(req: func.HttpRequest):
    auth_header = req.headers.get("authorization", None)
    request_body = req.get_body()

    if not _is_authentic(auth_header, request_body):
        logger.warning("DBT Webhook, not authenticated")
        return

    request_json = req.get_json()
    run_data = request_json["data"]
    run_state = run_data["runStatus"]

    run_id = run_data["runId"]
    job_id = run_data["jobId"]

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
    annotations = f"RunId={run_id}, JobId={job_id}"
    parameters["annotations"] = annotations

    result = _create_pipeline_run(
        subscription_id=subscription_id,
        resource_group_name=resource_group_name,
        factory_name=factory_name,
        pipeline_name=pipeline_name,
        parameters=parameters,
    )

    logger.info(f"ADF pipeline triggered, result: {result}")
