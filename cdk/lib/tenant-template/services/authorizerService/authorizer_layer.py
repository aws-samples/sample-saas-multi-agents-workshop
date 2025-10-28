# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from jose import jwk, jwt
from jose.utils import base64url_decode
import time
import re
import boto3
from aws_lambda_powertools import Logger, Tracer
from collections import namedtuple


logger = Logger()


def validateJWT(token, app_client_id, keys):
    """
    Validate the provided JWT token.
    
    Args:
        token (str): The JWT token to validate.
        app_client_id (str): The client ID the token was issued for.
        keys (list): The list of public keys to use for verification.
        
    Returns:
        dict: The decoded claims if the token is valid, False otherwise.
    """
    try:
        # Get the kid from the headers prior to verification
        headers = jwt.get_unverified_headers(token)
        kid = headers['kid']
        
        # Search for the kid in the downloaded public keys
        key_index = -1
        for i, key in enumerate(keys):
            if kid == key['kid']:
                key_index = i
                break
        if key_index == -1:
            logger.info('Public key not found in jwks.json')
            return False
        
        # Construct the public key
        public_key = jwk.construct(keys[key_index])
        
        # Get the last two sections of the token (message and signature)
        message, encoded_signature = str(token).rsplit('.', 1)
        
        # Decode the signature
        decoded_signature = base64url_decode(encoded_signature.encode('utf-8'))
        
        # Verify the signature
        if not public_key.verify(message.encode("utf8"), decoded_signature):
            logger.info('Signature verification failed')
            return False
        
        logger.info('Signature successfully verified')
        
        # Get the unverified claims
        claims = jwt.get_unverified_claims(token)
        
        # Verify the token expiration
        if time.time() > claims['exp']:
            # logger.info('Token is expired')
            return False
        
        # Verify the audience
        if claims['aud'] != app_client_id:
            logger.info('Token was not issued for this audience')
            return False
        
        logger.info(claims)
        return claims
    except Exception as e:
        logger.error(f"Error validating JWT: {e}")
        return False

class HttpVerb:
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    HEAD = "HEAD"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    ALL = "*"

class AuthPolicy:
    """
    Class for creating and managing authentication policies.
    """
    awsAccountId = ""
    """The AWS account id the policy will be generated for."""
    principalId = ""
    """The principal used for the policy, this should be a unique identifier for the end user."""
    version = "2012-10-17"
    """The policy version used for the evaluation."""
    pathRegex = "^[/.a-zA-Z0-9-\*]+$"
    """The regular expression used to validate resource paths for the policy"""

    allowMethods = []
    denyMethods = []

    restApiId = "*"
    """The API Gateway API id. By default this is set to '*'"""
    region = "*"
    """The region where the API is deployed. By default this is set to '*'"""
    stage = "*"
    """The name of the stage used in the policy. By default this is set to '*'"""

    def __init__(self, principal, awsAccountId):
        self.awsAccountId = awsAccountId
        self.principalId = principal
        self.allowMethods = []
        self.denyMethods = []

    def _addMethod(self, effect, verb, resource, conditions):
        """
        Adds a method to the internal lists of allowed or denied methods.
        
        Args:
            effect (str): "Allow" or "Deny".
            verb (str): The HTTP verb (GET, POST, etc.) or "*" for all verbs.
            resource (str): The resource path.
            conditions (dict): Additional conditions for the policy statement.
        
        Raises:
            NameError: If the HTTP verb or resource path is invalid.
        """
        if verb != "*" and not hasattr(HttpVerb, verb):
            raise NameError(f"Invalid HTTP verb '{verb}'. Allowed verbs in HttpVerb class")
        
        resourcePattern = re.compile(self.pathRegex)
        if not resourcePattern.match(resource):
            raise NameError(f"Invalid resource path: '{resource}'. Path should match '{self.pathRegex}'")

        if resource[:1] == "/":
            resource = resource[1:]

        resourceArn = (
            "arn:aws:execute-api:"
            + self.region
            + ":"
            + self.awsAccountId
            + ":"
            + self.restApiId
            + "/"
            + self.stage
            + "/"
            + verb
            + "/"
            + resource
        )

        if effect.lower() == "allow":
            self.allowMethods.append({"resourceArn": resourceArn, "conditions": conditions})
        elif effect.lower() == "deny":
            self.denyMethods.append({"resourceArn": resourceArn, "conditions": conditions})

    # Other methods omitted for brevity

def create_auth_success_policy(
    method_arn: str,
    tenant_id: str,
    tenant_name: str,
    knowledge_base_id: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    aws_session_token: str,
    api_key: str
) -> dict:
    """
    Creates a success policy for the authorizer to return.

    Args:
        method_arn (str): The ARN of the API Gateway method.
        tenant_id (str): The tenant ID.
        tenant_name (str): The tenant name.
        knowledge_base_id (str): The knowledge base ID.
        aws_access_key_id (str): The AWS access key ID.
        aws_secret_access_key (str): The AWS secret access key.
        aws_session_token (str): The AWS session token.

    Returns:
        dict: The success policy.
    """
    authorization_success_policy = {
        "principalId": tenant_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": method_arn,
                }
            ],
        },
        "context": {
            "knowledge_base_id": knowledge_base_id,
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
            "aws_session_token": aws_session_token,
            "tenant_name": tenant_name
        },
        "usageIdentifierKey": api_key
    }
    return authorization_success_policy

def create_auth_denied_policy(method_arn: str) -> dict:
    """
    Creates a deny policy for the authorizer to return.
    
    Args:
        method_arn (str): The ARN of the API Gateway method.
        
    Returns:
        dict: The deny policy.
    """
    authorization_deny_policy = {
        "principalId": "",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Deny",
                    "Resource": method_arn,
                }
            ],
        },
    }
    return authorization_deny_policy


