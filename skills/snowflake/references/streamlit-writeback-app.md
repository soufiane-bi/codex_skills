# Snowflake Streamlit Writeback Apps

Use this reference when building a Streamlit-in-Snowflake app that writes controlled business inputs back to Snowflake tables, especially planning apps for adjustments, forecasts, promotions, scenarios, or app-managed overrides.

## Core Design

Prefer a controlled app over free-form table appends:

- Use business tabs such as `Adjustments`, `Forecasts`, and `Promotions`.
- Map each tab internally to an approved fully-qualified table name.
- Never expose raw table-name input to users.
- Validate fields before insert and raise a clear error when a payload contains fields for the wrong record type.
- Submit normal-user changes as `PENDING_APPROVAL`; only `STREAMLIT_APP_ADMIN` users should approve or reject records.
- Keep foreign-key validation optional. Dropdowns normally prevent wrong keys, and per-submit FK checks add extra Snowflake queries. Enable them only when the user wants stronger protection.
- Keep Snowflake helper-script exploration read-only; generate or edit writeback code, but do not execute DDL/DML unless the user explicitly asks and the active role is appropriate.

## Requirements Discovery

Before finalizing the app fields, ask the user for the best available example of the intended input shape:

1. Prefer a CSV or Excel extract with 1-5 representative rows.
2. Accept a screenshot/image of an Excel sheet when the user cannot share a file; use it to infer column names, ordering, and rough field types, then confirm any unclear fields.
3. If the user has no sample, ask them to describe the fields manually in chat.

Keep the questions short and practical:

- What is the business object being entered, for example forecast, promotion, or adjustment?
- What columns should users fill in?
- Which columns should come from Snowflake dropdowns or lookups?
- Which fields are required?
- Should submissions go straight to approved, or stay pending until an admin approves them?

If no sample is provided, start from the recommended fields below and tell the user they are a sensible default rather than a final contract.

## First-Run Storage Flow

On app startup:

1. Check whether all required writeback tables exist.
2. If all exist, load dimension lookups and show append forms.
3. If tables are missing and the user has `STREAMLIT_APP_ADMIN`, show an `Initialise storage tables` button.
4. If tables are missing and the user is not an admin, show a blocking error asking them to contact an app admin.
5. For every user submission, write `STATUS = 'PENDING_APPROVAL'`. Show approval/rejection actions only to admins.

Admin check pattern:

```python
def is_app_admin(session):
    value = session.sql("""
        SELECT
            IS_ROLE_IN_SESSION('STREAMLIT_APP_ADMIN')
            OR CURRENT_ROLE() = 'ACCOUNTADMIN'
    """).collect()[0][0]

    return bool(value)
```

`ACCOUNTADMIN` is acceptable as a temporary trial-account fallback. Prefer `STREAMLIT_APP_ADMIN` for real use.

## Role Setup

Generate setup SQL like this when the user asks for role/admin setup:

```sql
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS STREAMLIT_APP_ADMIN
    COMMENT = 'Admin role for Streamlit writeback app setup and storage initialisation';

CREATE ROLE IF NOT EXISTS STREAMLIT_APP_USER
    COMMENT = 'Standard role for Streamlit writeback app users';

GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE STREAMLIT_APP_ADMIN;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE STREAMLIT_APP_USER;

GRANT USAGE ON DATABASE DEMO_DWH TO ROLE STREAMLIT_APP_ADMIN;
GRANT USAGE ON DATABASE DEMO_DWH TO ROLE STREAMLIT_APP_USER;

GRANT USAGE ON SCHEMA DEMO_DWH.RETAIL_MART TO ROLE STREAMLIT_APP_ADMIN;
GRANT USAGE ON SCHEMA DEMO_DWH.RETAIL_MART TO ROLE STREAMLIT_APP_USER;

GRANT SELECT ON ALL TABLES IN SCHEMA DEMO_DWH.RETAIL_MART TO ROLE STREAMLIT_APP_ADMIN;
GRANT SELECT ON ALL TABLES IN SCHEMA DEMO_DWH.RETAIL_MART TO ROLE STREAMLIT_APP_USER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DEMO_DWH.RETAIL_MART TO ROLE STREAMLIT_APP_ADMIN;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DEMO_DWH.RETAIL_MART TO ROLE STREAMLIT_APP_USER;

GRANT CREATE SCHEMA ON DATABASE DEMO_DWH TO ROLE STREAMLIT_APP_ADMIN;
```

After storage objects exist, grant app users only the minimum table privileges they need, usually `SELECT, INSERT` on writeback tables and `SELECT` on dimension tables.

## Retail Mart Key Alignment

Always inspect the target mart before finalizing the app. For the demo retail mart used in examples, align to these keys:

- `DATE_KEY` from `RETAIL_MART.DIM_DATE`
- `PRODUCT_KEY` from `RETAIL_MART.DIM_PRODUCT`
- `STORE_KEY` from `RETAIL_MART.DIM_STORE`
- `CHANNEL_KEY` from `RETAIL_MART.DIM_CHANNEL`

