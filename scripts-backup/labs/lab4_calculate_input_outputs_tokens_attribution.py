from replace_code import replace_code_in_file

original_input_output_tokens_str = """# TODO: Lab4 - Add Amazon CloudWatch logs insights queries for converse input output tokens
        converse_input_output_tokens_query = ""
        """

update_input_output_tokens_str = r"""# TODO: Lab4 - Add Amazon CloudWatch logs insights queries for converse input output tokens
        converse_input_output_tokens_query = "filter @message like /ModelInvocationInputTokens|ModelInvocationOutputTokens/ \
                            | fields tenant_id as TenantId, ModelInvocationInputTokens.0 as ModelInvocationInputTokens, ModelInvocationOutputTokens.0 as ModelInvocationOutputTokens \
                            | stats sum(ModelInvocationInputTokens) as TotalInputTokens, sum(ModelInvocationOutputTokens) as TotalOutputTokens by TenantId, dateceil(@timestamp, 1d) as timestamp"
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_input_output_tokens_str, update_input_output_tokens_str)

original_total_input_output_tokens_str = """# TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get total converse input output tokens
        total_converse_input_output_tokens_query = ""
        """

update_total_input_output_tokens_str = r"""# TODO: Lab4 - Add Amazon CloudWatch logs insights queries to get total converse input output tokens
        total_converse_input_output_tokens_query = "filter @message like /ModelInvocationInputTokens|ModelInvocationOutputTokens/ \
                                | fields ModelInvocationInputTokens.0 as ModelInvocationInputTokens, ModelInvocationOutputTokens.0 as ModelInvocationOutputTokens \
                                | stats sum(ModelInvocationInputTokens) as TotalInputTokens, sum(ModelInvocationOutputTokens) as TotalOutputTokens by dateceil(@timestamp, 1d) as timestamp"
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_total_input_output_tokens_str, update_total_input_output_tokens_str)


original_input_output_tokens_attribution_str = """# TODO: Lab4 - Calculate the percentage of tenant attribution for converse input and output tokens
                    tenant_attribution_input_tokens_percentage = 0
                    tenant_attribution_output_tokens_percentage = 0
        """

update_input_output_tokens_attribution_str = """# TODO: Lab4 - Calculate the percentage of tenant attribution for converse input and output tokens
                    tenant_attribution_input_tokens_percentage = tenant_input_tokens/total_input_tokens
                    tenant_attribution_output_tokens_percentage = tenant_output_tokens/total_input_tokens
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_input_output_tokens_attribution_str, update_input_output_tokens_attribution_str)

