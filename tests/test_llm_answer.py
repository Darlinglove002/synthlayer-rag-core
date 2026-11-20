"""The LLM answer path, with a stand-in for the `anthropic` package (no network, no key)."""

import sys
from types import ModuleType, SimpleNamespace

from app import answer as answer_mod
from app.config import get_settings
from app.search import Hit

HITS = [
    Hit(1, 1, "guide", 1, "Backups run every night and are kept for 14 days."),
    Hit(2, 1, "guide", 2, "Single sign-on uses SAML 2.0 or OIDC."),
]


def _provider_returns(monkeypatch, blocks):
    class Messages:
        def create(self, **kwargs):
            return SimpleNamespace(content=blocks)

    class Anthropic:
        def __init__(self, api_key=None):
            self.messages = Messages()

    fake = ModuleType("anthropic")
    fake.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test-not-a-real-key")


def test_only_text_blocks_are_read_and_markers_become_citations(monkeypatch):
    _provider_returns(
        monkeypatch,
        [
            SimpleNamespace(type="thinking", thinking="not part of the answer"),
            SimpleNamespace(type="text", text="Backups are kept for 14 days [1]."),
        ],
    )
    out = answer_mod.llm_answer("How long are backups kept?", HITS)
    assert out.grounded and out.text == "Backups are kept for 14 days [1]."
    assert [(c.n, c.title, c.page) for c in out.citations] == [(1, "guide", 1)]


def test_a_refusal_from_the_model_carries_no_citations(monkeypatch):
    _provider_returns(monkeypatch, [SimpleNamespace(type="text", text=answer_mod.NO_ANSWER)])
    out = answer_mod.llm_answer("What is the capital of France?", HITS)
    assert not out.grounded and out.citations == []


def test_an_answer_without_a_valid_source_marker_is_not_trusted(monkeypatch):
    _provider_returns(
        monkeypatch,
        [SimpleNamespace(type="text", text="Paris. See [7].")],  # only sources 1 and 2 exist
    )
    out = answer_mod.llm_answer("What is the capital of France?", HITS)
    assert not out.grounded and out.text == answer_mod.NO_ANSWER
