from replace_code import replace_code_in_file

original_str = """# TODO: Lab1 - Add tenant provisioning service"""

update_str = """# TODO: Lab1 - Add tenant provisioning service
tenant_provision_output=$(python3 lib/tenant-template/tenant-provisioning/tenant_provisioning_service.py --tenantid "$CDK_PARAM_TENANT_ID" 2>&1 > /dev/null && exit_code=$?) || exit_code=$?
check_error "$provision_name" $exit_code "$tenant_provision_output"
"""

replace_code_in_file("../provision-tenant.sh", original_str, update_str)
