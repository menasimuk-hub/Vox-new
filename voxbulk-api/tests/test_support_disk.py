"""Support Disk status/channel helpers and FAQ surface filters."""

from __future__ import annotations

import pytest

from app.services.support_ticket_service import (
    normalize_channel,
    normalize_priority,
    normalize_status,
)


def test_normalize_status_supports_disk_set():
    assert normalize_status("waiting") == "waiting"
    assert normalize_status("resolved") == "resolved"
    with pytest.raises(ValueError):
        normalize_status("bogus")


def test_normalize_channel():
    assert normalize_channel("imap") == "imap"
    assert normalize_channel("mail") == "email"
    assert normalize_channel(None) == "web"
    with pytest.raises(ValueError):
        normalize_channel("phone")


def test_normalize_priority():
    assert normalize_priority("urgent") == "urgent"
    assert normalize_priority("") is None
