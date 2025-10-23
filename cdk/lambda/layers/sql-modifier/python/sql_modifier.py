# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import re

def append_tenant_filter(sql: str, tenant_id: str) -> str:
    """
    Appends WHERE tenant_id = '{tenant_id}' to SQL query.
    Handles queries with existing WHERE clauses by adding AND condition.
    Properly handles GROUP BY, ORDER BY, and LIMIT clauses.
    """
    if not tenant_id:
        return sql
    
    sql = sql.strip()
    
    # Remove trailing semicolon if present
    if sql.endswith(';'):
        sql = sql[:-1].strip()
    
    # Find positions of GROUP BY, ORDER BY, and LIMIT clauses (case-insensitive)
    group_by_match = re.search(r'\s+GROUP\s+BY\s+', sql, re.IGNORECASE)
    order_by_match = re.search(r'\s+ORDER\s+BY\s+', sql, re.IGNORECASE)
    limit_match = re.search(r'\s+LIMIT\s+', sql, re.IGNORECASE)
    
    # Find the earliest position where we need to insert the tenant filter
    insert_pos = len(sql)
    if group_by_match:
        insert_pos = min(insert_pos, group_by_match.start())
    if order_by_match:
        insert_pos = min(insert_pos, order_by_match.start())
    if limit_match:
        insert_pos = min(insert_pos, limit_match.start())
    
    # Split SQL into main query and trailing clauses
    main_query = sql[:insert_pos].strip()
    trailing_clauses = sql[insert_pos:].strip()
    
    # Check if WHERE clause exists in main query
    if re.search(r'\bWHERE\b', main_query, re.IGNORECASE):
        # Add AND condition
        modified_sql = f"{main_query} AND tenant_id = '{tenant_id}'"
    else:
        # Add WHERE clause
        modified_sql = f"{main_query} WHERE tenant_id = '{tenant_id}'"
    
    # Append trailing clauses
    if trailing_clauses:
        modified_sql = f"{modified_sql} {trailing_clauses}"
    
    return modified_sql
