"""`.env.example` must not drift from the settings the code actually reads."""

import re
from pathlib import Path

from app.config import Settings

EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"
ENTRY = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def _entries() -> dict[str, tuple[bool, str]]:
    """name -> (commented out?, value)"""
    found: dict[str, tuple[bool, str]] = {}
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        if m := ENTRY.match(line):
            found[m.group(2)] = (bool(m.group(1)), m.group(3).strip())
    return found


def test_every_setting_is_listed_in_env_example():
    missing = {name.upper() for name in Settings.model_fields} - set(_entries())
    assert not missing, f".env.example does not mention: {sorted(missing)}"


def test_example_values_are_the_defaults_in_code():
    values = {n.lower(): v for n, (commented, v) in _entries().items() if not commented and v}
    parsed = Settings(_env_file=None, **values)
    for name in values:
        if name in Settings.model_fields:
            assert getattr(parsed, name) == Settings.model_fields[name].default, name
