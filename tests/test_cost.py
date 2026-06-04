from datetime import datetime, timezone

import pytest

from src.adapters.types import UsageEntry
from src.analyzer import cost


def make_entry(**kw):
    defaults = dict(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        session_id="s1",
        message_id="m1",
        request_id="r1",
        model="claude-opus-4-6",
        input_tokens=0,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        cost_usd=None,
        project="proj",
        agent_id="claude",
    )
    defaults.update(kw)
    return UsageEntry(**defaults)


@pytest.fixture
def fixed_pricing(monkeypatch):
    """Inject deterministic pricing so tests never hit the network or cache file."""
    pricing = {
        "claude-opus-4-6": {
            "input_cost_per_token": 15e-6,
            "output_cost_per_token": 75e-6,
            "cache_creation_input_token_cost": 18.75e-6,
            "cache_read_input_token_cost": 1.5e-6,
        },
    }
    monkeypatch.setattr(cost, "_pricing", pricing)
    return pricing


def test_explicit_cost_is_passed_through(fixed_pricing):
    # When the entry already carries a cost, pricing must be ignored entirely.
    entry = make_entry(cost_usd=1.23, input_tokens=999_999)
    assert cost.calculate_cost(entry) == 1.23


def test_cost_computed_from_pricing(fixed_pricing):
    entry = make_entry(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
        cache_read_tokens=1_000_000,
    )
    # 15 + 75 + 18.75 + 1.5
    assert cost.calculate_cost(entry) == pytest.approx(110.25)


def test_unknown_model_returns_zero(fixed_pricing):
    entry = make_entry(model="totally-unknown-xyz", input_tokens=1_000_000)
    assert cost.calculate_cost(entry) == 0.0


def test_model_resolved_by_substring(fixed_pricing):
    # A dated model id should resolve to its base pricing key via substring match.
    entry = make_entry(model="claude-opus-4-6-20260101", input_tokens=1_000_000)
    assert cost.calculate_cost(entry) == pytest.approx(15.0)
