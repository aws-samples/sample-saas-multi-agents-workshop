from replace_code import replace_code_in_file

def replace_kb_id(kb_id):
        
        original_str = """# TODO: Lab2 - uncomment below and hardcode an knowledge base id
        # knowledge_base_id = "<hardcode knowledge base id>"
        # logger.info(f"hard coded knowledge base id: {knowledge_base_id}")"""

        update_str = f"""# TODO: Lab2 - uncomment below and hardcode an knowledge base id
        knowledge_base_id = "{kb_id}"
        logger.info(f"hard coded knowledge base id: {{knowledge_base_id}}")
        """

        replace_code_in_file("../../cdk/lib/tenant-template/services/ragService/rag_service.py", original_str, update_str)


if __name__ == "__main__":
    kb_id = input("Enter the knowledge base id: ")
    replace_kb_id(kb_id)
