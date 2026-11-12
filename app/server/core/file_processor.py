import json
import pandas as pd
import sqlite3
import io
import re
from typing import Dict, Any, List
from . import constants
from .sql_security import (
    execute_query_safely,
    validate_identifier,
    SQLSecurityError
)

def sanitize_table_name(table_name: str) -> str:
    """
    Sanitize table name for SQLite by removing/replacing bad characters
    and validating against SQL injection
    """
    # Remove file extension if present
    if '.' in table_name:
        table_name = table_name.rsplit('.', 1)[0]
    
    # Replace bad characters with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', table_name)
    
    # Ensure it starts with a letter or underscore
    if sanitized and not sanitized[0].isalpha() and sanitized[0] != '_':
        sanitized = '_' + sanitized
    
    # Ensure it's not empty
    if not sanitized:
        sanitized = 'table'
    
    # Validate the sanitized name
    try:
        validate_identifier(sanitized, "table")
    except SQLSecurityError:
        # If validation fails, use a safe default
        sanitized = f"table_{hash(table_name) % 100000}"
    
    return sanitized

def convert_csv_to_sqlite(csv_content: bytes, table_name: str) -> Dict[str, Any]:
    """
    Convert CSV file content to SQLite table
    """
    try:
        # Sanitize table name
        table_name = sanitize_table_name(table_name)
        
        # Read CSV into pandas DataFrame
        df = pd.read_csv(io.BytesIO(csv_content))
        
        # Clean column names
        df.columns = [col.lower().replace(' ', '_').replace('-', '_') for col in df.columns]
        
        # Connect to SQLite database
        conn = sqlite3.connect("db/database.db")
        
        # Write DataFrame to SQLite
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        # Get schema information using safe query execution
        cursor_info = execute_query_safely(
            conn,
            "PRAGMA table_info({table})",
            identifier_params={'table': table_name}
        )
        columns_info = cursor_info.fetchall()
        
        schema = {}
        for col in columns_info:
            schema[col[1]] = col[2]  # column_name: data_type
        
        # Get sample data using safe query execution
        cursor_sample = execute_query_safely(
            conn,
            "SELECT * FROM {table} LIMIT 5",
            identifier_params={'table': table_name}
        )
        sample_rows = cursor_sample.fetchall()
        column_names = [col[1] for col in columns_info]
        sample_data = [dict(zip(column_names, row)) for row in sample_rows]
        
        # Get row count using safe query execution
        cursor_count = execute_query_safely(
            conn,
            "SELECT COUNT(*) FROM {table}",
            identifier_params={'table': table_name}
        )
        row_count = cursor_count.fetchone()[0]
        
        conn.close()
        
        return {
            'table_name': table_name,
            'schema': schema,
            'row_count': row_count,
            'sample_data': sample_data
        }
        
    except Exception as e:
        raise Exception(f"Error converting CSV to SQLite: {str(e)}")

def convert_json_to_sqlite(json_content: bytes, table_name: str) -> Dict[str, Any]:
    """
    Convert JSON file content to SQLite table
    """
    try:
        # Sanitize table name
        table_name = sanitize_table_name(table_name)
        
        # Parse JSON
        data = json.loads(json_content.decode('utf-8'))
        
        # Ensure it's a list of objects
        if not isinstance(data, list):
            raise ValueError("JSON must be an array of objects")
        
        if not data:
            raise ValueError("JSON array is empty")
        
        # Convert to pandas DataFrame
        df = pd.DataFrame(data)
        
        # Clean column names
        df.columns = [col.lower().replace(' ', '_').replace('-', '_') for col in df.columns]
        
        # Connect to SQLite database
        conn = sqlite3.connect("db/database.db")
        
        # Write DataFrame to SQLite
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        # Get schema information using safe query execution
        cursor_info = execute_query_safely(
            conn,
            "PRAGMA table_info({table})",
            identifier_params={'table': table_name}
        )
        columns_info = cursor_info.fetchall()
        
        schema = {}
        for col in columns_info:
            schema[col[1]] = col[2]  # column_name: data_type
        
        # Get sample data using safe query execution
        cursor_sample = execute_query_safely(
            conn,
            "SELECT * FROM {table} LIMIT 5",
            identifier_params={'table': table_name}
        )
        sample_rows = cursor_sample.fetchall()
        column_names = [col[1] for col in columns_info]
        sample_data = [dict(zip(column_names, row)) for row in sample_rows]
        
        # Get row count using safe query execution
        cursor_count = execute_query_safely(
            conn,
            "SELECT COUNT(*) FROM {table}",
            identifier_params={'table': table_name}
        )
        row_count = cursor_count.fetchone()[0]
        
        conn.close()
        
        return {
            'table_name': table_name,
            'schema': schema,
            'row_count': row_count,
            'sample_data': sample_data
        }
        
    except Exception as e:
        raise Exception(f"Error converting JSON to SQLite: {str(e)}")

