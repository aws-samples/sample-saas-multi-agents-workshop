from replace_code import replace_code_in_file

original_tenant_cost_kb_str = """# TODO: Lab4 - Calculate tenant cost for ingesting & retrieving tenant data to/from Amazon Bedrock Knowledge Base
            tenant_kb_input_tokens_cost = 0
        """

update_tenant_cost_kb_str = """# TODO: Lab4 - Calculate tenant cost for ingesting & retrieving tenant data to/from Amazon Bedrock Knowledge Base
            tenant_kb_input_tokens_cost = self.__get_tenant_cost(EMBEDDING_TITAN_INPUT_TOKENS_LABEL, total_service_cost_dict, tenant_attribution_percentage_json)
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_tenant_cost_kb_str, update_tenant_cost_kb_str)

