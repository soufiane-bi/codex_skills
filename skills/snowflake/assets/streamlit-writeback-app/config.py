# Replace these placeholders with app-specific values before deploying.
APP_NAME = "YOUR_STREAMLIT_APP_NAME"
APP_DATABASE = "YOUR_APP_DATABASE"
APP_SCHEMA = "YOUR_APP_WRITEBACK_SCHEMA"
MART_SCHEMA = "YOUR_SOURCE_SCHEMA"
ADMIN_ROLE = "YOUR_APP_ADMIN_ROLE"
USER_ROLE = "YOUR_APP_USER_ROLE"
ACCOUNTADMIN_IS_ADMIN = True
SOURCE_APP = "YOUR_APP_CODE"
ENABLE_FOREIGN_KEY_VALIDATION = False

PENDING_STATUS = "PENDING_APPROVAL"
APPROVED_STATUS = "APPROVED"
REJECTED_STATUS = "REJECTED"

# Start with one neutral record type. Replace it with the app's real tabs,
# fields, DDL columns, and table names during app generation.
RECORD_TYPES = {
    "Records": {
        "table_name": f"{APP_DATABASE}.{APP_SCHEMA}.YOUR_WRITEBACK_TABLE",
        "physical_table_name": "YOUR_WRITEBACK_TABLE",
        "key_column": "RECORD_KEY",
        "fields": [
            {
                "name": "RECORD_CODE",
                "label": "Record code",
                "type": "text",
                "required": True,
                "default": "",
            },
            {
                "name": "EFFECTIVE_DATE",
                "label": "Effective date",
                "type": "date",
                "required": True,
            },
            {
                "name": "RECORD_VALUE",
                "label": "Record value",
                "type": "number",
                "required": False,
                "default": 0.0,
                "step": 1.0,
            },
            {
                "name": "BUSINESS_STATUS",
                "label": "Business status",
                "type": "select",
                "required": True,
                "options": ["Valid", "Invalid"],
                "default": "Valid",
            },
            {
                "name": "COMMENT",
                "label": "Comment",
                "type": "textarea",
                "required": False,
                "default": "",
            },
        ],
        "ddl_columns": [
            "RECORD_KEY NUMBER(38, 0) AUTOINCREMENT START 1 INCREMENT 1",
            "RECORD_CODE VARCHAR(100) NOT NULL",
            "EFFECTIVE_DATE DATE NOT NULL",
            "RECORD_VALUE NUMBER(18, 4)",
            "BUSINESS_STATUS VARCHAR(30) DEFAULT 'Valid'",
            "COMMENT VARCHAR(1000)",
        ],
    }
}

WRITEBACK_TABLES = {
    record_type: config["table_name"]
    for record_type, config in RECORD_TYPES.items()
}

KEY_COLUMNS = {
    record_type: config["key_column"]
    for record_type, config in RECORD_TYPES.items()
}

REQUIRED_TABLES = {
    config["physical_table_name"]
    for config in RECORD_TYPES.values()
}

EXPECTED_FIELDS = {
    record_type: {field["name"] for field in config["fields"]}
    for record_type, config in RECORD_TYPES.items()
}

REQUIRED_FIELDS = {
    record_type: {
        field["name"]
        for field in config["fields"]
        if field.get("required", False)
    }
    for record_type, config in RECORD_TYPES.items()
}

# Optional submit-time FK checks. Keep empty by default to avoid unnecessary
# Snowflake queries. Example:
# FOREIGN_KEY_CHECKS = {
#     "YOUR_LOOKUP_KEY": {"table": "YOUR_DIMENSION_TABLE", "column": "YOUR_LOOKUP_KEY"},
# }
FOREIGN_KEY_CHECKS = {}
