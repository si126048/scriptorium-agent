import os
import tempfile
from pathlib import Path

import pytest

# The legacy SQLite database is a *source*, not scratch space. Keep the legacy default path
# outside the project so an import or a fixture cannot create tables in data/lacan.db, and mark
# that file read-only so an explicit path cannot overwrite it either.
_TESTS_TMP = Path(tempfile.mkdtemp(prefix='hermeneut-tests-'))
os.environ.setdefault('LACAN_DB_PATH', str(_TESTS_TMP / 'legacy-default.db'))
os.environ.setdefault('HERMENEUT_FROZEN_SOURCE', str(Path(__file__).resolve().parents[1] / 'data' / 'lacan.db'))

from hermeneut.db import Store
from hermeneut.models import ConsentScope, Participant, Project


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
