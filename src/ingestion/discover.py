"""Découverte récursive des fichiers Massar. L'arborescence par enseignant n'est pas
supposée : on cherche tous les .xlsx sous le dossier racine, quelle que soit la profondeur."""
from __future__ import annotations

import glob
import os


def discover_xlsx(root_dir: str) -> list[str]:
    pattern = os.path.join(root_dir, "**", "*.xlsx")
    return sorted(glob.glob(pattern, recursive=True))
