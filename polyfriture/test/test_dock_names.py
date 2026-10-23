"""New panels remain usable after importing historical dock names."""

from types import SimpleNamespace

import pytest

from polyfriture import dockmanager


class FakeDock:
    def __init__(self, parent, name, qml_engine, widget_id=None):
        self.name = name

    def objectName(self):
        return self.name


@pytest.mark.parametrize(
    ("existing_names", "expected_name"),
    [
        (["central", "Dock 2"], "Dock 3"),
        (["central", "Existing scope", "Dock custom", "Other 42"], "Dock 1"),
        (["Dock 1", "Dock 3", "Dock 2"], "Dock 4"),
        ([], "Dock 1"),
    ],
)
def test_new_dock_numbering_ignores_historical_names(monkeypatch, existing_names, expected_name):
    monkeypatch.setattr(dockmanager, "Dock", FakeDock)
    manager = SimpleNamespace(
        docks=[FakeDock(None, name, None) for name in existing_names],
        last_widget_stack=[],
        last_settings={},
        _parent=SimpleNamespace(qml_engine=None),
    )

    dockmanager.DockManager.new_dock(manager)

    assert manager.docks[-1].objectName() == expected_name
    assert len({dock.objectName() for dock in manager.docks}) == len(manager.docks)
