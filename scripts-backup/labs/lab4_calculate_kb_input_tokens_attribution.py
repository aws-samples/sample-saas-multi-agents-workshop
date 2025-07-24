from replace_code import replace_code_in_file

original_kb_tokens_str = """#TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get knowledge base input tokens
        knowledgebase_input_tokens_query = ""
        """

update_kb_tokens_str = r"""#TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get knowledge base input tokens
        knowledgebase_input_tokens_query = "fields @timestamp, identity.arn, input.inputTokenCount \
                        | filter modelId like /amazon.titan-embed-text-v1/ and operation = 'InvokeModel' \
                        | parse identity.arn '/bedrock-kb-role-*/' as tenantId \
                        | filter ispresent(tenantId) \
                        | stats sum(input.inputTokenCount) as TotalInputTokens by tenantId, dateceil(@timestamp, 1d) as timestamp \
                        | sort totalInputTokenCount desc"
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_kb_tokens_str, update_kb_tokens_str)

original_total_kb_tokens_str = """# TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get total knowledge base input tokens
        total_knowledgebase_input_tokens_query = ""
        """

update_total_kb_tokens_str = r"""# TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get total knowledge base input tokens
        total_knowledgebase_input_tokens_query = "fields @timestamp, identity.arn, input.inputTokenCount \
                        | filter modelId like /amazon.titan-embed-text-v1/ and operation = 'InvokeModel' \
                        | parse identity.arn '/bedrock-kb-role-*/' as tenantId \
                        | filter ispresent(tenantId) \
                        | stats sum(input.inputTokenCount) as TotalInputTokens, dateceil(@timestamp, 1d) as timestamp"
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_total_kb_tokens_str, update_total_kb_tokens_str)


original_kb_tokens_attribution_str = """# TODO: Lab4 - Calculate the percentage of tenant attribution for knowledge base input tokens
                tenant_kb_input_tokens_attribution_percentage = 0
        """

update_kb_tokens_attribution_str = """# TODO: Lab4 - Calculate the percentage of tenant attribution for knowledge base input tokens
                tenant_kb_input_tokens_attribution_percentage = input_tokens/total_knowledgebase_input_tokens
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_kb_tokens_attribution_str, update_kb_tokens_attribution_str)

