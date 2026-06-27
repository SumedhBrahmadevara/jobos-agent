"""Root conftest: force offline mode for every test.

Patches jobos.llm_client.OPENAI_API_KEY to None so llm_is_available()
returns False and all agents fall back to their deterministic offline paths.
No API key is required to run the suite.
"""
import pytest


@pytest.fixture(autouse=True)
def offline_mode(monkeypatch):
    import jobos.llm_client as lc
    monkeypatch.setattr(lc, "OPENAI_API_KEY", None)