Useful display columns:

- Product: `SKU`, `PRODUCT_NAME`, `BRAND_NAME`, `CATEGORY_L1`, `CATEGORY_L2`
- Store: `STORE_CODE`, `STORE_NAME`, `COUNTRY_CODE`, `REGION_NAME`
- Channel: `CHANNEL_CODE`, `CHANNEL_NAME`
- Date: `FULL_DATE`

## Optional Foreign Key Validation

By default, rely on dropdown selectors loaded from dimension tables. This keeps app usage cheap and responsive. If the user explicitly wants stronger protection, enable a submit-time FK check for:

- Date fields: `DATE_KEY`, `EFFECTIVE_FROM_DATE_KEY`, `EFFECTIVE_TO_DATE_KEY`, `PERIOD_START_DATE_KEY`, `PERIOD_END_DATE_KEY`, `START_DATE_KEY`, `END_DATE_KEY` in `DIM_DATE.DATE_KEY`.
- `PRODUCT_KEY` in `DIM_PRODUCT.PRODUCT_KEY`.
- `STORE_KEY` in `DIM_STORE.STORE_KEY`.
- `CHANNEL_KEY` in `DIM_CHANNEL.CHANNEL_KEY`.

Show a specific error such as `Invalid foreign key selection: PRODUCT_KEY=12345 not found in DIM_PRODUCT.PRODUCT_KEY`.

## Approval Workflow

Normal users should append records only as `PENDING_APPROVAL`. Admins should have a review tab that can approve or reject pending records and enter an approval or rejection comment. Use audit columns such as `SUBMITTED_AT`, `SUBMITTED_BY`, `APPROVED_AT`, `APPROVED_BY`, `APPROVAL_COMMENT`, `REJECTED_AT`, `REJECTED_BY`, and `REJECTION_REASON`. Downstream marts should usually consume only `STATUS = 'APPROVED'` records.

## Recommended User Fields

Keep user-entered fields lean and derive keys from selectors.

Adjustments:

- `METRIC_NAME`
- `ADJUSTMENT_TYPE`
- `ADJUSTMENT_METHOD`
- `ADJUSTMENT_VALUE`
- `DATE_KEY`, `EFFECTIVE_FROM_DATE_KEY`, `EFFECTIVE_TO_DATE_KEY`
- `PRODUCT_KEY`, `STORE_KEY`, `CHANNEL_KEY`
- `REASON_CODE`
- `COMMENT`
- `STATUS`

Forecasts:

- `FORECAST_VERSION`
- `SCENARIO_NAME`
- `FORECAST_GRAIN`
- `DATE_KEY`, `PERIOD_START_DATE_KEY`, `PERIOD_END_DATE_KEY`
- `PRODUCT_KEY`, `STORE_KEY`, `CHANNEL_KEY`
- `FORECAST_QUANTITY`
- `FORECAST_GROSS_SALES_AMOUNT`
- `FORECAST_DISCOUNT_AMOUNT`
- `FORECAST_NET_SALES_AMOUNT`
- `FORECAST_TOTAL_COST_AMOUNT`
- `FORECAST_GROSS_MARGIN_AMOUNT`
- `COMMENT`
- `STATUS`

Promotions:

- `PROMOTION_NAME`
- `PROMOTION_TYPE`
- `PROMOTION_MECHANIC`
- `START_DATE_KEY`, `END_DATE_KEY`
- `PRODUCT_KEY`, `STORE_KEY`, `CHANNEL_KEY`
- `REGULAR_PRICE`
- `PROMO_PRICE`
- `DISCOUNT_AMOUNT`
- `DISCOUNT_PCT`
- `EXPECTED_UPLIFT_PCT`
- `SUPPLIER_FUNDING_AMOUNT`
- `COMMENT`
- `STATUS`

System fields should be automatic: `CREATED_AT`, `CREATED_BY`, `UPDATED_AT`, `UPDATED_BY`, `SOURCE_APP`.

## Template Asset

A reusable starter template lives in `assets/streamlit-writeback-app/`:

- `streamlit_app.py` - tabs, forms, admin first-run flow, record previews
- `storage.py` - DDL, existence checks, dimension loads, safe mapped inserts
- `validators.py` - record-type field validation and friendly errors
- `config.py` - database/schema/table config and expected field mapping

A focused forecast-only project lives in `assets/manual-data-ingest-forecast-app/`. Use it when the user wants a single Snowflake Streamlit app called Manual Data Ingest with only forecast submissions and admin approval.

When using the template:

1. Copy the asset folder into the target project.
2. Inspect the target Snowflake mart metadata with the read-only helper scripts.
3. Update `config.py` for database, schemas, role names, and table names.
4. Update `storage.py` DDL if the target writeback fields differ.
5. Run local syntax checks, then test in Snowflake Streamlit.
