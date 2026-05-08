# Stock Adjustment Ingest

Snowflake Streamlit writeback app for uploading stock adjustment CSV/Excel files
or entering a single adjustment manually.

The stock adjustment columns in `config.py` are provisional until they are
matched to an approved source-file sample. Update database, schema, role names,
aliases, and required fields before deployment.

## Files

- `streamlit_app.py` - Streamlit UI for file upload, manual entry, previews, and admin review.
- `config.py` - app scope, roles, table DDL, upload aliases, and field rules.
- `storage.py` - table creation, inserts, recent records, and approve/reject updates.
- `validators.py` - field ownership, required-field, select-option, and quantity checks.
- `environment.yml` - suggested Snowflake Streamlit packages.

## Deployment Notes

1. Confirm the `DEMO_DWH.STREAMLIT_APP` target in `config.py`.
2. Confirm `STREAMLIT_APP_ADMIN` and `STREAMLIT_APP_USER` role names.
3. Deploy the files to a Snowflake Streamlit app.
4. Add packages from `environment.yml`.
5. Run once as an admin role and click `Initialise storage tables`.

Rows are inserted with `APPROVAL_STATUS = 'PENDING_APPROVAL'`. Admin users can
approve or reject pending rows from the `Review` tab.

## Upload Columns

- `adjustment_code`
- `date`
- `product`
- `store`
- `channel`
- `country`
- `adjusted_qty`
- `comments`
