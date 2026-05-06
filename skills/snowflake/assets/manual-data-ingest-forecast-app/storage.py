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
    FORECAST_KEY_COLUMN,
    FORECAST_TABLE_NAME,
    MART_SCHEMA,
    PENDING_STATUS,
    PROMOTION_KEY_COLUMN,
    PROMOTION_TABLE_NAME,
    REJECTED_STATUS,
    REQUIRED_TABLES,
    SOURCE_APP,
)
from validators import ValidationError, validate_forecast_payload, validate_promotion_payload


CREATE_SCHEMA_SQL = f"""
CREATE SCHEMA IF NOT EXISTS {APP_DATABASE}.{APP_SCHEMA}
    COMMENT = 'Writable Streamlit app schema for manual data ingest'
"""

CREATE_FORECAST_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {FORECAST_TABLE_NAME} (
    FORECAST_KEY NUMBER(38, 0) AUTOINCREMENT START 1 INCREMENT 1,
    FORECAST_GRAIN_KEY VARCHAR(500) NOT NULL,
    FORECAST_CODE VARCHAR(100) NOT NULL,

    DATE_KEY DATE NOT NULL,
    PERIOD_START_DATE_KEY DATE NOT NULL,
    PERIOD_END_DATE_KEY DATE NOT NULL,

    PRODUCT_KEY VARCHAR(100) NOT NULL,
    STORE_KEY VARCHAR(100) NOT NULL,
    CHANNEL_KEY VARCHAR(100) NOT NULL,

    SKU VARCHAR(100) NOT NULL,
    COUNTRY_CODE VARCHAR(20) NOT NULL,

    FORECAST_QUANTITY NUMBER(18, 4) NOT NULL,
    COMMENT VARCHAR(1000),
    STATUS VARCHAR(30) DEFAULT 'Valid',

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
    SOURCE_APP VARCHAR(100) DEFAULT '{SOURCE_APP}',

    CONSTRAINT PK_FORECAST PRIMARY KEY (FORECAST_KEY),
    CONSTRAINT UQ_FORECAST_GRAIN UNIQUE (FORECAST_GRAIN_KEY)
)
"""

CREATE_PROMOTION_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PROMOTION_TABLE_NAME} (
    PROMOTION_KEY NUMBER(38, 0) AUTOINCREMENT START 1 INCREMENT 1,
    PROMOTION_GRAIN_KEY VARCHAR(500) NOT NULL,
    PROMOTION_CODE VARCHAR(100) NOT NULL,

    DATE_KEY DATE NOT NULL,
    PERIOD_START_DATE_KEY DATE NOT NULL,
    PERIOD_END_DATE_KEY DATE NOT NULL,

    PRODUCT_KEY VARCHAR(100) NOT NULL,
    STORE_KEY VARCHAR(100) NOT NULL,
    CHANNEL_KEY VARCHAR(100) NOT NULL,

    SKU VARCHAR(100) NOT NULL,
    COUNTRY_CODE VARCHAR(20) NOT NULL,

    PROMOTION_PRICE NUMBER(18, 4) NOT NULL,
    COMMENT VARCHAR(1000),
    STATUS VARCHAR(30) DEFAULT 'Valid',

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
    SOURCE_APP VARCHAR(100) DEFAULT '{SOURCE_APP}',

    CONSTRAINT PK_PROMOTION PRIMARY KEY (PROMOTION_KEY),
    CONSTRAINT UQ_PROMOTION_GRAIN UNIQUE (PROMOTION_GRAIN_KEY)
)
"""


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
        raise PermissionError("Only a Manual Data Ingest admin can initialise storage or review submissions.")


def get_missing_tables(session):
    rows = session.sql(
        f"""
        SELECT TABLE_NAME
        FROM {APP_DATABASE}.INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{APP_SCHEMA}'
          AND TABLE_NAME IN ('FORECAST', 'PROMOTION')
        """
    ).collect()
    existing = {row["TABLE_NAME"] for row in rows}
    return sorted(REQUIRED_TABLES - existing)


def create_storage_objects(session):
    require_admin(session)
    session.sql(CREATE_SCHEMA_SQL).collect()
    session.sql(CREATE_FORECAST_TABLE_SQL).collect()
    session.sql(CREATE_PROMOTION_TABLE_SQL).collect()


def load_pending_forecasts(session):
    return session.sql(
        f"""
        SELECT *
        FROM {FORECAST_TABLE_NAME}
        WHERE APPROVAL_STATUS = '{PENDING_STATUS}'
        ORDER BY {FORECAST_KEY_COLUMN} ASC
        """
    ).to_pandas()


