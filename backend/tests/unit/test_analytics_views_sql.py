"""Tests for analytics views migration module (T-084)."""

import importlib


def test_revision() -> None:
    m = importlib.import_module("migrations.versions.009_analytics_views")
    assert m.revision == "c3d4e5f6a7b8"
    assert m.down_revision == "b2c3d4e5f6a7"


def test_upgrade_and_downgrade_are_callable() -> None:
    m = importlib.import_module("migrations.versions.009_analytics_views")
    assert callable(m.upgrade)
    assert callable(m.downgrade)


def test_branch_labels_and_depends_on_are_none() -> None:
    m = importlib.import_module("migrations.versions.009_analytics_views")
    assert m.branch_labels is None
    assert m.depends_on is None
