"""Offline tests for Phase 10 fail-closed integration gates."""

import pytest

from src.database.postgres_integration_gate import (
    assess_storage_cutover,
    inspect_connection_target,
)


URL = (
    "postgresql://phtech_reader_app:fake-password@"
    "ep-synthetic.aws-ap-southeast-1.neon.tech/"
    "phtech_staging?sslmode=verify-full&channel_binding=require"
)


def test_read_only_staging_target_is_metadata_only():
    report = inspect_connection_target(URL)
    assert report["configuration_valid"]
    assert report["database"] == "phtech_staging"
    assert report["read_only_requested"]
    assert report["tls_verified_by_network"] is False
    assert report["connected"] is False
    assert "fake-password" not in str(report)


@pytest.mark.parametrize("bad", [
    "sqlite:///data/opportunities.sqlite3",
    URL.replace("phtech_staging?", "postgres?"),
    URL.replace("sslmode=verify-full", "sslmode=disable"),
    URL.replace("sslmode=verify-full", "sslmode=require"),
    URL.replace(".neon.tech", ".neon.tech.evil.example"),
    URL.replace("ep-synthetic.", "ep-synthetic-pooler."),
    URL.replace("phtech_reader_app", "phtech_staging_owner"),
])
def test_dangerous_configuration_rejected(bad):
    with pytest.raises(ValueError):
        inspect_connection_target(bad)


def test_any_write_operation_rejected():
    with pytest.raises(ValueError):
        inspect_connection_target(URL, operation="write")


def test_bad_url_does_not_echo_credentials():
    with pytest.raises(ValueError) as exc:
        inspect_connection_target(URL.replace("postgresql://", "https://"))
    assert "fake-password" not in str(exc.value)


def test_unreconciled_histories_block_cutover():
    result = assess_storage_cutover(
        local_report={
            "inventory_complete": True,
            "blockers": ["histories_diverged"],
            "opportunity_table_matches": {
                "opportunities": False,
                "notification_jobs": True,
            },
        },
        destination_reviewed=True,
    )
    assert result["cutover_authorized"] is False
    assert "unreconciled_opportunity_histories" in result["blockers"]
    assert "source_histories_diverged" in result["blockers"]
    assert result["sqlite_backend_remains_authoritative"]


def test_even_matching_histories_cannot_authorize_cutover():
    result = assess_storage_cutover(
        local_report={
            "inventory_complete": True,
            "blockers": [],
            "opportunity_table_matches": {
                "opportunities": True,
                "notification_jobs": True,
            },
        },
        destination_reviewed=True,
    )
    assert result["cutover_authorized"] is False
    assert "cutover_requires_separate_authorization" in result["blockers"]
    assert not result["reviewed_email_automation_enabled"]
    assert not result["records_modified"]
    assert not result["email_sent"]


def test_missing_inventory_blocks_cutover():
    with pytest.raises(ValueError):
        assess_storage_cutover(local_report=None)
