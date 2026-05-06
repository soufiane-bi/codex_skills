APP_DATABASE = "DEMO_DWH"
APP_SCHEMA = "STREAMLIT_APP"
MART_SCHEMA = "RETAIL_MART"
ADMIN_ROLE = "STREAMLIT_APP_ADMIN"
ACCOUNTADMIN_IS_ADMIN = True
SOURCE_APP = "STREAMLIT_WRITEBACK"
ENABLE_FOREIGN_KEY_VALIDATION = False
PENDING_STATUS = "PENDING_APPROVAL"
APPROVED_STATUS = "APPROVED"
REJECTED_STATUS = "REJECTED"

WRITEBACK_TABLES = {
    "Adjustments": f"{APP_DATABASE}.{APP_SCHEMA}.ADJUSTMENTS",
    "Forecasts": f"{APP_DATABASE}.{APP_SCHEMA}.FORECAST",
    "Promotions": f"{APP_DATABASE}.{APP_SCHEMA}.PROMOTIONS",
}

KEY_COLUMNS = {
    "Adjustments": "ADJUSTMENT_KEY",
    "Forecasts": "FORECAST_KEY",
    "Promotions": "PROMOTION_KEY",
}

REQUIRED_TABLES = {"ADJUSTMENTS", "FORECAST", "PROMOTIONS"}

EXPECTED_FIELDS = {
    "Adjustments": {
        "ADJUSTMENT_CODE",
        "ADJUSTMENT_TYPE",
        "METRIC_NAME",
        "ADJUSTMENT_METHOD",
        "ADJUSTMENT_VALUE",
        "DATE_KEY",
        "EFFECTIVE_FROM_DATE_KEY",
        "EFFECTIVE_TO_DATE_KEY",
        "PRODUCT_KEY",
        "STORE_KEY",
        "CHANNEL_KEY",
        "SKU",
        "STORE_CODE",
        "CHANNEL_CODE",
        "COUNTRY_CODE",
        "REASON_CODE",
        "COMMENT",
        "STATUS",
    },
    "Forecasts": {
        "FORECAST_CODE",
        "FORECAST_VERSION",
        "SCENARIO_NAME",
        "FORECAST_GRAIN",
        "DATE_KEY",
        "PERIOD_START_DATE_KEY",
        "PERIOD_END_DATE_KEY",
        "PRODUCT_KEY",
        "STORE_KEY",
        "CHANNEL_KEY",
        "SKU",
        "STORE_CODE",
        "CHANNEL_CODE",
        "COUNTRY_CODE",
        "FORECAST_QUANTITY",
        "FORECAST_GROSS_SALES_AMOUNT",
        "FORECAST_DISCOUNT_AMOUNT",
        "FORECAST_NET_SALES_AMOUNT",
        "FORECAST_TOTAL_COST_AMOUNT",
        "FORECAST_GROSS_MARGIN_AMOUNT",
        "MODEL_NAME",
        "CONFIDENCE_SCORE",
        "COMMENT",
        "STATUS",
    },
    "Promotions": {
        "PROMOTION_CODE",
        "PROMOTION_NAME",
        "PROMOTION_TYPE",
        "PROMOTION_MECHANIC",
        "START_DATE_KEY",
        "END_DATE_KEY",
        "PRODUCT_KEY",
        "STORE_KEY",
        "CHANNEL_KEY",
        "SKU",
        "STORE_CODE",
        "CHANNEL_CODE",
        "COUNTRY_CODE",
        "REGULAR_PRICE",
        "PROMO_PRICE",
        "DISCOUNT_AMOUNT",
        "DISCOUNT_PCT",
        "EXPECTED_UPLIFT_PCT",
        "SUPPLIER_FUNDING_AMOUNT",
        "COMMENT",
        "STATUS",
    },
}

REQUIRED_FIELDS = {
    "Adjustments": {
        "ADJUSTMENT_CODE",
        "ADJUSTMENT_TYPE",
        "METRIC_NAME",
        "ADJUSTMENT_METHOD",
        "ADJUSTMENT_VALUE",
        "DATE_KEY",
        "PRODUCT_KEY",
        "STORE_KEY",
        "CHANNEL_KEY",
        "STATUS",
    },
    "Forecasts": {
        "FORECAST_CODE",
        "FORECAST_VERSION",
        "SCENARIO_NAME",
        "FORECAST_GRAIN",
        "DATE_KEY",
        "PRODUCT_KEY",
        "STORE_KEY",
        "CHANNEL_KEY",
        "STATUS",
    },
    "Promotions": {
        "PROMOTION_CODE",
        "PROMOTION_NAME",
        "PROMOTION_TYPE",
        "PROMOTION_MECHANIC",
        "START_DATE_KEY",
        "END_DATE_KEY",
        "PRODUCT_KEY",
        "STORE_KEY",
        "CHANNEL_KEY",
        "STATUS",
    },
}

DATE_KEY_FIELDS = {
    "DATE_KEY",
    "EFFECTIVE_FROM_DATE_KEY",
    "EFFECTIVE_TO_DATE_KEY",
    "PERIOD_START_DATE_KEY",
    "PERIOD_END_DATE_KEY",
    "START_DATE_KEY",
    "END_DATE_KEY",
}
