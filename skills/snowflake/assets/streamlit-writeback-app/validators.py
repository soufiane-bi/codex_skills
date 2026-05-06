from config import EXPECTED_FIELDS, REQUIRED_FIELDS, WRITEBACK_TABLES


class ValidationError(ValueError):
    """Raised when a writeback payload does not match the selected record type."""


def validate_record(record_type, payload):
    if record_type not in WRITEBACK_TABLES:
        raise ValidationError(f"Unsupported record type: {record_type}")

    payload_fields = set(payload)
    unexpected_fields = payload_fields - EXPECTED_FIELDS[record_type]
    missing_fields = REQUIRED_FIELDS[record_type] - payload_fields
    empty_required = {
        field
        for field in REQUIRED_FIELDS[record_type]
        if payload.get(field) in (None, "")
    }

    if unexpected_fields:
        fields = ", ".join(sorted(unexpected_fields))
        raise ValidationError(
            f"{record_type} cannot be saved because these fields do not belong "
            f"to that table: {fields}. Check the selected tab before submitting."
        )

    if missing_fields:
        fields = ", ".join(sorted(missing_fields))
        raise ValidationError(f"{record_type} is missing required fields: {fields}.")

    if empty_required:
        fields = ", ".join(sorted(empty_required))
        raise ValidationError(f"{record_type} has blank required fields: {fields}.")

    return True
