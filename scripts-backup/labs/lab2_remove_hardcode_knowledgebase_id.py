from replace_code import replace_code_in_file_regex

old_pattern = r"""# TODO: Lab2 - uncomment below and hardcode an knowledge base id
        \s*knowledge_base_id = ".*?"
        \s*logger\.info\(f"hard coded knowledge base id: \{knowledge_base_id\}"\)"""

update_str = """# TODO: Lab2 - uncomment below and hardcode an knowledge base id
        # knowledge_base_id = "<hardcode knowledge base id>"
        # logger.info(f"hard coded knowledge base id: {knowledge_base_id}")
"""

replace_code_in_file_regex("../../cdk/lib/tenant-template/services/ragService/rag_service.py", old_pattern, update_str)


