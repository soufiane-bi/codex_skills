import streamlit as st
from snowflake.snowpark.context import get_active_session

from config import APPROVED_STATUS, KEY_COLUMNS, PENDING_STATUS, REJECTED_STATUS
from storage import (
    create_storage_objects,
    get_missing_tables,
    insert_record,
    is_app_admin,
    load_channels,
    load_dates,
    load_pending_records,
    load_products,
    load_recent_records,
    load_stores,
    set_record_status,
)
from validators import ValidationError


st.set_page_config(page_title="Retail Planning Writeback", layout="wide")
st.title("Retail Planning Writeback")

session = get_active_session()
admin_user = is_app_admin(session)

missing_tables = get_missing_tables(session)
if missing_tables:
    if admin_user:
        st.warning("Storage tables are missing: " + ", ".join(missing_tables))
        if st.button("Initialise storage tables", type="primary"):
            create_storage_objects(session)
            st.success("Storage tables created. Refresh the app to continue.")
            st.stop()
    else:
        st.error(
            "Storage tables are not initialised. "
            "Please ask a Streamlit app admin to create them."
        )
    st.stop()


@st.cache_data(ttl=300)
def cached_dimensions():
    return {
        "products": load_products(session),
        "stores": load_stores(session),
        "channels": load_channels(session),
        "dates": load_dates(session),
    }


dims = cached_dimensions()
products = dims["products"]
stores = dims["stores"]
channels = dims["channels"]
dates = dims["dates"]


def choose_product(key):
    options = products.to_dict("records")
    selected = st.selectbox(
        "Product",
        options,
        key=key,
        format_func=lambda row: f"{row['SKU']} | {row['PRODUCT_NAME']}",
    )
    return selected


def choose_store(key):
    options = stores.to_dict("records")
    selected = st.selectbox(
        "Store",
        options,
        key=key,
        format_func=lambda row: f"{row['STORE_CODE']} | {row['STORE_NAME']} | {row['COUNTRY_CODE']}",
    )
    return selected


def choose_channel(key):
    options = channels.to_dict("records")
    selected = st.selectbox(
        "Channel",
        options,
        key=key,
        format_func=lambda row: f"{row['CHANNEL_CODE']} | {row['CHANNEL_NAME']}",
    )
    return selected


def choose_date(label, key):
    options = dates.to_dict("records")
    selected = st.selectbox(
        label,
        options,
        key=key,
        format_func=lambda row: str(row["FULL_DATE"]),
    )
    return selected


def shared_dimension_payload(prefix):
    date_row = choose_date("Date", f"{prefix}_date")
    product = choose_product(f"{prefix}_product")
    store = choose_store(f"{prefix}_store")
    channel = choose_channel(f"{prefix}_channel")

    return {
        "DATE_KEY": int(date_row["DATE_KEY"]),
        "PRODUCT_KEY": int(product["PRODUCT_KEY"]),
        "STORE_KEY": int(store["STORE_KEY"]),
        "CHANNEL_KEY": int(channel["CHANNEL_KEY"]),
        "SKU": product["SKU"],
        "STORE_CODE": store["STORE_CODE"],
        "CHANNEL_CODE": channel["CHANNEL_CODE"],
        "COUNTRY_CODE": store["COUNTRY_CODE"],
    }


def submit(record_type, payload):
    try:
        insert_record(session, record_type, payload)
    except ValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Could not submit {record_type.lower()} record: {exc}")
    else:
        st.success(f"Submitted {record_type.lower()} record for admin approval.")
        st.cache_data.clear()


def review_pending(record_type):
    pending = load_pending_records(session, record_type)
    key_column = KEY_COLUMNS[record_type]

    if pending.empty:
        st.info(f"No {record_type.lower()} records are pending approval.")
        return

    st.dataframe(pending, use_container_width=True)
    selected_key = st.selectbox(
        "Select record to review",
        pending[key_column].tolist(),
        key=f"review_{record_type}",
    )
    review_comment = st.text_area("Admin review comment", key=f"review_comment_{record_type}")
    col1, col2 = st.columns(2)

    if col1.button("Approve selected record", key=f"approve_{record_type}", type="primary"):
        set_record_status(session, record_type, selected_key, APPROVED_STATUS, review_comment)
        st.success("Record approved.")
        st.rerun()

    if col2.button("Reject selected record", key=f"reject_{record_type}"):
        set_record_status(session, record_type, selected_key, REJECTED_STATUS, review_comment)
        st.warning("Record rejected.")
        st.rerun()


