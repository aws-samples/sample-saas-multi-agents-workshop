import json

def handler(event, context):
    """
    Pre Token Generation Lambda trigger for Cognito (Version 2)
    Adds custom attributes to the token claims
    """
    
    # Get user attributes
    user_attributes = event.get('request', {}).get('userAttributes', {})
    
    # Extract custom attributes
    tenant_id = user_attributes.get('custom:tenantId')
    user_role = user_attributes.get('custom:userRole')
    
    # Add custom claims to both access and ID tokens (Version 2 format)
    if tenant_id:
        event['response']['claimsAndScopeOverrideDetails'] = {
            'accessTokenGeneration': {
                'claimsToAddOrOverride': {
                    'tenantId': tenant_id
                }
            },
            'idTokenGeneration': {
                'claimsToAddOrOverride': {
                    'tenantId': tenant_id
                }
            }
        }
        
        if user_role:
            event['response']['claimsAndScopeOverrideDetails']['accessTokenGeneration']['claimsToAddOrOverride']['userRole'] = user_role
            event['response']['claimsAndScopeOverrideDetails']['idTokenGeneration']['claimsToAddOrOverride']['userRole'] = user_role
    
    return event
