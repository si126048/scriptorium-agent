import os
import tempfile
from pathlib import Path

import pytest

# The legacy SQLite database is a *source*, not scratch space. Keep the legacy default path
# outside the project so an import or a fixture cannot create tables in data/lacan.db, and mark
# that file read-only so an explicit path cannot overwrite it either.
_TESTS_TMP = Path(tempfile.mkdtemp(prefix='scriptorium-tests-'))
os.environ.setdefault('LACAN_DB_PATH', str(_TESTS_TMP / 'legacy-default.db'))
os.environ.setdefault('SCRIPTORIUM_FROZEN_SOURCE', str(Path(__file__).resolve().parents[1] / 'data' / 'lacan.db'))

# Model credentials are personal: never read the developer's Windows credential store or
# ~/.config during tests, and never write to them. Tests that need a key set it explicitly.
_TESTS_HOME = Path(tempfile.mkdtemp(prefix='scriptorium-tests-home-'))
os.environ['SCRIPTORIUM_HOME'] = str(_TESTS_HOME)
os.environ['SCRIPTORIUM_KEY_STORAGE'] = 'file'

from scriptorium.db import Store
from scriptorium.models import ConsentScope, Participant, Project


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = Store(str(db_path))
    s.create_project(Project(id='p'))
    return s


@pytest.fixture
def participant(store):
    return store.put_participant(Participant(
        id='A', project_id='p', pseudonym='A', consent_scope=ConsentScope(),
    ))
