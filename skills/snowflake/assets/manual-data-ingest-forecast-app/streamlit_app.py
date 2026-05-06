from datetime import date, timedelta

import streamlit as st
from snowflake.snowpark.context import get_active_session

from config import (
    APP_NAME,
    APPROVED_STATUS,
    FORECAST_KEY_COLUMN,
    PENDING_STATUS,
    REJECTED_STATUS,
)
from storage import (
    create_storage_objects,
    get_missing_tables,
    is_app_admin,
    load_pending_forecasts,
    load_recent_forecasts,
    set_forecast_statuses,
    submit_forecast,
)
from validators import ValidationError


st.set_page_config(page_title=APP_NAME, layout="wide")
st.title(APP_NAME)

session = get_active_session()
admin_user = is_app_admin(session)

missing_tables = get_missing_tables(session)
if missing_tables:
    if admin_user:
        st.warning("Manual Data Ingest storage is not initialised.")
        if st.button("Initialise forecast storage", type="primary"):
            create_storage_objects(session)
            st.success("Forecast storage created. Refresh the app to continue.")
            st.stop()
    else:
        st.error(
            "Manual Data Ingest is not ready yet. "
            "Please contact a Streamlit app admin to initialise forecast storage."
        )
    st.stop()

if "forecast_form_version" not in st.session_state:
    st.session_state["forecast_form_version"] = 0

if st.session_state.pop("forecast_submit_success", False):
    st.success("Forecast submitted for admin approval.")

admin_review_message = st.session_state.pop("forecast_admin_review_message", None)
if admin_review_message:
    message_type, message = admin_review_message
    if message_type == "success":
        st.success(message)
    else:
        st.warning(message)


def submit_payload(payload):
    try:
        submit_forecast(session, payload)
    except ValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Could not submit forecast: {exc}")
    else:
        st.cache_data.clear()
        st.session_state["forecast_submit_success"] = True
        st.session_state["forecast_form_version"] += 1
        st.rerun()


def review_pending_forecasts():
    pending = load_pending_forecasts(session)

    if pending.empty:
        st.info("No forecasts are pending approval.")
        return

    st.dataframe(pending, use_container_width=True)

    pending_records = {
        row[FORECAST_KEY_COLUMN]: row
        for row in pending.to_dict("records")
    }

    def format_forecast_key(forecast_key):
        row = pending_records.get(forecast_key, {})
        return (
            f"{forecast_key} | {row.get('FORECAST_CODE', '')} | "
            f"{row.get('PRODUCT_KEY', '')} | "
            f"{row.get('PERIOD_START_DATE_KEY', '')} to {row.get('PERIOD_END_DATE_KEY', '')} | "
            f"Qty {row.get('FORECAST_QUANTITY', '')}"
        )

    selected_keys = st.multiselect(
        "Select forecasts to review",
        pending[FORECAST_KEY_COLUMN].tolist(),
        format_func=format_forecast_key,
        key="forecast_review_keys",
    )
    review_comment = st.text_area("Admin review comment", key="forecast_review_comment")

    col1, col2 = st.columns(2)
    if col1.button("Approve selected forecasts", type="primary", disabled=not selected_keys):
        set_forecast_statuses(session, selected_keys, APPROVED_STATUS, review_comment)
        st.cache_data.clear()
        st.session_state["forecast_admin_review_message"] = (
            "success",
            f"Approved {len(selected_keys)} forecast submission(s).",
        )
        st.rerun()

    if col2.button("Reject selected forecasts", disabled=not selected_keys):
        set_forecast_statuses(session, selected_keys, REJECTED_STATUS, review_comment)
        st.cache_data.clear()
        st.session_state["forecast_admin_review_message"] = (
            "warning",
            f"Rejected {len(selected_keys)} forecast submission(s).",
        )
        st.rerun()


forecast_tab = st.tabs(["Forecast"])[0]

with forecast_tab:
    st.caption("Submit manual forecast records using the Excel-style layout.")

    form_version = st.session_state["forecast_form_version"]

    with st.form("forecast_submission_form"):
        st.subheader("New forecast")

        col1, col2, col3 = st.columns(3)
        forecast_code = col1.text_input("FORECAST_CODE", value="", key=f"forecast_code_{form_version}")
        product_key = col2.text_input("PRODUCT_KEY", value="", key=f"product_key_{form_version}")
        forecast_quantity = col3.number_input(
            "FORECAST_QUANTITY",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"forecast_quantity_{form_version}",
        )

        date_col1, date_col2, date_col3 = st.columns(3)
        date_key = date_col1.date_input("DATE_KEY", value=date.today(), key=f"date_key_{form_version}")
        period_start = date_col2.date_input(
            "PERIOD_START_DATE_KEY",
            value=date.today(),
            key=f"period_start_{form_version}",
        )
        period_end = date_col3.date_input(
            "PERIOD_END_DATE_KEY",
            value=date.today() + timedelta(days=7),
            key=f"period_end_{form_version}",
        )

        key_col1, key_col2, key_col3 = st.columns(3)
        store_key = key_col1.text_input("STORE_KEY", value="", key=f"store_key_{form_version}")
        channel_key = key_col2.selectbox("CHANNEL_KEY", ["store", "online"], key=f"channel_key_{form_version}")
        sku = key_col3.text_input("SKU", value="", key=f"sku_{form_version}")

        country_code = st.text_input("COUNTRY_CODE", value="UK", key=f"country_code_{form_version}")

        comment = st.text_area("COMMENT", value="", key=f"comment_{form_version}")
        status = st.selectbox("STATUS", ["Valid", "Invalid"], index=0, key=f"status_{form_version}")

        submitted = st.form_submit_button("Submit forecast for approval", type="primary")

        if submitted:
            payload = {
                "FORECAST_CODE": forecast_code,
                "DATE_KEY": date_key,
                "PERIOD_START_DATE_KEY": period_start,
                "PERIOD_END_DATE_KEY": period_end,
                "PRODUCT_KEY": product_key,
                "STORE_KEY": store_key,
                "CHANNEL_KEY": channel_key,
                "SKU": sku,
                "COUNTRY_CODE": country_code,
                "FORECAST_QUANTITY": forecast_quantity,
                "COMMENT": comment,
                "STATUS": status,
            }
            submit_payload(payload)

    st.divider()

    if admin_user:
        st.subheader("Pending approval")
        review_pending_forecasts()
    else:
        st.subheader("Recent forecast submissions")
        st.dataframe(load_recent_forecasts(session), use_container_width=True)
