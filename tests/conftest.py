"""Fixtures partagées.

`tmp_path`/`tmp_path_factory` de pytest utilisent AppData\\Local\\Temp par
défaut, inaccessible dans cet environnement (PermissionError sandbox Windows).
`local_tmp_path` fournit un répertoire temporaire équivalent sous le dépôt,
toujours accessible en écriture, nettoyé après chaque test."""
import shutil
import uuid
from pathlib import Path

import pytest

_TMP_ROOT = Path(__file__).parent / ".tmp"


@pytest.fixture
def local_tmp_path():
    path = _TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)
