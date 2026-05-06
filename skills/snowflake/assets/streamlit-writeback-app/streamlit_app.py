from datetime import date

import streamlit as st
from snowflake.snowpark.context import get_active_session

from config import APP_NAME, APPROVED_STATUS, KEY_COLUMNS, RECORD_TYPES, REJECTED_STATUS
from storage import (
    create_storage_objects,
    get_missing_tables,
    insert_record,
    is_app_admin,
    load_pending_records,
    load_recent_records,
    set_record_statuses,
)
from validators import ValidationError


st.set_page_config(page_title=APP_NAME, layout="wide")
st.title(APP_NAME)

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
            "Please ask an app admin to create them."
        )
    st.stop()


def state_key(*parts):
    return "_".join(str(part).lower().replace(" ", "_") for part in parts)


for record_type in RECORD_TYPES:
    version_key = state_key(record_type, "form_version")
    if version_key not in st.session_state:
        st.session_state[version_key] = 0

    success_key = state_key(record_type, "submit_success")
    if st.session_state.pop(success_key, False):
        st.success(f"{record_type} submitted for admin approval.")

review_message = st.session_state.pop("review_message", None)
if review_message:
    message_type, message = review_message
    if message_type == "success":
        st.success(message)
    else:
        st.warning(message)


def render_field(record_type, field, version):
    field_name = field["name"]
    label = field.get("label", field_name)
    widget_key = state_key(record_type, field_name, version)
    field_type = field.get("type", "text")

    if field_type == "textarea":
        return st.text_area(label, value=field.get("default", ""), key=widget_key)

    if field_type == "number":
        value = float(field.get("default", 0.0))
        step = float(field.get("step", 1.0))
        min_value = field.get("min_value")
        if min_value is not None:
            min_value = float(min_value)
        return st.number_input(label, value=value, step=step, min_value=min_value, key=widget_key)

    if field_type == "date":
        return st.date_input(label, value=field.get("default", date.today()), key=widget_key)

    if field_type == "select":
        options = field.get("options", [])
        default = field.get("default")
        index = options.index(default) if default in options else 0
        return st.selectbox(label, options, index=index, key=widget_key)

    return st.text_input(label, value=field.get("default", ""), key=widget_key)


def submit_record(record_type, payload):
    try:
        insert_record(session, record_type, payload)
    except ValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Could not submit {record_type.lower()} record: {exc}")
    else:
        st.cache_data.clear()
        st.session_state[state_key(record_type, "submit_success")] = True
        st.session_state[state_key(record_type, "form_version")] += 1
        st.rerun()


def render_submit_form(record_type):
    record_config = RECORD_TYPES[record_type]
    version = st.session_state[state_key(record_type, "form_version")]

    with st.form(state_key(record_type, "form")):
        payload = {}
        fields = record_config["fields"]

        for index in range(0, len(fields), 3):
            columns = st.columns(3)
            for column, field in zip(columns, fields[index:index + 3]):
                with column:
                    payload[field["name"]] = render_field(record_type, field, version)

        submitted = st.form_submit_button(f"Submit {record_type.lower()} for approval", type="primary")
        if submitted:
            submit_record(record_type, payload)


def review_pending(record_type):
    pending = load_pending_records(session, record_type)
    key_column = KEY_COLUMNS[record_type]

    if pending.empty:
        st.info(f"No {record_type.lower()} records are pending approval.")
        return

    st.dataframe(pending, use_container_width=True)
    selected_keys = st.multiselect(
        "Select records to review",
        pending[key_column].tolist(),
        key=state_key(record_type, "review_keys"),
    )
    review_comment = st.text_area("Admin review comment", key=state_key(record_type, "review_comment"))

    col1, col2 = st.columns(2)
    if col1.button("Approve selected records", type="primary", disabled=not selected_keys):
        set_record_statuses(session, record_type, selected_keys, APPROVED_STATUS, review_comment)
        st.cache_data.clear()
        st.session_state["review_message"] = (
            "success",
            f"Approved {len(selected_keys)} {record_type.lower()} record(s).",
        )
        st.rerun()

    if col2.button("Reject selected records", disabled=not selected_keys):
        set_record_statuses(session, record_type, selected_keys, REJECTED_STATUS, review_comment)
        st.cache_data.clear()
        st.session_state["review_message"] = (
            "warning",
            f"Rejected {len(selected_keys)} {record_type.lower()} record(s).",
        )
        st.rerun()


record_type_names = list(RECORD_TYPES)
tabs = st.tabs(record_type_names + ["Review"])

for record_type, tab in zip(record_type_names, tabs[:-1]):
    with tab:
        render_submit_form(record_type)
        st.divider()
        st.subheader(f"Recent {record_type.lower()} submissions")
        st.dataframe(load_recent_records(session, record_type), use_container_width=True)

with tabs[-1]:
    record_type = st.selectbox("Record type", record_type_names)
    if admin_user:
        review_pending(record_type)
    else:
        st.info("Approval actions are available to app admins only.")
        st.dataframe(load_recent_records(session, record_type), use_container_width=True)