MAX_SQLITE_COLUMNS = 2000

def _flatten_record(value: Any, prefix: str = "", delimiter: str = None) -> Dict[str, Any]:
    """
    Flatten nested dicts/lists into a single-level dict. Path segments are joined
    with the delimiter; list items are denoted by their index.
    """
    if delimiter is None:
        delimiter = constants.NESTED_FIELD_DELIMITER

    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, list):
        items = enumerate(value)
    else:
        return {prefix: value}

    if not value:
        return {prefix: None}

    flat: Dict[str, Any] = {}
    for key, child in items:
        key = str(key)
        path = f"{prefix}{delimiter}{key}" if prefix else key
        flat.update(_flatten_record(child, path, delimiter))
    return flat

def convert_jsonl_to_sqlite(jsonl_content: bytes, table_name: str) -> Dict[str, Any]:
    """
    Convert JSONL file content to a single SQLite table
    """
    try:
        table_name = sanitize_table_name(table_name)

        # Pass 1: parse and flatten every line, collecting the union of all columns
        flat_records: List[Dict[str, Any]] = []
        all_columns: Dict[str, None] = {}
        for line_no, line in enumerate(jsonl_content.decode('utf-8-sig').splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_no}: {e.msg}")
            if not isinstance(record, dict):
                raise ValueError(f"Line {line_no} is not a JSON object")
            flat = _flatten_record(record)
            flat_records.append(flat)
            for key in flat:
                all_columns.setdefault(key, None)

        if not flat_records:
            raise ValueError("JSONL file is empty")

        # Clean column names, disambiguating collisions
        raw_columns = list(all_columns)
        used = set()
        clean_columns = []
        for col in raw_columns:
            base = col.lower().replace(' ', '_').replace('-', '_')
            name = base
            suffix = 1
            while name in used:
                suffix += 1
                name = f"{base}_{suffix}"
            used.add(name)
            clean_columns.append(name)

        if len(clean_columns) > MAX_SQLITE_COLUMNS:
            raise ValueError(
                f"Too many columns after flattening ({len(clean_columns)}); "
                f"SQLite supports at most {MAX_SQLITE_COLUMNS}"
            )

        # Pass 2: build the DataFrame with the full column set (missing -> NULL)
        rows = [[rec.get(col) for col in raw_columns] for rec in flat_records]
        df = pd.DataFrame(rows, columns=clean_columns)

        conn = sqlite3.connect("db/database.db")
        df.to_sql(table_name, conn, if_exists='replace', index=False)

        cursor_info = execute_query_safely(
            conn,
            "PRAGMA table_info({table})",
            identifier_params={'table': table_name}
        )
        columns_info = cursor_info.fetchall()
        schema = {col[1]: col[2] for col in columns_info}

        cursor_sample = execute_query_safely(
            conn,
            "SELECT * FROM {table} LIMIT 5",
            identifier_params={'table': table_name}
        )
        column_names = [col[1] for col in columns_info]
        sample_data = [dict(zip(column_names, row)) for row in cursor_sample.fetchall()]

        cursor_count = execute_query_safely(
            conn,
            "SELECT COUNT(*) FROM {table}",
            identifier_params={'table': table_name}
        )
        row_count = cursor_count.fetchone()[0]

        conn.close()

        return {
            'table_name': table_name,
            'schema': schema,
            'row_count': row_count,
            'sample_data': sample_data
        }

    except Exception as e:
        raise Exception(f"Error converting JSONL to SQLite: {str(e)}")