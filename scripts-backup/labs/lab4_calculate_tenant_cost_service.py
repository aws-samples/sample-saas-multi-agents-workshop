from replace_code import replace_code_in_file

original_tenant_cost_service_str = """# TODO: Lab4 - Calculate tenant cost for generating final tenant specific response
            tenant_input_tokens_cost = 0
            tenant_output_tokens_cost = 0
"""

update_tenant_cost_service_str = """# TODO: Lab4 - Calculate tenant cost for generating final tenant specific response
            tenant_input_tokens_cost = self.__get_tenant_cost(TEXTLITE_INPUT_TOKENS_LABEL, total_service_cost_dict, tenant_attribution_percentage_json)
            tenant_output_tokens_cost = self.__get_tenant_cost(TEXTLITE_OUTPUT_TOKENS_LABEL, total_service_cost_dict, tenant_attribution_percentage_json)
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_tenant_cost_service_str, update_tenant_cost_service_str)