st.caption(
    "All new records are submitted as pending approval. "
    "Admins can approve or reject them from the Review tab."
)

tab_adjustments, tab_forecasts, tab_promotions, tab_review = st.tabs(
    ["Adjustments", "Forecasts", "Promotions", "Review"]
)

with tab_adjustments:
    with st.form("adjustments_form"):
        dims_payload = shared_dimension_payload("adjustment")
        col1, col2, col3 = st.columns(3)
        adjustment_type = col1.selectbox(
            "Adjustment type",
            ["COMMERCIAL_OVERRIDE", "STORE_DISRUPTION", "SUPPLY_CONSTRAINT", "PRICE_CHANGE", "DEMAND_EVENT"],
        )
        metric_name = col2.selectbox(
            "Metric",
            ["NET_SALES_AMOUNT", "QUANTITY", "GROSS_MARGIN_AMOUNT"],
        )
        adjustment_method = col3.selectbox("Method", ["PERCENT", "DELTA", "ABSOLUTE"])
        adjustment_value = st.number_input("Adjustment value", value=0.0, step=0.01, format="%.4f")
        reason_code = st.selectbox(
            "Reason code",
            ["WELLNESS_EVENT", "STORE_REFIT", "LOW_STOCK", "PRICE_CHANGE", "WEATHER_UPLIFT"],
        )
        comment = st.text_area("Comment")

        if st.form_submit_button("Submit adjustment for approval", type="primary"):
            payload = {
                "ADJUSTMENT_CODE": f"ADJ-{dims_payload['DATE_KEY']}-{dims_payload['PRODUCT_KEY']}",
                "ADJUSTMENT_TYPE": adjustment_type,
                "METRIC_NAME": metric_name,
                "ADJUSTMENT_METHOD": adjustment_method,
                "ADJUSTMENT_VALUE": adjustment_value,
                "EFFECTIVE_FROM_DATE_KEY": dims_payload["DATE_KEY"],
                "EFFECTIVE_TO_DATE_KEY": dims_payload["DATE_KEY"],
                "REASON_CODE": reason_code,
                "COMMENT": comment,
                "STATUS": PENDING_STATUS,
                **dims_payload,
            }
            submit("Adjustments", payload)

with tab_forecasts:
    with st.form("forecast_form"):
        dims_payload = shared_dimension_payload("forecast")
        col1, col2, col3 = st.columns(3)
        forecast_version = col1.text_input("Forecast version", value="FY26 Wellness Baseline")
        scenario_name = col2.selectbox(
            "Scenario",
            ["BASELINE", "HIGH_DEMAND", "DIGITAL_UPLIFT", "PROMOTIONAL", "CONSTRAINED"],
        )
        forecast_grain = col3.selectbox("Grain", ["DAY", "WEEK", "MONTH"])
        quantity = st.number_input("Forecast quantity", min_value=0.0, value=100.0, step=1.0)
        gross_sales = st.number_input("Gross sales amount", min_value=0.0, value=1000.0, step=10.0)
        discount = st.number_input("Discount amount", min_value=0.0, value=50.0, step=5.0)
        net_sales = st.number_input("Net sales amount", min_value=0.0, value=950.0, step=10.0)
        total_cost = st.number_input("Total cost amount", min_value=0.0, value=500.0, step=10.0)
        gross_margin = st.number_input("Gross margin amount", min_value=0.0, value=450.0, step=10.0)
        comment = st.text_area("Comment", value="Forecast includes known trading events and latest commercial assumptions.")

        if st.form_submit_button("Submit forecast for approval", type="primary"):
            payload = {
                "FORECAST_CODE": f"FCST-{dims_payload['DATE_KEY']}-{dims_payload['PRODUCT_KEY']}",
                "FORECAST_VERSION": forecast_version,
                "SCENARIO_NAME": scenario_name,
                "FORECAST_GRAIN": forecast_grain,
                "PERIOD_START_DATE_KEY": dims_payload["DATE_KEY"],
                "PERIOD_END_DATE_KEY": dims_payload["DATE_KEY"],
                "FORECAST_QUANTITY": quantity,
                "FORECAST_GROSS_SALES_AMOUNT": gross_sales,
                "FORECAST_DISCOUNT_AMOUNT": discount,
                "FORECAST_NET_SALES_AMOUNT": net_sales,
                "FORECAST_TOTAL_COST_AMOUNT": total_cost,
                "FORECAST_GROSS_MARGIN_AMOUNT": gross_margin,
                "MODEL_NAME": "Commercial Planning Forecast",
                "CONFIDENCE_SCORE": 0.85,
                "COMMENT": comment,
                "STATUS": PENDING_STATUS,
                **dims_payload,
            }
            submit("Forecasts", payload)

