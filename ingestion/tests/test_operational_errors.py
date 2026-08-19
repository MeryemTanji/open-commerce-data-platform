"""Unit tests for mercury_ingestion.common.operational_errors."""

from __future__ import annotations

import dataclasses

import pytest

from mercury_ingestion.common.operational_errors import (
    MAX_OPERATIONAL_ERROR_LENGTH,
    OperationalError,
    OperationalErrorCategory,
)


def _error(**overrides: object) -> OperationalError:
    fields = {
        "category": OperationalErrorCategory.SOURCE_VALIDATION_FAILED,
        "component": "CustomerConnector",
        "operation": "validate_source",
        "safe_message": "Source validation failed",
    }
    fields.update(overrides)
    return OperationalError(**fields)  # type: ignore[arg-type]


class TestOperationalErrorCategory:
    def test_exact_values(self) -> None:
        assert OperationalErrorCategory.SOURCE_VALIDATION_FAILED.value == "source_validation_failed"
        assert OperationalErrorCategory.RECORD_COUNT_FAILED.value == "record_count_failed"
        assert OperationalErrorCategory.STORAGE_WRITE_FAILED.value == "storage_write_failed"
        assert OperationalErrorCategory.INGESTION_FAILED.value == "ingestion_failed"
        assert OperationalErrorCategory.WAREHOUSE_LOAD_FAILED.value == "warehouse_load_failed"
        assert OperationalErrorCategory.STATE_PERSISTENCE_FAILED.value == "state_persistence_failed"
        assert OperationalErrorCategory.UNEXPECTED_INTERNAL_ERROR.value == "unexpected_internal_error"

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            OperationalErrorCategory("not_a_real_category")


class TestOperationalErrorValidation:
    def test_valid_construction(self) -> None:
        error = _error()

        assert error.category is OperationalErrorCategory.SOURCE_VALIDATION_FAILED

    def test_is_immutable(self) -> None:
        error = _error()

        with pytest.raises(dataclasses.FrozenInstanceError):
            error.safe_message = "changed"  # type: ignore[misc]

    def test_invalid_category_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            _error(category="source_validation_failed")

    def test_blank_component_rejected(self) -> None:
        with pytest.raises(ValueError):
            _error(component="   ")

    def test_non_string_component_rejected(self) -> None:
        with pytest.raises(TypeError):
            _error(component=123)

    def test_blank_operation_rejected(self) -> None:
        with pytest.raises(ValueError):
            _error(operation="")

    def test_blank_safe_message_rejected(self) -> None:
        with pytest.raises(ValueError):
            _error(safe_message="   ")

    def test_non_string_safe_message_rejected(self) -> None:
        with pytest.raises(TypeError):
            _error(safe_message=None)


class TestToSafeString:
    def test_contains_all_four_fields(self) -> None:
        error = _error(
            category=OperationalErrorCategory.WAREHOUSE_LOAD_FAILED,
            component="HistoricalReplayRunner",
            operation="warehouse_load",
            safe_message="Warehouse load failed",
        )

        rendered = error.to_safe_string()

        assert "warehouse_load_failed" in rendered
        assert "HistoricalReplayRunner" in rendered
        assert "warehouse_load" in rendered
        assert "Warehouse load failed" in rendered

    def test_is_deterministic(self) -> None:
        error = _error()

        assert error.to_safe_string() == error.to_safe_string()

    def test_never_contains_exception_type_name(self) -> None:
        # There is no field for exception type/repr/args at all -- this
        # is a structural guarantee, not a runtime check, but this test
        # documents the expectation directly against the rendered output.
        error = _error(safe_message="Record counting failed")

        rendered = error.to_safe_string()

        assert "Traceback" not in rendered
        assert "Exception" not in rendered

    def test_bounded_length_under_normal_input(self) -> None:
        error = _error()

        assert len(error.to_safe_string()) <= MAX_OPERATIONAL_ERROR_LENGTH

    def test_defensive_truncation_of_oversized_safe_message(self) -> None:
        # Every persisted string is Mercury-authored, so this should
        # never trigger in practice -- but the boundary itself must hold
        # even if a future safe_message is accidentally verbose.
        oversized_message = "x" * (MAX_OPERATIONAL_ERROR_LENGTH * 2)
        error = _error(safe_message=oversized_message)

        rendered = error.to_safe_string()

        assert len(rendered) == MAX_OPERATIONAL_ERROR_LENGTH

    def test_different_categories_produce_different_output(self) -> None:
        source_validation = _error(category=OperationalErrorCategory.SOURCE_VALIDATION_FAILED)
        record_count = _error(category=OperationalErrorCategory.RECORD_COUNT_FAILED)

        assert source_validation.to_safe_string() != record_count.to_safe_string()