"""Tests for the coordinator's option handling and poll pacing."""

from __future__ import annotations

from custom_components.allen_heath_idr.coordinator import IdrOptions


def test_default_poll_interval_is_unchanged() -> None:
    """At the default 8x8 without extras, the configured interval is used as-is."""
    options = IdrOptions.from_mapping({})
    assert options.commands_per_poll == 34
    assert options.effective_scan_interval == 10


def test_short_interval_is_kept_when_the_poll_is_small() -> None:
    """A small poll may run as often as the minimum allows."""
    options = IdrOptions.from_mapping({"scan_interval": 2})
    assert options.effective_scan_interval == 2


def test_large_matrix_raises_the_poll_interval() -> None:
    """16x16 with crosspoints polls ~600 values; it's never hammered every 2 s."""
    options = IdrOptions.from_mapping(
        {"inputs": 16, "outputs": 16, "expose_crosspoints": True, "scan_interval": 2}
    )
    assert options.commands_per_poll == 578
    assert options.effective_scan_interval == 24


def test_longer_configured_interval_wins() -> None:
    """A user who picked a slower interval than the floor keeps theirs."""
    options = IdrOptions.from_mapping(
        {"inputs": 16, "outputs": 16, "expose_crosspoints": True, "scan_interval": 60}
    )
    assert options.effective_scan_interval == 60
