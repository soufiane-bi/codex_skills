APP_NAME = "Stock Adjustment Ingest"
APP_DATABASE = "DEMO_DWH"
APP_SCHEMA = "STREAMLIT_APP"
MART_SCHEMA = "RETAIL_MART"
ADMIN_ROLE = "STREAMLIT_APP_ADMIN"
USER_ROLE = "STREAMLIT_APP_USER"
ACCOUNTADMIN_IS_ADMIN = True
SOURCE_APP = "STOCK_ADJUSTMENT_INGEST"
ENABLE_FOREIGN_KEY_VALIDATION = False
UPLOAD_MAX_ROWS = 10000

PENDING_STATUS = "PENDING_APPROVAL"
APPROVED_STATUS = "APPROVED"
REJECTED_STATUS = "REJECTED"

# Stock adjustment upload fields matched to the agreed source sheet.
RECORD_TYPES = {
    "Stock Adjustments": {
        "table_name": f"{APP_DATABASE}.{APP_SCHEMA}.STOCK_ADJUSTMENTS",
        "physical_table_name": "STOCK_ADJUSTMENTS",
        "key_column": "STOCK_ADJUSTMENT_KEY",
        "system_fields": {"UPLOAD_BATCH_ID", "UPLOAD_FILE_NAME", "UPLOAD_ROW_NUMBER"},
        "fields": [
            {
                "name": "ADJUSTMENT_CODE",
                "label": "adjustment_code",
                "type": "text",
                "required": True,
                "default": "",
                "aliases": ["adjustment_code", "adjustment code", "adjustmentcode"],
            },
            {
                "name": "DATE",
                "label": "date",
                "type": "date",
                "required": True,
                "aliases": ["date", "adjustment_date", "adjustment date"],
            },
            {
                "name": "PRODUCT",
                "label": "product",
                "type": "text",
                "required": True,
                "default": "",
                "aliases": ["product", "product_code", "product code", "sku"],
            },
            {
                "name": "STORE",
                "label": "store",
                "type": "text",
                "required": True,
                "default": "",
                "aliases": ["store", "store_code", "store code"],
            },
            {
                "name": "CHANNEL",
                "label": "channel",
                "type": "select",
                "required": True,
                "options": ["retail", "online"],
                "default": "retail",
                "aliases": ["channel", "sales_channel", "sales channel"],
            },
            {
                "name": "COUNTRY",
                "label": "country",
                "type": "select",
                "required": True,
                "options": ["UK", "IE", "NL"],
                "default": "UK",
                "aliases": ["country", "country_code", "country code"],
            },
            {
                "name": "ADJUSTED_QTY",
                "label": "adjusted_qty",
                "type": "number",
                "required": True,
                "default": 0.0,
                "step": 1.0,
                "aliases": ["adjusted_qty", "adjusted qty", "adjusted_quantity", "adjusted quantity"],
            },
            {
                "name": "COMMENTS",
                "label": "comments",
                "type": "textarea",
                "required": False,
                "default": "",
                "aliases": ["comments", "comment", "notes"],
            },
        ],
        "ddl_columns": [
            "STOCK_ADJUSTMENT_KEY NUMBER(38, 0) AUTOINCREMENT START 1 INCREMENT 1",
            "UPLOAD_BATCH_ID VARCHAR(36)",
            "UPLOAD_FILE_NAME VARCHAR(500)",
            "UPLOAD_ROW_NUMBER NUMBER(38, 0)",
            "ADJUSTMENT_CODE VARCHAR(100) NOT NULL",
            "DATE DATE NOT NULL",
            "PRODUCT VARCHAR(100) NOT NULL",
            "STORE VARCHAR(100) NOT NULL",
            "CHANNEL VARCHAR(30) NOT NULL",
            "COUNTRY VARCHAR(20) NOT NULL",
            "ADJUSTED_QTY NUMBER(18, 4) NOT NULL",
            "COMMENTS VARCHAR(1000)",
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
    record_type: {field["name"] for field in config["fields"]} | set(config.get("system_fields", set()))
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

# Optional submit-time FK checks. Keep empty because the upload contract only
# defines flat file columns, not Snowflake lookup tables.
# Example:
# FOREIGN_KEY_CHECKS = {
#     "PRODUCT": {"table": "DIM_PRODUCTS", "column": "PRODUCT"},
#     "STORE": {"table": "DIM_STORES", "column": "STORE"},
# }
FOREIGN_KEY_CHECKS = {}
