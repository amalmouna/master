"""Étape A — parsing : matières hors périmètre modélisé.

Régression pour le bug réel observé en production : un export Massar pour
une matière non modélisée (ex. Informatique, "المعلوميات") n'était pas
reconnu par MATIERE_AR_TO_CODE, et le code arabe brut finissait comme
`matiere`/`subject_code` jusqu'à la persistance, où il violait la contrainte
de clé étrangère `grades_subject_code_fkey` (aucune ligne correspondante
dans `subjects`, qui ne contient que les 7 matières modélisées). Le fichier
doit être mis en quarantaine au parsing, comme un fichier illisible."""
import os
import shutil
import tempfile

import openpyxl
import pytest

from ingestion.parse_massar import parse_file
from score_import import BLOCKING_ISSUE_CODES


@pytest.fixture
def tmp_path():
    d = tempfile.mkdtemp(prefix="test_ingestion_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _build_massar_like_file(path: str, matiere_ar: str) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="المادة")
    ws.cell(row=1, column=2, value=matiere_ar)
    ws.cell(row=2, column=2, value="ID")
    ws.cell(row=2, column=3, value="Code")
    ws.cell(row=2, column=4, value="Nom")
    ws.cell(row=2, column=7, value="الفرض الأول")
    ws.cell(row=4, column=2, value="1")
    ws.cell(row=4, column=3, value="C001")
    ws.cell(row=4, column=4, value="Élève Un")
    ws.cell(row=4, column=7, value=12.0)
    wb.save(path)


def test_matiere_connue_ne_declenche_aucun_probleme(tmp_path):
    path = os.path.join(tmp_path, "Export_28847E_1APIC-1_LANGUE ARABE_20260101000000.xlsx")
    _build_massar_like_file(path, "اللغة العربية")
    result = parse_file(path)
    assert result.matiere_content == "LANGUE ARABE"
    assert not any(i["code"] == "MATIERE_HORS_PERIMETRE" for i in result.issues)


def test_matiere_hors_perimetre_est_signalee_et_bloquante(tmp_path):
    path = os.path.join(tmp_path, "Export_28847E_2APIC-1_INFORMATIQUE_20260101000000.xlsx")
    _build_massar_like_file(path, "المعلوميات")
    result = parse_file(path)

    assert result.matiere_content == "المعلوميات"  # code brut, jamais un code canonique inventé
    matiere_issues = [i for i in result.issues if i["code"] == "MATIERE_HORS_PERIMETRE"]
    assert len(matiere_issues) == 1
    assert matiere_issues[0]["detail"] == "المعلوميات"

    # C'est bien ce code qui fait quarantiner le fichier en amont de la persistance
    # (score_import._ingest_and_clean / pipeline_run.run) — sinon ce texte brut finirait
    # comme subject_code et violerait la FK grades_subject_code_fkey en base.
    assert "MATIERE_HORS_PERIMETRE" in BLOCKING_ISSUE_CODES
