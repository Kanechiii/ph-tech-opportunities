"""Offline Phase 12 backend-activation guard regression tests."""

import pytest

from src.database.phase12_runtime_guard import assess_application_backend

SYNTHETIC_URL = (
    "postgresql://phtech_reader_app:synthetic-only@"
    "ep-synthetic.aws-ap-southeast-1.neon.tech/"
    "phtech_staging?sslmode=verify-full&channel_binding=require"
)


def test_default_remains_sqlite_and_side_effect_free():
    result = assess_application_backend({})
    assert result["configuration_accepted"]
    assert result["runtime_backend"] == "sqlite"
    assert not result["postgres_runtime_enabled"]
    assert not result["postgres_import_enabled"]
    assert not result["production_cutover_authorized"]
    assert not result["reviewed_email_automation_enabled"]
    assert not result["network_connected"]
    assert not result["database_modified"]
    assert not result["email_sent"]


def test_explicit_sqlite_configuration_remains_supported():
    result = assess_application_backend({
        "storage_backend": "sqlite",
        "postgres_runtime_enabled": False,
        "postgres_import_enabled": False,
        "production_cutover_enabled": False,
        "reviewed_email_automation_enabled": False,
    })
    assert result["runtime_backend"] == "sqlite"


@pytest.mark.parametrize("backend", [
    "postgres", "postgresql", "neon", "SQLITE", "", None, True
])
def test_backend_switches_rejected(backend):
    with pytest.raises(PermissionError):
        assess_application_backend({"storage_backend": backend})


@pytest.mark.parametrize("switch", [
    "postgres_runtime_enabled",
    "postgres_import_enabled",
    "production_cutover_enabled",
    "reviewed_email_automation_enabled",
])
@pytest.mark.parametrize("value", [True, "true", "YES", 1])
def test_activation_switches_fail_closed(switch, value):
    with pytest.raises(PermissionError):
        assess_application_backend({switch: value})


def test_staging_url_inspection_is_pure_and_never_echoes_password():
    result = assess_application_backend({
        "storage_backend": "sqlite",
        "postgres_inspection_url": SYNTHETIC_URL,
    })
    assert result["staging_metadata_inspected_offline"]
    assert not result["network_connected"]
    assert not result["secrets_exported"]
    assert "synthetic-only" not in repr(result)


@pytest.mark.parametrize("wrong", [
    SYNTHETIC_URL.replace("phtech_staging?", "postgres?"),
    SYNTHETIC_URL.replace("sslmode=verify-full", "sslmode=disable"),
    SYNTHETIC_URL.replace(".neon.tech", ".neon.tech.evil.test"),
    SYNTHETIC_URL.replace("phtech_reader_app", "phtech_staging_owner"),
])
def test_unsafe_staging_target_refused(wrong):
    with pytest.raises(ValueError) as exc:
        assess_application_backend({"postgres_inspection_url": wrong})
    assert "synthetic-only" not in str(exc.value)


def test_unrecognized_configuration_key_fails_closed():
    with pytest.raises(ValueError):
        assess_application_backend({"override_authorization": True})


def test_input_never_modified():
    settings = {"storage_backend": "sqlite", "postgres_runtime_enabled": False}
    before = settings.copy()
    assess_application_backend(settings)
    assert settings == before
