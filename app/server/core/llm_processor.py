import os
import json
import asyncio
from typing import Dict, Any
from openai import OpenAI
from anthropic import Anthropic
from core.data_models import QueryRequest

def build_sql_prompt(query_text: str, schema_info: Dict[str, Any]) -> str:
    schema_description = format_schema_for_prompt(schema_info)
    return f"""Given the following database schema:

{schema_description}

Convert this natural language query to SQL: "{query_text}"

Rules:
- Return ONLY the SQL query, no explanations
- Use proper SQLite syntax
- Handle date/time queries appropriately (e.g., "last week" = date('now', '-7 days'))
- Be careful with column names and table names
- If the query is ambiguous, make reasonable assumptions

SQL Query:"""

def clean_sql(sql: str) -> str:
    sql = sql.strip()
    if sql.startswith("```sql"):
        sql = sql[6:]
    if sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]
    return sql.strip()

def generate_sql_with_openai(query_text: str, schema_info: Dict[str, Any]) -> str:
    """
    Generate SQL query using OpenAI API
    """
    try:
        # Get API key from environment
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        client = OpenAI(api_key=api_key)

        prompt = build_sql_prompt(query_text, schema_info)

        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a SQL expert. Convert natural language to SQL queries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500
        )
        
        return clean_sql(response.choices[0].message.content)
        
    except Exception as e:
        raise Exception(f"Error generating SQL with OpenAI: {str(e)}")

def generate_sql_with_anthropic(query_text: str, schema_info: Dict[str, Any]) -> str:
    """
    Generate SQL query using Anthropic API
    """
    try:
        # Get API key from environment
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        client = Anthropic(api_key=api_key)
        
        prompt = build_sql_prompt(query_text, schema_info)
        
        # Call Anthropic API
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            temperature=0.1,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return clean_sql(response.content[0].text)
        
    except Exception as e:
        raise Exception(f"Error generating SQL with Anthropic: {str(e)}")

def generate_sql_with_copilot(query_text: str, schema_info: Dict[str, Any]) -> str:
    async def run() -> str:
        try:
            from copilot import CopilotClient
            from copilot.session_events import AssistantMessageData
        except ImportError as e:
            raise RuntimeError("Copilot requires Python 3.11+ and github-copilot-sdk") from e

        async with CopilotClient(mode="empty") as client:
            async with await client.create_session(model="auto", available_tools=[]) as session:
                response = await session.send_and_wait(build_sql_prompt(query_text, schema_info))
                if response is None or not isinstance(response.data, AssistantMessageData):
                    raise RuntimeError("Copilot returned no assistant message")
                sql = clean_sql(response.data.content)
                if not sql:
                    raise RuntimeError("Copilot returned an empty SQL query")
                return sql

    try:
        return asyncio.run(run())
    except Exception as e:
        raise RuntimeError(f"Error generating SQL with Copilot: {e}") from e

def format_schema_for_prompt(schema_info: Dict[str, Any]) -> str:
    """
    Format database schema for LLM prompt
    """
    lines = []
    
    for table_name, table_info in schema_info.get('tables', {}).items():
        lines.append(f"Table: {table_name}")
        lines.append("Columns:")
        
        for col_name, col_type in table_info['columns'].items():
            lines.append(f"  - {col_name} ({col_type})")
        
        lines.append(f"Row count: {table_info['row_count']}")
        lines.append("")
    
    return "\n".join(lines)

def generate_sql(request: QueryRequest, schema_info: Dict[str, Any]) -> str:
    """
    Route to appropriate LLM provider based on API key availability and request preference.
    An explicit Copilot request wins. Otherwise configured keys take priority:
    OpenAI, Anthropic, then Copilot.
    """
    if request.llm_provider == "copilot":
        return generate_sql_with_copilot(request.query, schema_info)

    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    
    # Check API key availability first (OpenAI priority)
    if openai_key:
        return generate_sql_with_openai(request.query, schema_info)
    elif anthropic_key:
        return generate_sql_with_anthropic(request.query, schema_info)
    elif os.environ.get("COPILOT_GITHUB_TOKEN"):
        return generate_sql_with_copilot(request.query, schema_info)
    
    # Fall back to request preference if both keys available or neither available
    if request.llm_provider == "openai":
        return generate_sql_with_openai(request.query, schema_info)
    else:
        return generate_sql_with_anthropic(request.query, schema_info)