with tab_promotions:
    with st.form("promotions_form"):
        start_date = choose_date("Start date", "promo_start_date")
        end_date = choose_date("End date", "promo_end_date")
        product = choose_product("promo_product")
        store = choose_store("promo_store")
        channel = choose_channel("promo_channel")

        promotion_name = st.text_input("Promotion name", value="Buy 1 Get 1 Free - Vitamins")
        promotion_type = st.selectbox("Promotion type", ["MULTIBUY", "PRICE_DISCOUNT", "LOYALTY_PRICE", "BUNDLE", "FLASH_SALE"])
        promotion_mechanic = st.selectbox(
            "Promotion mechanic",
            ["BUY_1_GET_1_FREE", "THREE_FOR_TWO", "PERCENT_OFF", "MEMBER_PRICE", "LIMITED_TIME_DEAL"],
        )
        regular_price = st.number_input("Regular price", min_value=0.0, value=12.99, step=0.01)
        promo_price = st.number_input("Promo price", min_value=0.0, value=6.50, step=0.01)
        discount_amount = max(regular_price - promo_price, 0)
        discount_pct = discount_amount / regular_price if regular_price else 0
        expected_uplift = st.number_input("Expected uplift pct", min_value=0.0, value=0.75, step=0.01)
        supplier_funding = st.number_input("Supplier funding amount", min_value=0.0, value=500.0, step=10.0)
        comment = st.text_area("Comment", value="Promotion expected to drive incremental demand during the wellness event.")

        if st.form_submit_button("Submit promotion for approval", type="primary"):
            payload = {
                "PROMOTION_CODE": f"PROMO-{start_date['DATE_KEY']}-{product['PRODUCT_KEY']}",
                "PROMOTION_NAME": promotion_name,
                "PROMOTION_TYPE": promotion_type,
                "PROMOTION_MECHANIC": promotion_mechanic,
                "START_DATE_KEY": int(start_date["DATE_KEY"]),
                "END_DATE_KEY": int(end_date["DATE_KEY"]),
                "PRODUCT_KEY": int(product["PRODUCT_KEY"]),
                "STORE_KEY": int(store["STORE_KEY"]),
                "CHANNEL_KEY": int(channel["CHANNEL_KEY"]),
                "SKU": product["SKU"],
                "STORE_CODE": store["STORE_CODE"],
                "CHANNEL_CODE": channel["CHANNEL_CODE"],
                "COUNTRY_CODE": store["COUNTRY_CODE"],
                "REGULAR_PRICE": regular_price,
                "PROMO_PRICE": promo_price,
                "DISCOUNT_AMOUNT": discount_amount,
                "DISCOUNT_PCT": discount_pct,
                "EXPECTED_UPLIFT_PCT": expected_uplift,
                "SUPPLIER_FUNDING_AMOUNT": supplier_funding,
                "COMMENT": comment,
                "STATUS": PENDING_STATUS,
            }
            submit("Promotions", payload)

with tab_review:
    record_type = st.selectbox("Record type", ["Adjustments", "Forecasts", "Promotions"])
    if admin_user:
        review_pending(record_type)
    else:
        st.info("You can see recent submissions here. Approval actions are available to app admins only.")
        st.dataframe(load_recent_records(session, record_type), use_container_width=True)
