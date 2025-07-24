from replace_code import replace_code_in_file

original_str = """# TODO: Lab3 - Enable tenant token usage"""

update_str = """# TODO: Lab3 - Enable tenant token usage
        if ('/invoke' in method_arn and __is_tenant_token_limit_exceeded(tenant_id, input_tokens, output_tokens)) :
            return authorizer_layer.create_auth_denied_policy(method_arn)
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/authorizerService/tenant_authorizer.py", original_str, update_str)
