"""Tests for YAML validation and safe backup/save in profile_manager."""
import re
import pytest


def test_validate_yaml_valid():
    from jobos.profile_manager import validate_yaml_text
    result = validate_yaml_text("key: value\nother: 42")
    assert result == {"key": "value", "other": 42}


def test_validate_yaml_empty_returns_empty_dict():
    from jobos.profile_manager import validate_yaml_text
    result = validate_yaml_text("")
    assert result == {}


def test_validate_yaml_invalid_raises():
    from jobos.profile_manager import validate_yaml_text
    with pytest.raises(ValueError):
        validate_yaml_text("key: [unclosed bracket")


def test_validate_yaml_non_dict_top_level_raises():
    from jobos.profile_manager import validate_yaml_text
    with pytest.raises(ValueError, match="mapping"):
        validate_yaml_text("- item1\n- item2")


def test_backup_file_creates_copy(tmp_path):
    from jobos.profile_manager import backup_file
    src = tmp_path / "profile.yaml"
    src.write_text("name: test", encoding="utf-8")
    backup = backup_file(src, tmp_path / "backups")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "name: test"


def test_backup_file_name_has_timestamp_and_original_name(tmp_path):
    from jobos.profile_manager import backup_file
    src = tmp_path / "claims.yaml"
    src.write_text("key: val", encoding="utf-8")
    backup = backup_file(src, tmp_path / "backups")
    assert re.match(r"\d{8}_\d{6}_claims\.yaml", backup.name)


def test_backup_file_creates_backups_dir(tmp_path):
    from jobos.profile_manager import backup_file
    src = tmp_path / "f.yaml"
    src.write_text("x: 1", encoding="utf-8")
    backups_dir = tmp_path / "deep" / "backups"
    assert not backups_dir.exists()
    backup_file(src, backups_dir)
    assert backups_dir.exists()


def test_save_yaml_safe_valid_writes_file(tmp_path):
    from jobos.profile_manager import save_yaml_safe
    target = tmp_path / "profile.yaml"
    target.write_text("old: content", encoding="utf-8")
    new_text = "name: Sumedh\nrole: analyst"
    parsed, backup = save_yaml_safe(target, new_text, tmp_path / "backups")
    assert target.read_text(encoding="utf-8") == new_text
    assert parsed == {"name": "Sumedh", "role": "analyst"}


def test_save_yaml_safe_creates_backup_of_existing_file(tmp_path):
    from jobos.profile_manager import save_yaml_safe
    target = tmp_path / "profile.yaml"
    target.write_text("old: content", encoding="utf-8")
    _, backup = save_yaml_safe(target, "new: data", tmp_path / "backups")
    assert backup is not None
    assert backup.exists()
    assert "old: content" in backup.read_text(encoding="utf-8")


def test_save_yaml_safe_no_backup_when_file_absent(tmp_path):
    from jobos.profile_manager import save_yaml_safe
    target = tmp_path / "new_file.yaml"
    assert not target.exists()
    _, backup = save_yaml_safe(target, "key: value", tmp_path / "backups")
    assert target.exists()
    assert backup is None


def test_save_yaml_safe_invalid_does_not_overwrite(tmp_path):
    from jobos.profile_manager import save_yaml_safe
    target = tmp_path / "profile.yaml"
    original = "valid: yaml"
    target.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError):
        save_yaml_safe(target, "key: [unclosed", tmp_path / "backups")
    assert target.read_text(encoding="utf-8") == original


def test_save_yaml_safe_invalid_does_not_create_backup(tmp_path):
    from jobos.profile_manager import save_yaml_safe
    target = tmp_path / "profile.yaml"
    target.write_text("valid: yaml", encoding="utf-8")
    backups_dir = tmp_path / "backups"
    with pytest.raises(ValueError):
        save_yaml_safe(target, ": broken: yaml:", backups_dir)
    # Backup dir may not exist, or if it does, it should be empty
    if backups_dir.exists():
        assert list(backups_dir.iterdir()) == []
