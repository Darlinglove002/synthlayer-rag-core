import logging

from app import answer as answer_mod
from app.config import get_settings
from app.logging_config import FORMAT, configure_logging
from app.search import Hit


def test_log_level_comes_from_the_environment(monkeypatch):
    root = logging.getLogger()
    before = root.level
    try:
        monkeypatch.setenv("LOG_LEVEL", "debug")
        configure_logging()
        assert root.level == logging.DEBUG
        monkeypatch.setenv("LOG_LEVEL", "nonsense")
        configure_logging()
        assert root.level == logging.INFO  # a typo must not stop the service from starting
    finally:
        root.setLevel(before)


def test_configure_logging_installs_one_handler_and_is_idempotent():
    root = logging.getLogger()
    saved, level = root.handlers[:], root.level
    root.handlers = []
    try:
        configure_logging("INFO")
        configure_logging("INFO")
        assert len(root.handlers) == 1
        formatter = root.handlers[0].formatter
        assert formatter is not None and formatter._fmt == FORMAT
    finally:
        root.handlers = saved
        root.setLevel(level)


def test_llm_failure_is_logged_and_falls_back_to_the_extractive_answer(monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test-not-a-real-key")

    def provider_down(question, hits):
        raise RuntimeError("provider down, key sk-test-not-a-real-key")

    monkeypatch.setattr(answer_mod, "llm_answer", provider_down)
    hit = Hit(
        chunk_id=1,
        document_id=1,
        title="guide",
        page=1,
        content="Backups run every night. They are kept for 14 days.",
        rerank_score=5.0,
    )
    with caplog.at_level(logging.WARNING, logger="app.answer"):
        result = answer_mod.answer("How long are backups kept?", [hit])

    assert result.generator == "extractive" and result.grounded
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "falling back" in caplog.text and "RuntimeError" in caplog.text
    assert "sk-test" not in caplog.text, (
        "the provider's message (and any key in it) stays out of logs"
    )