def load_recent_forecasts(session, limit=50):
    return session.sql(
        f"""
        SELECT *
        FROM {FORECAST_TABLE_NAME}
        ORDER BY {FORECAST_KEY_COLUMN} DESC
        LIMIT {int(limit)}
        """
    ).to_pandas()


def load_pending_promotions(session):
    return session.sql(
        f"""
        SELECT *
        FROM {PROMOTION_TABLE_NAME}
        WHERE APPROVAL_STATUS = '{PENDING_STATUS}'
        ORDER BY {PROMOTION_KEY_COLUMN} ASC
        """
    ).to_pandas()


def load_recent_promotions(session, limit=50):
    return session.sql(
        f"""
        SELECT *
        FROM {PROMOTION_TABLE_NAME}
        ORDER BY {PROMOTION_KEY_COLUMN} DESC
        LIMIT {int(limit)}
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
            checks.append((field, "DIM_DATE", "FULL_DATE", payload.get(field)))

    missing = []
    for field, table_name, column_name, value in checks:
        if value is not None and not key_exists(session, table_name, column_name, value):
            missing.append(f"{field}={value} not found in {table_name}.{column_name}")

    if missing:
        raise ValidationError("Invalid foreign key selection: " + "; ".join(missing))


def build_forecast_grain_key(payload):
    grain_parts = [
        payload.get("PERIOD_START_DATE_KEY"),
        payload.get("PERIOD_END_DATE_KEY"),
        payload.get("PRODUCT_KEY"),
        payload.get("STORE_KEY"),
        payload.get("CHANNEL_KEY"),
        payload.get("COUNTRY_CODE"),
    ]
    return "|".join(str(part).strip().upper() for part in grain_parts)


def build_promotion_grain_key(payload):
    grain_parts = [
        payload.get("PROMOTION_CODE"),
        payload.get("PERIOD_START_DATE_KEY"),
        payload.get("PERIOD_END_DATE_KEY"),
        payload.get("PRODUCT_KEY"),
        payload.get("STORE_KEY"),
        payload.get("CHANNEL_KEY"),
        payload.get("COUNTRY_CODE"),
    ]
    return "|".join(str(part).strip().upper() for part in grain_parts)


def forecast_grain_exists(session, forecast_grain_key):
    rows = session.sql(
        f"""
        SELECT COUNT(*) AS CNT
        FROM {FORECAST_TABLE_NAME}
        WHERE FORECAST_GRAIN_KEY = {sql_literal(forecast_grain_key)}
          AND APPROVAL_STATUS <> '{REJECTED_STATUS}'
        """
    ).collect()
    return rows[0]["CNT"] > 0


def promotion_grain_exists(session, promotion_grain_key):
    rows = session.sql(
        f"""
        SELECT COUNT(*) AS CNT
        FROM {PROMOTION_TABLE_NAME}
        WHERE PROMOTION_GRAIN_KEY = {sql_literal(promotion_grain_key)}
          AND APPROVAL_STATUS <> '{REJECTED_STATUS}'
        """
    ).collect()
    return rows[0]["CNT"] > 0


def submit_forecast(session, payload):
    payload = dict(payload)
    payload["FORECAST_GRAIN_KEY"] = build_forecast_grain_key(payload)

    validate_forecast_payload(payload)
    if ENABLE_FOREIGN_KEY_VALIDATION:
        validate_foreign_keys(session, payload)

    if forecast_grain_exists(session, payload["FORECAST_GRAIN_KEY"]):
        raise ValidationError(
            "A non-rejected forecast already exists for this period, product, "
            "store, channel, and country grain."
        )

    columns = list(payload.keys())
    values = [sql_literal(payload[column]) for column in columns]
    sql = f"""
        INSERT INTO {FORECAST_TABLE_NAME} ({", ".join(columns)})
        SELECT {", ".join(values)}
    """
    session.sql(sql).collect()


def submit_promotion(session, payload):
    payload = dict(payload)
    payload["PROMOTION_GRAIN_KEY"] = build_promotion_grain_key(payload)

    validate_promotion_payload(payload)
    if ENABLE_FOREIGN_KEY_VALIDATION:
        validate_foreign_keys(session, payload)

    if promotion_grain_exists(session, payload["PROMOTION_GRAIN_KEY"]):
        raise ValidationError(
            "A non-rejected promotion already exists for this promotion code, "
            "period, product, store, channel, and country grain."
        )

    columns = list(payload.keys())
    values = [sql_literal(payload[column]) for column in columns]
    sql = f"""
        INSERT INTO {PROMOTION_TABLE_NAME} ({", ".join(columns)})
        SELECT {", ".join(values)}
    """
    session.sql(sql).collect()


def set_forecast_statuses(session, forecast_keys, status, review_comment=None):
    require_admin(session)
    if status not in {APPROVED_STATUS, REJECTED_STATUS}:
        raise ValidationError("Admin action must approve or reject the submitted forecast.")

    forecast_keys = [forecast_key for forecast_key in forecast_keys if forecast_key is not None]
    if not forecast_keys:
        raise ValidationError("Select at least one pending forecast to review.")

    status_sql = sql_literal(status)
    comment_sql = sql_literal(review_comment)
    forecast_keys_sql = ", ".join(sql_literal(forecast_key) for forecast_key in forecast_keys)

    if status == APPROVED_STATUS:
        sql = f"""
            UPDATE {FORECAST_TABLE_NAME}
            SET APPROVAL_STATUS = {status_sql},
                APPROVED_AT = CURRENT_TIMESTAMP(),
                APPROVED_BY = CURRENT_USER(),
                APPROVAL_COMMENT = {comment_sql},
                REJECTED_AT = NULL,
                REJECTED_BY = NULL,
                REJECTION_REASON = NULL,
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = CURRENT_USER()
            WHERE {FORECAST_KEY_COLUMN} IN ({forecast_keys_sql})
              AND APPROVAL_STATUS = '{PENDING_STATUS}'
        """
    else:
        sql = f"""
            UPDATE {FORECAST_TABLE_NAME}
            SET APPROVAL_STATUS = {status_sql},
                REJECTED_AT = CURRENT_TIMESTAMP(),
                REJECTED_BY = CURRENT_USER(),
                APPROVAL_COMMENT = NULL,
                REJECTION_REASON = {comment_sql},
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = CURRENT_USER()
            WHERE {FORECAST_KEY_COLUMN} IN ({forecast_keys_sql})
              AND APPROVAL_STATUS = '{PENDING_STATUS}'
        """

    session.sql(sql).collect()


def set_forecast_status(session, forecast_key, status, review_comment=None):
    set_forecast_statuses(session, [forecast_key], status, review_comment)


def set_promotion_statuses(session, promotion_keys, status, review_comment=None):
    require_admin(session)
    if status not in {APPROVED_STATUS, REJECTED_STATUS}:
        raise ValidationError("Admin action must approve or reject the submitted promotion.")

    promotion_keys = [promotion_key for promotion_key in promotion_keys if promotion_key is not None]
    if not promotion_keys:
        raise ValidationError("Select at least one pending promotion to review.")

    status_sql = sql_literal(status)
    comment_sql = sql_literal(review_comment)
    promotion_keys_sql = ", ".join(sql_literal(promotion_key) for promotion_key in promotion_keys)

    if status == APPROVED_STATUS:
        sql = f"""
            UPDATE {PROMOTION_TABLE_NAME}
            SET APPROVAL_STATUS = {status_sql},
                APPROVED_AT = CURRENT_TIMESTAMP(),
                APPROVED_BY = CURRENT_USER(),
                APPROVAL_COMMENT = {comment_sql},
                REJECTED_AT = NULL,
                REJECTED_BY = NULL,
                REJECTION_REASON = NULL,
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = CURRENT_USER()
            WHERE {PROMOTION_KEY_COLUMN} IN ({promotion_keys_sql})
              AND APPROVAL_STATUS = '{PENDING_STATUS}'
        """
    else:
        sql = f"""
            UPDATE {PROMOTION_TABLE_NAME}
            SET APPROVAL_STATUS = {status_sql},
                REJECTED_AT = CURRENT_TIMESTAMP(),
                REJECTED_BY = CURRENT_USER(),
                APPROVAL_COMMENT = NULL,
                REJECTION_REASON = {comment_sql},
                UPDATED_AT = CURRENT_TIMESTAMP(),
                UPDATED_BY = CURRENT_USER()
            WHERE {PROMOTION_KEY_COLUMN} IN ({promotion_keys_sql})
              AND APPROVAL_STATUS = '{PENDING_STATUS}'
        """

    session.sql(sql).collect()


def set_promotion_status(session, promotion_key, status, review_comment=None):
    set_promotion_statuses(session, [promotion_key], status, review_comment)
