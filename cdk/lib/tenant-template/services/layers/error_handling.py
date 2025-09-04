# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import traceback
import uuid
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from aws_lambda_powertools import Logger

# Initialize logger
logger = Logger()

# Type variables for function signatures
F = TypeVar('F', bound=Callable[..., Any])
R = TypeVar('R')

class AppError(Exception):
    """Base class for application errors"""
    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(self.message)

class ValidationError(AppError):
    """Error raised when input validation fails"""
    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR"):
        super().__init__(message, error_code, 400)

class AuthorizationError(AppError):
    """Error raised when authorization fails"""
    def __init__(self, message: str, error_code: str = "AUTHORIZATION_ERROR"):
        super().__init__(message, error_code, 403)

class ResourceNotFoundError(AppError):
    """Error raised when a resource is not found"""
    def __init__(self, message: str, error_code: str = "RESOURCE_NOT_FOUND"):
        super().__init__(message, error_code, 404)

class TenantIsolationError(AppError):
    """Error raised when tenant isolation is violated"""
    def __init__(self, message: str, error_code: str = "TENANT_ISOLATION_ERROR"):
        super().__init__(message, error_code, 403)

def handle_error(func: F) -> F:
    """
    Decorator for standardized error handling in Lambda functions
    
    Usage:
    @handle_error
    def handler(event, context):
        # Your handler code
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        try:
            return func(*args, **kwargs)
        except AppError as e:
            error_id = str(uuid.uuid4())
            logger.error({
                "error_id": error_id,
                "error_type": e.__class__.__name__,
                "error_code": e.error_code,
                "error_message": e.message,
                "status_code": e.status_code
            })
            return {
                "statusCode": e.status_code,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": e.message,
                    "error_code": e.error_code,
                    "error_id": error_id
                })
            }
        except Exception as e:
            error_id = str(uuid.uuid4())
            logger.error({
                "error_id": error_id,
                "error_type": e.__class__.__name__,
                "error_message": str(e),
                "stacktrace": traceback.format_exc()
            })
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "Internal server error",
                    "error_id": error_id
                })
            }
    
    return cast(F, wrapper)

def validate_tenant_access(tenant_id: str, user_tenant_id: str) -> None:
    """
    Validates that the user has access to the requested tenant
    
    Args:
        tenant_id: The tenant ID being accessed
        user_tenant_id: The tenant ID of the user
        
    Raises:
        TenantIsolationError: If the user does not have access to the tenant
    """
    if tenant_id != user_tenant_id:
        raise TenantIsolationError(f"User from tenant {user_tenant_id} cannot access resources from tenant {tenant_id}")

def validate_required_fields(data: Dict[str, Any], required_fields: list) -> None:
    """
    Validates that all required fields are present in the data
    
    Args:
        data: The data to validate
        required_fields: List of required field names
        
    Raises:
        ValidationError: If any required field is missing
    """
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    if missing_fields:
        raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")