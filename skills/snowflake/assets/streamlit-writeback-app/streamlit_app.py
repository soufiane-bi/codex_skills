from datetime import date
from decimal import Decimal, InvalidOperation
import io
import re
import uuid

import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

from config import APP_NAME, APPROVED_STATUS, KEY_COLUMNS, RECORD_TYPES, REJECTED_STATUS, UPLOAD_MAX_ROWS
from storage import (
    create_storage_objects,
    get_missing_tables,
    insert_records,
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


def normalize_token(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def normalize_cell(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def parse_uploaded_file(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    file_name = uploaded_file.name.lower()

    if file_name.endswith(".csv"):
        frame = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    elif file_name.endswith((".xlsx", ".xls")):
        frame = pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna("")
    else:
        raise ValidationError("Upload a CSV or Excel file.")

    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.dropna(how="all")
    frame = frame.loc[~(frame.astype(str).apply(lambda row: "".join(row).strip(), axis=1) == "")]
    frame = frame.reset_index(drop=True)

    if frame.empty:
        raise ValidationError("The uploaded file does not contain any data rows.")

    if len(frame) > UPLOAD_MAX_ROWS:
        raise ValidationError(f"Upload has {len(frame):,} rows. The limit is {UPLOAD_MAX_ROWS:,}.")

    return frame


def infer_column_mapping(record_type, frame):
    normalized_columns = {normalize_token(column): column for column in frame.columns}
    mapping = {}

    for field in RECORD_TYPES[record_type]["fields"]:
        mapped_column = ""
        for alias in field.get("aliases", []):
            match = normalized_columns.get(normalize_token(alias))
            if match:
                mapped_column = match
                break
        mapping[field["name"]] = mapped_column

    return mapping


def render_column_mapping(record_type, frame):
    inferred = infer_column_mapping(record_type, frame)
    choices = [""] + list(frame.columns)
    mapping = {}

    st.subheader("Column mapping")
    columns = st.columns(3)
    for index, field in enumerate(RECORD_TYPES[record_type]["fields"]):
        default = inferred.get(field["name"], "")
        default_index = choices.index(default) if default in choices else 0
        label = field.get("label", field["name"])
        if field.get("required", False):
            label = f"{label} *"

        with columns[index % 3]:
            mapping[field["name"]] = st.selectbox(
                label,
                choices,
                index=default_index,
                key=state_key(record_type, field["name"], "upload_mapping"),
            )

    return mapping


def coerce_upload_value(raw_value, field):
    value = normalize_cell(raw_value)
    field_type = field.get("type", "text")

    if value is None:
        return None

    if field_type == "number":
        try:
            return Decimal(value.replace(",", ""))
        except (AttributeError, InvalidOperation) as exc:
            raise ValidationError(f"{field['label']} must be numeric.") from exc

    if field_type == "date":
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            raise ValidationError(f"{field['label']} must be a valid date.")
        return parsed.date()

    if field_type == "select":
        options = field.get("options", [])
        normalized_options = {normalize_token(option): option for option in options}
        matched = normalized_options.get(normalize_token(value))
        if matched:
            return matched
        raise ValidationError(f"{field['label']} must be one of: {', '.join(options)}.")

    return value


def build_upload_payloads(record_type, frame, mapping, upload_batch_id, upload_file_name):
    payloads = []
    errors = []
    fields = RECORD_TYPES[record_type]["fields"]

    for row_number, row in frame.iterrows():
        payload = {}
        row_errors = []

        for field in fields:
            field_name = field["name"]
            source_column = mapping.get(field_name)
            raw_value = row[source_column] if source_column else None

            try:
                payload[field_name] = coerce_upload_value(raw_value, field)
            except ValidationError as exc:
                payload[field_name] = raw_value
                row_errors.append(str(exc))

        try:
            from validators import validate_record

            validate_record(record_type, payload)
        except ValidationError as exc:
            row_errors.append(str(exc))

        if row_errors:
            errors.append(
                {
                    "row_number": row_number + 1,
                    "errors": "; ".join(row_errors),
                }
            )

        payload["UPLOAD_BATCH_ID"] = upload_batch_id
        payload["UPLOAD_FILE_NAME"] = upload_file_name
        payload["UPLOAD_ROW_NUMBER"] = row_number + 1
        payloads.append(payload)

    return payloads, pd.DataFrame(errors)


def upload_preview(record_type, payloads):
    return pd.DataFrame(
        [
            {
                field["name"]: payload.get(field["name"])
                for field in RECORD_TYPES[record_type]["fields"]
            }
            for payload in payloads
        ]
    )


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


def submit_upload(record_type, payloads):
    try:
        insert_records(session, record_type, payloads)
    except ValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Could not submit uploaded {record_type.lower()} records: {exc}")
    else:
        st.cache_data.clear()
        st.session_state[state_key(record_type, "upload_success")] = len(payloads)
        st.rerun()


def render_upload_form(record_type):
    uploaded_count = st.session_state.pop(state_key(record_type, "upload_success"), None)
    if uploaded_count:
        st.success(f"{uploaded_count:,} {record_type.lower()} submitted for admin approval.")

    uploaded_file = st.file_uploader(
        "Upload CSV or Excel",
        type=["csv", "xlsx", "xls"],
        key=state_key(record_type, "upload_file"),
    )

    if uploaded_file is None:
        return

    try:
        frame = parse_uploaded_file(uploaded_file)
    except ValidationError as exc:
        st.error(str(exc))
        return

    st.dataframe(frame.head(50), use_container_width=True)
    mapping = render_column_mapping(record_type, frame)
    upload_batch_id = str(uuid.uuid4())
    payloads, errors = build_upload_payloads(
        record_type,
        frame,
        mapping,
        upload_batch_id=upload_batch_id,
        upload_file_name=uploaded_file.name,
    )
    preview = upload_preview(record_type, payloads)

    metric_columns = st.columns(3)
    metric_columns[0].metric("Rows", f"{len(frame):,}")
    metric_columns[1].metric("Ready", f"{len(frame) - len(errors):,}")
    metric_columns[2].metric("Errors", f"{len(errors):,}")

    st.subheader("Upload preview")
    st.dataframe(preview.head(100), use_container_width=True)

    if not errors.empty:
        st.error("Fix the mapped values before submitting.")
        st.dataframe(errors, use_container_width=True)
        return

    if st.button(
        f"Submit {len(payloads):,} {record_type.lower()} for approval",
        type="primary",
        key=state_key(record_type, "submit_upload"),
    ):
        submit_upload(record_type, payloads)


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
        upload_tab, manual_tab = st.tabs(["File upload", "Manual entry"])
        with upload_tab:
            render_upload_form(record_type)
        with manual_tab:
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
