from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from config import (
    ACCOUNTADMIN_IS_ADMIN,
    ADMIN_ROLE,
    APP_DATABASE,
    APP_SCHEMA,
    APPROVED_STATUS,
    ENABLE_FOREIGN_KEY_VALIDATION,
    FOREIGN_KEY_CHECKS,
    KEY_COLUMNS,
    MART_SCHEMA,
    PENDING_STATUS,
    RECORD_TYPES,
    REJECTED_STATUS,
    REQUIRED_TABLES,
    SOURCE_APP,
    WRITEBACK_TABLES,
)
from validators import ValidationError, validate_record


CREATE_SCHEMA_SQL = f"""
CREATE SCHEMA IF NOT EXISTS {APP_DATABASE}.{APP_SCHEMA}
    COMMENT = 'Writable Streamlit app schema for app-specific writeback tables'
"""

COMMON_APPROVAL_COLUMNS = f"""
        APPROVAL_STATUS VARCHAR(30) DEFAULT '{PENDING_STATUS}',
        SUBMITTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
        SUBMITTED_BY VARCHAR(200) DEFAULT CURRENT_USER(),
        APPROVED_AT TIMESTAMP_NTZ,
        APPROVED_BY VARCHAR(200),
        APPROVAL_COMMENT VARCHAR(1000),
        REJECTED_AT TIMESTAMP_NTZ,
        REJECTED_BY VARCHAR(200),
        REJECTION_REASON VARCHAR(1000),
        CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
        CREATED_BY VARCHAR(200) DEFAULT CURRENT_USER(),
        UPDATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
        UPDATED_BY VARCHAR(200) DEFAULT CURRENT_USER(),
        SOURCE_APP VARCHAR(100) DEFAULT '{SOURCE_APP}'
"""


def build_create_table_sql(record_type, record_config):
    ddl_columns = ",\n        ".join(record_config["ddl_columns"])
    table_name = record_config["table_name"]
    key_column = record_config["key_column"]
    return f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        {ddl_columns},
{COMMON_APPROVAL_COLUMNS},
        CONSTRAINT PK_{record_config["physical_table_name"]} PRIMARY KEY ({key_column})
    )
    """


CREATE_TABLE_SQL = [
    build_create_table_sql(record_type, record_config)
    for record_type, record_config in RECORD_TYPES.items()
]


def is_app_admin(session):
    accountadmin_clause = "OR CURRENT_ROLE() = 'ACCOUNTADMIN'" if ACCOUNTADMIN_IS_ADMIN else ""
    sql = f"""
        SELECT
            IS_ROLE_IN_SESSION('{ADMIN_ROLE}')
            {accountadmin_clause}
    """
    return bool(session.sql(sql).collect()[0][0])


def require_admin(session):
    if not is_app_admin(session):
        raise PermissionError("Only a Streamlit app admin can approve, reject, or initialise app storage.")


def get_missing_tables(session):
    quoted_tables = ", ".join(f"'{table_name}'" for table_name in sorted(REQUIRED_TABLES))
    rows = session.sql(
        f"""
        SELECT TABLE_NAME
        FROM {APP_DATABASE}.INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{APP_SCHEMA}'
          AND TABLE_NAME IN ({quoted_tables})
        """
    ).collect()
    existing = {row["TABLE_NAME"] for row in rows}
    return sorted(REQUIRED_TABLES - existing)


def create_storage_objects(session):
    require_admin(session)
    session.sql(CREATE_SCHEMA_SQL).collect()
    for statement in CREATE_TABLE_SQL:
        session.sql(statement).collect()


def load_recent_records(session, record_type, limit=50):
    table_name = WRITEBACK_TABLES[record_type]
    key_column = KEY_COLUMNS[record_type]
    return session.sql(
        f"""
        SELECT *
        FROM {table_name}
        ORDER BY {key_column} DESC
        LIMIT {int(limit)}
        """
    ).to_pandas()


def load_pending_records(session, record_type):
    table_name = WRITEBACK_TABLES[record_type]
    key_column = KEY_COLUMNS[record_type]
    return session.sql(
        f"""
        SELECT *
        FROM {table_name}
        WHERE APPROVAL_STATUS = '{PENDING_STATUS}'
        ORDER BY {key_column} ASC
        """
    ).to_pandas()


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, float) and pd.isna(value):
        return "NULL"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return f"'{value.isoformat()}'"

    text = str(value).replace("'", "''")
    return f"'{text}'"


def key_exists(session, table_name, column_name, value):
    if value is None:
        return True
    rows = session.sql(
        f"""
        SELECT COUNT(*) AS CNT
        FROM {APP_DATABASE}.{MART_SCHEMA}.{table_name}
        WHERE {column_name} = {sql_literal(value)}
        """
    ).collect()
    return rows[0]["CNT"] > 0


def validate_foreign_keys(session, payload):
    missing = []
    for field_name, check in FOREIGN_KEY_CHECKS.items():
        if field_name not in payload:
            continue
        value = payload.get(field_name)
        if value is not None and not key_exists(session, check["table"], check["column"], value):
            missing.append(f"{field_name}={value} not found in {check['table']}.{check['column']}")

    if missing:
        raise ValidationError("Invalid foreign key selection: " + "; ".join(missing))


def insert_record(session, record_type, payload):
    validate_record(record_type, payload)
    if ENABLE_FOREIGN_KEY_VALIDATION:
        validate_foreign_keys(session, payload)

    columns = list(payload.keys())
    values = [sql_literal(payload[column]) for column in columns]
    table_name = WRITEBACK_TABLES[record_type]

    sql = f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        SELECT {", ".join(values)}
    """
    session.sql(sql).collect()


def set_record_statuses(session, record_type, record_keys, status, review_comment=None):
    require_admin(session)
    if status not in {APPROVED_STATUS, REJECTED_STATUS}:
        raise ValidationError("Admin action must approve or reject the submitted record.")

    record_keys = [record_key for record_key in record_keys if record_key is not None]
    if not record_keys:
        raise ValidationError("Select at least one pending record to review.")

    table_name = WRITEBACK_TABLES[record_type]
    key_column = KEY_COLUMNS[record_type]
    status_sql = sql_literal(status)
    comment_sql = sql_literal(review_comment)
    record_keys_sql = ", ".join(sql_literal(record_key) for record_key in record_keys)

    if status == APPROVED_STATUS:
        sql = f"""
            UPDATE {table_name}
            SET APPROVAL_STATUS = {status_sql},
                APPROVED_AT = CURRENT_TIMESTAMP(),
                APPROVED_BY = CURRENT_USER(),
                APPROVAL_COMMENT = {comment_sql},
                REJECTED_AT = NULL,
                REJECTED_BY = NULL,
                REJECTION_REASON = NULL,
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = CURRENT_USER()
            WHERE {key_column} IN ({record_keys_sql})
              AND APPROVAL_STATUS = '{PENDING_STATUS}'
        """
    else:
        sql = f"""
            UPDATE {table_name}
            SET APPROVAL_STATUS = {status_sql},
                REJECTED_AT = CURRENT_TIMESTAMP(),
                REJECTED_BY = CURRENT_USER(),
                APPROVAL_COMMENT = NULL,
                REJECTION_REASON = {comment_sql},
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = CURRENT_USER()
            WHERE {key_column} IN ({record_keys_sql})
              AND APPROVAL_STATUS = '{PENDING_STATUS}'
        """

    session.sql(sql).collect()


def set_record_status(session, record_type, record_key, status, review_comment=None):
    set_record_statuses(session, record_type, [record_key], status, review_comment)
