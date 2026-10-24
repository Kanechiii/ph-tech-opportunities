"""Offline regression checks for approved synthetic rehearsal fixtures."""

from pathlib import Path

import pytest

from src.database.phase12_synthetic_gate import (
    SQL_ROOT, EXPECTED_COUNTS, assess_synthetic_rehearsal,
)


@pytest.fixture
def synthetic_sql(tmp_path):
    original = SQL_ROOT / "003_synthetic_rehearsal.sql"
    sample = tmp_path / "synthetic.sql"
    sample.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    return sample


def test_existing_fixture_matches_seven_table_contract(synthetic_sql):
    report = assess_synthetic_rehearsal(synthetic_sql)
    assert report["synthetic_contract_passed"]
    assert report["table_counts"] == EXPECTED_COUNTS
    assert report["notification_states_checked"] == ["sent", "uncertain"]


def test_gate_never_performs_import_or_cutover(synthetic_sql):
    report = assess_synthetic_rehearsal(synthetic_sql)
    assert not report["source_records_read"]
    assert not report["postgres_connected"]
    assert not report["migration_performed"]
    assert not report["cutover_authorized"]
    assert not report["email_sent"]


def test_fixture_not_modified(synthetic_sql):
    before = synthetic_sql.read_bytes()
    assess_synthetic_rehearsal(synthetic_sql)
    assert synthetic_sql.read_bytes() == before


@pytest.mark.parametrize("old,new", [
    ("950003", "950004"),
    ("950001", "950002"),
    ("940003", "940004"),
    ("910003", "910004"),
])
def test_changed_historical_ids_rejected(synthetic_sql, old, new):
    text = synthetic_sql.read_text(encoding="utf-8")
    # Limit replacement to the first appearance, the INSERT row.
    synthetic_sql.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(ValueError):
        assess_synthetic_rehearsal(synthetic_sql)


def test_missing_table_rejected(synthetic_sql):
    text = synthetic_sql.read_text(encoding="utf-8")
    start = text.index("INSERT INTO phtech.collection_runs")
    end = text.index(";", start) + 1
    synthetic_sql.write_text(text[:start] + text[end:], encoding="utf-8")
    with pytest.raises(ValueError, match="seven"):
        assess_synthetic_rehearsal(synthetic_sql)


def test_uncertain_state_must_remain_uncertain(synthetic_sql):
    text = synthetic_sql.read_text(encoding="utf-8")
    synthetic_sql.write_text(
        text.replace("'uncertain',1,NULL", "'sent',1,NULL", 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="states"):
        assess_synthetic_rehearsal(synthetic_sql)


def test_missing_empty_target_rejection_fails_closed(synthetic_sql):
    text = synthetic_sql.read_text(encoding="utf-8")
    synthetic_sql.write_text(
        text.replace("row_total <> 0", "row_total < 0"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        assess_synthetic_rehearsal(synthetic_sql)


def test_absent_fixture_does_not_create_file(tmp_path):
    path = tmp_path / "absent.sql"
    with pytest.raises(ValueError):
        assess_synthetic_rehearsal(path)
    assert not path.exists()


def test_unapproved_table_is_rejected(synthetic_sql):
    text = synthetic_sql.read_text(encoding="utf-8")
    synthetic_sql.write_text(
        text.replace("INSERT INTO phtech.collection_runs", "INSERT INTO public.users"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        assess_synthetic_rehearsal(synthetic_sql)
