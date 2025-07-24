# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
import hashlib
from aws_lambda_powertools import Logger, Tracer
from collections import namedtuple

logger = Logger()

# Define a named tuple for session parameters
SessionParameters = namedtuple(
    typename="SessionParameters",
    field_names=["aws_access_key_id", "aws_secret_access_key", "aws_session_token"],
)

def assume_role(access_role_arn: str, request_tags: list[tuple[str, str]], duration_sec: int = 900) -> SessionParameters:
    logger.info(f"Trying to assume role ARN: {access_role_arn} with tags: {request_tags}")

    sts = boto3.client("sts")

    try:
        tags_str = "-".join([f"{name}={value}" for name, value in request_tags])
        role_session_name = hashlib.sha256(tags_str.encode()).hexdigest()[:32]
        
        assume_role_response = sts.assume_role(
            RoleArn=access_role_arn,
            DurationSeconds=duration_sec,
            RoleSessionName=role_session_name,
            Tags=[{"Key": name, "Value": value} for name, value in request_tags],
        )

    except Exception as exception:
        logger.error(exception)
        return None

    logger.info(f"Assumed role ARN: {assume_role_response['AssumedRoleUser']['Arn']}")

    session_parameters = SessionParameters(
        aws_access_key_id=assume_role_response["Credentials"]["AccessKeyId"],
        aws_secret_access_key=assume_role_response["Credentials"]["SecretAccessKey"],
        aws_session_token=assume_role_response["Credentials"]["SessionToken"],
    )

    return session_parameters