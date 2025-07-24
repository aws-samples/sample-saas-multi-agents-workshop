from replace_code import replace_code_in_file
       
original_str = """// TODO: Lab2 - Add principalTag in ABAC policy
                    resourceName: "*","""

update_str = """// TODO: Lab2 - Add principalTag in ABAC policy
                    resourceName: "${aws:PrincipalTag/KnowledgeBaseId}","""

replace_code_in_file("../../cdk/lib/tenant-template/services.ts", original_str, update_str)


