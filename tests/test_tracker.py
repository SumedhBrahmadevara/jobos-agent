"""Offline tests for the SQLite tracker: create, read, update."""
import pytest
from jobos.schemas import TrackerRecord


def _record(**kwargs) -> TrackerRecord:
    defaults = dict(
        company="Test Co",
        role_title="Test Analyst",
        fit_score=72,
        category="B",
        status="drafted",
    )
    defaults.update(kwargs)
    return TrackerRecord(**defaults)


def test_save_application_returns_positive_int(tmp_path):
    from jobos.tracker import save_application
    app_id = save_application(_record(), db_path=tmp_path / "test.db")
    assert isinstance(app_id, int)
    assert app_id > 0


def test_get_applications_returns_saved_record(tmp_path):
    from jobos.tracker import save_application, get_applications
    db = tmp_path / "test.db"
    save_application(_record(company="Alpha Fund"), db_path=db)
    rows = get_applications(db_path=db)
    assert len(rows) == 1
    assert rows[0]["company"] == "Alpha Fund"
    assert rows[0]["role_title"] == "Test Analyst"
    assert rows[0]["fit_score"] == 72
    assert rows[0]["category"] == "B"
    assert rows[0]["status"] == "drafted"


def test_get_applications_returns_multiple_records(tmp_path):
    from jobos.tracker import save_application, get_applications
    db = tmp_path / "test.db"
    save_application(_record(company="Alpha"), db_path=db)
    save_application(_record(company="Beta"), db_path=db)
    save_application(_record(company="Gamma"), db_path=db)
    rows = get_applications(db_path=db)
    assert len(rows) == 3
    companies = {r["company"] for r in rows}
    assert companies == {"Alpha", "Beta", "Gamma"}


def test_get_applications_returns_newest_first(tmp_path):
    from jobos.tracker import save_application, get_applications
    db = tmp_path / "test.db"
    save_application(_record(company="First"), db_path=db)
    save_application(_record(company="Second"), db_path=db)
    rows = get_applications(db_path=db)
    # created_at timestamps are ISO strings; lexicographic order == chronological
    assert rows[0]["company"] == "Second"
    assert rows[1]["company"] == "First"


def test_get_applications_empty_when_db_absent(tmp_path):
    from jobos.tracker import get_applications
    result = get_applications(db_path=tmp_path / "nonexistent.db")
    assert result == []


def test_get_applications_respects_limit(tmp_path):
    from jobos.tracker import save_application, get_applications
    db = tmp_path / "test.db"
    for i in range(5):
        save_application(_record(company=f"Co{i}"), db_path=db)
    rows = get_applications(limit=3, db_path=db)
    assert len(rows) == 3


def test_update_status_changes_record(tmp_path):
    from jobos.tracker import save_application, get_applications, update_status
    db = tmp_path / "test.db"
    app_id = save_application(_record(status="drafted"), db_path=db)
    update_status(app_id, "applied", db_path=db)
    rows = get_applications(db_path=db)
    assert rows[0]["status"] == "applied"


def test_update_status_only_changes_target_record(tmp_path):
    from jobos.tracker import save_application, get_applications, update_status
    db = tmp_path / "test.db"
    id_a = save_application(_record(company="A", status="drafted"), db_path=db)
    save_application(_record(company="B", status="drafted"), db_path=db)
    update_status(id_a, "interview", db_path=db)
    rows = {r["company"]: r["status"] for r in get_applications(db_path=db)}
    assert rows["A"] == "interview"
    assert rows["B"] == "drafted"


def test_tracker_stores_optional_fields(tmp_path):
    from jobos.tracker import save_application, get_applications
    db = tmp_path / "test.db"
    save_application(
        _record(job_url="https://example.com/job", platform="Greenhouse", notes="Via referral"),
        db_path=db,
    )
    rows = get_applications(db_path=db)
    assert rows[0]["company"] == "Test Co"
