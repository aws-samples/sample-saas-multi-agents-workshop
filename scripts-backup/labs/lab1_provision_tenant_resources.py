from replace_code import replace_code_in_file

original_str = """# TODO: Lab1 - Add provision tenant resources"""

update_str = """# TODO: Lab1 - Add provision tenant resources
        __create_opensearch_serverless_tenant_index(tenant_id, kb_collection_endpoint_domain)
        __create_s3_tenant_prefix(tenant_id, rule_name)
        __create_tenant_knowledge_base(tenant_id, kb_collection_name, rule_name)
"""

replace_code_in_file("../../cdk/lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py", original_str, update_str)
