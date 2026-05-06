# Snowflake Streamlit Writeback Apps

Use this reference when building a Streamlit-in-Snowflake app that writes controlled business inputs back to Snowflake tables, especially planning apps for adjustments, forecasts, promotions, scenarios, or app-managed overrides.

## Core Design

Prefer a controlled app over free-form table appends:

- Use business tabs such as `Adjustments`, `Forecasts`, and `Promotions`.
- Map each tab internally to an approved fully-qualified table name.
- Never expose raw table-name input to users.
- Validate fields before insert and raise a clear error when a payload contains fields for the wrong record type.
- Submit normal-user changes as `PENDING_APPROVAL`; only users with the app-specific admin role should approve or reject records.
- Keep foreign-key validation optional. Dropdowns normally prevent wrong keys, and per-submit FK checks add extra Snowflake queries. Enable them only when the user wants stronger protection.
- Keep Snowflake helper-script exploration read-only; generate or edit writeback code, but do not execute DDL/DML unless the user explicitly asks and the active role is appropriate.

## App Scope Discovery

Before generating app code or setup SQL, ask for the app's Snowflake scope:

- App name and short app code, for example `Forecast Planner` and `FORECAST_PLANNER`.
- Target database for the app and writeback tables.
- Source schema(s) to read from, for example marts or dimensions used for dropdowns.
- Writeback schema to create or use.
- Warehouse the app should run on.
- Admin role and standard user role.
- Snowflake users, groups, or existing roles that should receive admin or user access.

If the user is unsure, propose app-specific names rather than shared generic ones:

- Writeback schema: `<APP_CODE>_APP`, for example `FORECAST_PLANNER_APP`.
- Admin role: `<APP_CODE>_ADMIN`, for example `FORECAST_PLANNER_ADMIN`.
- User role: `<APP_CODE>_USER`, for example `FORECAST_PLANNER_USER`.

Use a shared app schema or shared app roles only when the user explicitly asks for that operating model. The safer default is one schema and two roles per app so access, ownership, and future cleanup are isolated.

## Requirements Discovery

Requirement discovery is a hard gate before finalizing app fields, table DDL, validators, or forms. Ask the user for the best available example of the intended input shape:

1. Prefer a CSV or Excel extract with 1-5 representative rows.
2. Accept a screenshot/image of an Excel sheet when the user cannot share a file; use it to infer column names, ordering, and rough field types, then confirm any unclear fields.
3. If the user has no sample, ask them to describe the fields manually in chat before choosing defaults.

Keep the questions short and practical:

- What is the business object being entered, for example forecast, promotion, or adjustment?
- What columns should users fill in?
- Which columns should come from Snowflake dropdowns or lookups?
- Which fields are required?
- Should submissions go straight to approved, or stay pending until an admin approves them?

Only use the recommended fields below after confirming the user wants to proceed without a sample. Tell the user they are provisional defaults rather than a final contract.

## First-Run Storage Flow

On app startup:

1. Check whether all required writeback tables exist.
2. If all exist, load dimension lookups and show append forms.
3. If tables are missing and the user has the app-specific admin role, show an `Initialise storage tables` button.
4. If tables are missing and the user is not an admin, show a blocking error asking them to contact an app admin.
5. For every user submission, write `STATUS = 'PENDING_APPROVAL'`. Show approval/rejection actions only to admins.

Admin check pattern:

```python
from config import ACCOUNTADMIN_IS_ADMIN, ADMIN_ROLE


def is_app_admin(session):
    accountadmin_clause = "OR CURRENT_ROLE() = 'ACCOUNTADMIN'" if ACCOUNTADMIN_IS_ADMIN else ""
    value = session.sql(f"""
        SELECT
            IS_ROLE_IN_SESSION('{ADMIN_ROLE}')
            {accountadmin_clause}
    """).collect()[0][0]

    return bool(value)
```

`ACCOUNTADMIN` is acceptable as a temporary trial-account fallback. Prefer the app-specific admin role for real use.

## Role Setup

Generate setup SQL like this when the user asks for role/admin setup:

```sql
-- Replace placeholders with the app-specific values agreed during scope discovery.
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS <APP_ADMIN_ROLE>
    COMMENT = 'Admin role for <APP_NAME> Streamlit writeback app setup and storage initialisation';

CREATE ROLE IF NOT EXISTS <APP_USER_ROLE>
    COMMENT = 'Standard role for <APP_NAME> Streamlit writeback app users';

CREATE SCHEMA IF NOT EXISTS <APP_DATABASE>.<APP_SCHEMA>
    COMMENT = 'Writeback schema for <APP_NAME>';

GRANT USAGE ON WAREHOUSE <APP_WAREHOUSE> TO ROLE <APP_ADMIN_ROLE>;
GRANT USAGE ON WAREHOUSE <APP_WAREHOUSE> TO ROLE <APP_USER_ROLE>;

GRANT USAGE ON DATABASE <APP_DATABASE> TO ROLE <APP_ADMIN_ROLE>;
GRANT USAGE ON DATABASE <APP_DATABASE> TO ROLE <APP_USER_ROLE>;

GRANT USAGE ON SCHEMA <APP_DATABASE>.<APP_SCHEMA> TO ROLE <APP_ADMIN_ROLE>;
GRANT USAGE ON SCHEMA <APP_DATABASE>.<APP_SCHEMA> TO ROLE <APP_USER_ROLE>;
GRANT CREATE TABLE ON SCHEMA <APP_DATABASE>.<APP_SCHEMA> TO ROLE <APP_ADMIN_ROLE>;
GRANT CREATE STAGE ON SCHEMA <APP_DATABASE>.<APP_SCHEMA> TO ROLE <APP_ADMIN_ROLE>;
GRANT CREATE STREAMLIT ON SCHEMA <APP_DATABASE>.<APP_SCHEMA> TO ROLE <APP_ADMIN_ROLE>;

GRANT USAGE ON SCHEMA <APP_DATABASE>.<SOURCE_SCHEMA> TO ROLE <APP_ADMIN_ROLE>;
GRANT USAGE ON SCHEMA <APP_DATABASE>.<SOURCE_SCHEMA> TO ROLE <APP_USER_ROLE>;
GRANT SELECT ON ALL TABLES IN SCHEMA <APP_DATABASE>.<SOURCE_SCHEMA> TO ROLE <APP_ADMIN_ROLE>;
GRANT SELECT ON ALL TABLES IN SCHEMA <APP_DATABASE>.<SOURCE_SCHEMA> TO ROLE <APP_USER_ROLE>;
GRANT SELECT ON FUTURE TABLES IN SCHEMA <APP_DATABASE>.<SOURCE_SCHEMA> TO ROLE <APP_ADMIN_ROLE>;
GRANT SELECT ON FUTURE TABLES IN SCHEMA <APP_DATABASE>.<SOURCE_SCHEMA> TO ROLE <APP_USER_ROLE>;
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

Concrete customer or account-specific apps should live outside the shared skill assets, for example in a private repo or an ignored local workspace such as `.local/streamlit-apps/<app-name>/`. Keep only reusable, sanitized templates in this skill.

When using the template:

1. Copy the asset folder into the target project.
2. Inspect the target Snowflake mart metadata with the read-only helper scripts.
3. Update `config.py` for database, schemas, role names, and table names.
4. Update `storage.py` DDL if the target writeback fields differ.
5. Run local syntax checks, then test in Snowflake Streamlit.
