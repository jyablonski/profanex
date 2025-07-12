import pytest

from profanex.filter import _load_yaml


def test_load_yaml_from_fixture(banned_words_path_fixture):
    loaded = _load_yaml(str(banned_words_path_fixture))
    assert isinstance(loaded, set)
    assert len(loaded) > 0
    # Example check: assert a known banned word in the fixture file
    assert "fuck" in loaded


def test_load_yaml_with_dict(tmp_path):
    yaml_path = tmp_path / "categorized.yaml"
    yaml_content = """
    swear:
      - bitch
      - fuck
    insults:
      - jerk
      - fool
    """
    yaml_path.write_text(yaml_content, encoding="utf-8")

    loaded = _load_yaml(str(yaml_path))
    assert isinstance(loaded, set)
    # Check some known words from categories
    assert "fuck" in loaded


def test_load_yaml_file_not_found():
    with pytest.raises(FileNotFoundError):
        _load_yaml("nonexistent_file.yaml")
