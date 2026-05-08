from decimal import Decimal, InvalidOperation

from config import EXPECTED_FIELDS, RECORD_TYPES, REQUIRED_FIELDS, WRITEBACK_TABLES


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

    fields_by_name = {
        field["name"]: field
        for field in RECORD_TYPES[record_type]["fields"]
    }

    for field_name, value in payload.items():
        if field_name not in fields_by_name:
            continue

        field = fields_by_name[field_name]
        field_type = field.get("type", "text")

        if value in (None, ""):
            continue

        if field_type == "number":
            try:
                numeric_value = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValidationError(f"{field_name} must be numeric.") from exc

            if field_name == "ADJUSTED_QTY" and numeric_value == 0:
                raise ValidationError("ADJUSTED_QTY must not be zero.")

        if field_type == "select" and value not in field.get("options", []):
            options = ", ".join(field.get("options", []))
            raise ValidationError(f"{field_name} must be one of: {options}.")

    return True
