from config import (
    EXPECTED_FORECAST_FIELDS,
    EXPECTED_PROMOTION_FIELDS,
    REQUIRED_FORECAST_FIELDS,
    REQUIRED_PROMOTION_FIELDS,
)


class ValidationError(ValueError):
    """Raised when a submitted payload is not valid for its ingest table."""


def _validate_payload(payload, expected_fields, required_fields, table_label):
    payload_fields = set(payload)
    effective_required_fields = set(required_fields)
    channel_key = str(payload.get("CHANNEL_KEY") or "").strip().lower()
    if channel_key == "online":
        effective_required_fields.discard("STORE_KEY")

    unexpected_fields = payload_fields - expected_fields
    missing_fields = effective_required_fields - payload_fields
    empty_required = {
        field
        for field in effective_required_fields
        if payload.get(field) in (None, "")
    }

    if unexpected_fields:
        fields = ", ".join(sorted(unexpected_fields))
        raise ValidationError(
            f"This submission cannot be saved to the {table_label} table because these "
            f"fields do not belong there: {fields}."
        )

    if missing_fields:
        fields = ", ".join(sorted(missing_fields))
        raise ValidationError(f"The {table_label} submission is missing required fields: {fields}.")

    if empty_required:
        fields = ", ".join(sorted(empty_required))
        raise ValidationError(f"The {table_label} submission has blank required fields: {fields}.")

    return True


def validate_forecast_payload(payload):
    return _validate_payload(
        payload,
        EXPECTED_FORECAST_FIELDS,
        REQUIRED_FORECAST_FIELDS,
        "forecast",
    )


def validate_promotion_payload(payload):
    return _validate_payload(
        payload,
        EXPECTED_PROMOTION_FIELDS,
        REQUIRED_PROMOTION_FIELDS,
        "promotion",
    )
