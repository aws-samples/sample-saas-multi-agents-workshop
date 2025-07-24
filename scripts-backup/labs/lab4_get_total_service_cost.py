from replace_code import replace_code_in_file

original_str = """# TODO: Lab4 - Get total input and output tokens cost"""

update_str = """# TODO: Lab4 - Get total input and output tokens cost
            if line_item in (EMBEDDING_TITAN_INPUT_TOKENS_LABEL, TEXTLITE_INPUT_TOKENS_LABEL,TEXTLITE_OUTPUT_TOKENS_LABEL):
                total_service_cost_dict[line_item] = cost
"""

replace_code_in_file("../../cdk/lib/tenant-template/services/aggregate-metrics/invoke_model_tenant_cost.py", original_str, update_str)
