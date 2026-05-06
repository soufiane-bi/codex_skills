from config import EXPECTED_FORECAST_FIELDS, REQUIRED_FORECAST_FIELDS


class ValidationError(ValueError):
    """Raised when a forecast payload is not valid for the forecast table."""


def validate_forecast_payload(payload):
    payload_fields = set(payload)
    unexpected_fields = payload_fields - EXPECTED_FORECAST_FIELDS
    missing_fields = REQUIRED_FORECAST_FIELDS - payload_fields
    empty_required = {
        field
        for field in REQUIRED_FORECAST_FIELDS
        if payload.get(field) in (None, "")
    }

    if unexpected_fields:
        fields = ", ".join(sorted(unexpected_fields))
        raise ValidationError(
            "This submission cannot be saved to the forecast table because these "
            f"fields do not belong there: {fields}."
        )

    if missing_fields:
        fields = ", ".join(sorted(missing_fields))
        raise ValidationError(f"The forecast submission is missing required fields: {fields}.")

    if empty_required:
        fields = ", ".join(sorted(empty_required))
        raise ValidationError(f"The forecast submission has blank required fields: {fields}.")

    return True
