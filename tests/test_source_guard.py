"""The legacy source database must stay untouched by tests and acceptance runs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scriptorium import db as legacy
from scriptorium.config import frozen_source


def test_frozen_source_refuses_to_open_for_writing(tmp_path, monkeypatch):
    frozen = tmp_path / 'frozen-source.db'
    frozen.write_bytes(b'')
    monkeypatch.setenv('SCRIPTORIUM_FROZEN_SOURCE', str(frozen))
    assert frozen_source() == str(frozen.resolve())
    with pytest.raises(RuntimeError, match='SOURCE_DATABASE_READ_ONLY'):
        legacy.Store(str(frozen))
    # The refusal happens before any table or default project is created.
    assert frozen.read_bytes() == b''


def test_working_copy_stays_usable(tmp_path, monkeypatch):
    frozen = tmp_path / 'frozen-source.db'
    frozen.write_bytes(b'')
    monkeypatch.setenv('SCRIPTORIUM_FROZEN_SOURCE', str(frozen))
    store = legacy.Store(str(tmp_path / 'working.db'))
    assert store.get_project('default')
    assert not frozen.exists() or frozen.stat().st_size == 0


def test_tests_never_default_to_the_project_data_directory():
    configured = Path(os.environ['LACAN_DB_PATH']).resolve()
    project_data = Path(__file__).resolve().parents[1] / 'data'
    assert configured.parent != project_data, f'tests would write legacy tables into {configured}'
    assert configured.name != 'lacan.db'
