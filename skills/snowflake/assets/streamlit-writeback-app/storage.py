from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from config import (
    ACCOUNTADMIN_IS_ADMIN,
    ADMIN_ROLE,
    APP_DATABASE,
    APP_SCHEMA,
    APPROVED_STATUS,
    DATE_KEY_FIELDS,
    ENABLE_FOREIGN_KEY_VALIDATION,
    KEY_COLUMNS,
    MART_SCHEMA,
    PENDING_STATUS,
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

CREATE_TABLE_SQL = [
    f"""
    CREATE TABLE IF NOT EXISTS {APP_DATABASE}.{APP_SCHEMA}.ADJUSTMENTS (
        ADJUSTMENT_KEY NUMBER(38, 0) AUTOINCREMENT START 1 INCREMENT 1,
        ADJUSTMENT_CODE VARCHAR(100) NOT NULL,
        ADJUSTMENT_TYPE VARCHAR(50) NOT NULL,
        METRIC_NAME VARCHAR(100) NOT NULL,
        ADJUSTMENT_METHOD VARCHAR(30) NOT NULL,
        ADJUSTMENT_VALUE NUMBER(18, 4) NOT NULL,
        DATE_KEY NUMBER(38, 0) NOT NULL,
        EFFECTIVE_FROM_DATE_KEY NUMBER(38, 0),
        EFFECTIVE_TO_DATE_KEY NUMBER(38, 0),
        PRODUCT_KEY NUMBER(38, 0),
        STORE_KEY NUMBER(38, 0),
        CHANNEL_KEY NUMBER(38, 0),
        SKU VARCHAR(100),
        STORE_CODE VARCHAR(100),
        CHANNEL_CODE VARCHAR(100),
        COUNTRY_CODE VARCHAR(20),
        REASON_CODE VARCHAR(100),
        COMMENT VARCHAR(1000),
        STATUS VARCHAR(30) DEFAULT '{PENDING_STATUS}',
{COMMON_APPROVAL_COLUMNS},
        CONSTRAINT PK_ADJUSTMENTS PRIMARY KEY (ADJUSTMENT_KEY)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {APP_DATABASE}.{APP_SCHEMA}.FORECAST (
        FORECAST_KEY NUMBER(38, 0) AUTOINCREMENT START 1 INCREMENT 1,
        FORECAST_CODE VARCHAR(100) NOT NULL,
        FORECAST_VERSION VARCHAR(100) NOT NULL,
        SCENARIO_NAME VARCHAR(100) NOT NULL,
        FORECAST_GRAIN VARCHAR(20) NOT NULL,
        DATE_KEY NUMBER(38, 0) NOT NULL,
        PERIOD_START_DATE_KEY NUMBER(38, 0),
        PERIOD_END_DATE_KEY NUMBER(38, 0),
        PRODUCT_KEY NUMBER(38, 0),
        STORE_KEY NUMBER(38, 0),
        CHANNEL_KEY NUMBER(38, 0),
        SKU VARCHAR(100),
        STORE_CODE VARCHAR(100),
        CHANNEL_CODE VARCHAR(100),
        COUNTRY_CODE VARCHAR(20),
        FORECAST_QUANTITY NUMBER(18, 4),
        FORECAST_GROSS_SALES_AMOUNT NUMBER(18, 4),
        FORECAST_DISCOUNT_AMOUNT NUMBER(18, 4),
        FORECAST_NET_SALES_AMOUNT NUMBER(18, 4),
        FORECAST_TOTAL_COST_AMOUNT NUMBER(18, 4),
        FORECAST_GROSS_MARGIN_AMOUNT NUMBER(18, 4),
        MODEL_NAME VARCHAR(200),
        CONFIDENCE_SCORE NUMBER(8, 4),
        COMMENT VARCHAR(1000),
        STATUS VARCHAR(30) DEFAULT '{PENDING_STATUS}',
{COMMON_APPROVAL_COLUMNS},
        CONSTRAINT PK_FORECAST PRIMARY KEY (FORECAST_KEY)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {APP_DATABASE}.{APP_SCHEMA}.PROMOTIONS (
        PROMOTION_KEY NUMBER(38, 0) AUTOINCREMENT START 1 INCREMENT 1,
        PROMOTION_CODE VARCHAR(100) NOT NULL,
        PROMOTION_NAME VARCHAR(300) NOT NULL,
        PROMOTION_TYPE VARCHAR(100),
        PROMOTION_MECHANIC VARCHAR(100),
        START_DATE_KEY NUMBER(38, 0) NOT NULL,
        END_DATE_KEY NUMBER(38, 0) NOT NULL,
        PRODUCT_KEY NUMBER(38, 0),
        STORE_KEY NUMBER(38, 0),
        CHANNEL_KEY NUMBER(38, 0),
        SKU VARCHAR(100),
        STORE_CODE VARCHAR(100),
        CHANNEL_CODE VARCHAR(100),
        COUNTRY_CODE VARCHAR(20),
        REGULAR_PRICE NUMBER(18, 4),
        PROMO_PRICE NUMBER(18, 4),
        DISCOUNT_AMOUNT NUMBER(18, 4),
        DISCOUNT_PCT NUMBER(8, 4),
        EXPECTED_UPLIFT_PCT NUMBER(8, 4),
        SUPPLIER_FUNDING_AMOUNT NUMBER(18, 4),
        COMMENT VARCHAR(1000),
        STATUS VARCHAR(30) DEFAULT '{PENDING_STATUS}',
{COMMON_APPROVAL_COLUMNS},
        CONSTRAINT PK_PROMOTIONS PRIMARY KEY (PROMOTION_KEY)
    )
    """,
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
    rows = session.sql(
        f"""
        SELECT TABLE_NAME
        FROM {APP_DATABASE}.INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{APP_SCHEMA}'
          AND TABLE_NAME IN ('ADJUSTMENTS', 'FORECAST', 'PROMOTIONS')
        """
    ).collect()
    existing = {row["TABLE_NAME"] for row in rows}
    return sorted(REQUIRED_TABLES - existing)


def create_storage_objects(session):
    require_admin(session)
    session.sql(CREATE_SCHEMA_SQL).collect()
    for statement in CREATE_TABLE_SQL:
        session.sql(statement).collect()


def load_products(session):
    return session.sql(
        f"""
        SELECT
            PRODUCT_KEY,
            SKU,
            PRODUCT_NAME,
            BRAND_NAME,
            CATEGORY_L1,
            CATEGORY_L2
        FROM {APP_DATABASE}.{MART_SCHEMA}.DIM_PRODUCT
        ORDER BY SKU
        """
    ).to_pandas()


def load_stores(session):
    return session.sql(
        f"""
        SELECT
            STORE_KEY,
            STORE_CODE,
            STORE_NAME,
            COUNTRY_CODE,
            REGION_NAME
        FROM {APP_DATABASE}.{MART_SCHEMA}.DIM_STORE
        ORDER BY STORE_CODE
        """
    ).to_pandas()


def load_channels(session):
    return session.sql(
        f"""
        SELECT
            CHANNEL_KEY,
            CHANNEL_CODE,
            CHANNEL_NAME
        FROM {APP_DATABASE}.{MART_SCHEMA}.DIM_CHANNEL
        ORDER BY CHANNEL_KEY
        """
    ).to_pandas()


def load_dates(session):
    return session.sql(
        f"""
        SELECT
            DATE_KEY,
            FULL_DATE
        FROM {APP_DATABASE}.{MART_SCHEMA}.DIM_DATE
        ORDER BY FULL_DATE DESC
        """
    ).to_pandas()


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
        WHERE STATUS = '{PENDING_STATUS}'
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
    checks = []
    for field in DATE_KEY_FIELDS:
        if field in payload:
            checks.append((field, "DIM_DATE", "DATE_KEY", payload.get(field)))
    for field, table_name, column_name in [
        ("PRODUCT_KEY", "DIM_PRODUCT", "PRODUCT_KEY"),
        ("STORE_KEY", "DIM_STORE", "STORE_KEY"),
        ("CHANNEL_KEY", "DIM_CHANNEL", "CHANNEL_KEY"),
    ]:
        if field in payload:
            checks.append((field, table_name, column_name, payload.get(field)))

    missing = []
    for field, table_name, column_name, value in checks:
        if value is not None and not key_exists(session, table_name, column_name, value):
            missing.append(f"{field}={value} not found in {table_name}.{column_name}")

    if missing:
        raise ValidationError("Invalid foreign key selection: " + "; ".join(missing))


def insert_record(session, record_type, payload):
    validate_record(record_type, payload)
    if ENABLE_FOREIGN_KEY_VALIDATION:
        validate_foreign_keys(session, payload)

    payload = dict(payload)
    payload["STATUS"] = PENDING_STATUS

    table_name = WRITEBACK_TABLES[record_type]
    columns = list(payload.keys())
    values = [sql_literal(payload[column]) for column in columns]

    sql = f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        SELECT {", ".join(values)}
    """
    session.sql(sql).collect()


def set_record_status(session, record_type, record_key, status, review_comment=None):
    require_admin(session)
    if status not in {APPROVED_STATUS, REJECTED_STATUS}:
        raise ValidationError("Admin action must approve or reject the submitted record.")

    table_name = WRITEBACK_TABLES[record_type]
    key_column = KEY_COLUMNS[record_type]
    status_sql = sql_literal(status)
    comment_sql = sql_literal(review_comment)

    if status == APPROVED_STATUS:
        sql = f"""
            UPDATE {table_name}
            SET STATUS = {status_sql},
                APPROVED_AT = CURRENT_TIMESTAMP(),
                APPROVED_BY = CURRENT_USER(),
                APPROVAL_COMMENT = {comment_sql},
                REJECTED_AT = NULL,
                REJECTED_BY = NULL,
                REJECTION_REASON = NULL,
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = CURRENT_USER()
            WHERE {key_column} = {sql_literal(record_key)}
              AND STATUS = '{PENDING_STATUS}'
        """
    else:
        sql = f"""
            UPDATE {table_name}
            SET STATUS = {status_sql},
                REJECTED_AT = CURRENT_TIMESTAMP(),
                REJECTED_BY = CURRENT_USER(),
                APPROVAL_COMMENT = NULL,
                REJECTION_REASON = {comment_sql},
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = CURRENT_USER()
            WHERE {key_column} = {sql_literal(record_key)}
              AND STATUS = '{PENDING_STATUS}'
        """

    session.sql(sql).collect()
