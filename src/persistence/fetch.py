"""Reconstruction, à partir de Supabase, d'une table longue (élève x matière)
compatible avec build_student_profile/build_early_profile — nécessaire pour
les imports additifs (incremental_import.py) : un élève déjà importé cette
année scolaire qui reçoit un nouveau fichier matière doit être re-profilé et
re-scoré sur l'ENSEMBLE de ses matières (anciennes + nouvelle), pas seulement
la nouvelle (cf. incident réel : import Éducation physique seul -> 0% de
risque, faute de signal sur les matières modélisées).

`grades` stocke déjà c1..activites bruts (pas seulement moyenne_matiere), donc
cette reconstruction est fidèle : build_early_profile a besoin des composantes
C1/C2 brutes, pas juste de la moyenne (cf. models/early_features.py)."""
from __future__ import annotations

import pandas as pd

from anonymization.anonymize import age_to_band
from persistence.supabase_client import SupabaseRestClient

GRADES_SELECT = (
    "student_id,subject_code,c1,c2,c3,c4,activites,"
    "c1_colonne_existe,c2_colonne_existe,c3_colonne_existe,c4_colonne_existe,activites_colonne_existe,"
    "moyenne_matiere,tendance_matiere,remarque_fr"
)
STUDENTS_SELECT = "id,student_pseudo,niveau,classe,age"


def fetch_full_grades(client: SupabaseRestClient, student_ids: list[str]) -> pd.DataFrame:
    """Renvoie une DataFrame longue (une ligne par élève x matière déjà en
    base) avec les colonnes attendues par build_subject_aggregates en sortie
    (add_subject_aggregates n'a pas besoin d'être ré-appliqué : moyenne_matiere/
    tendance_matiere sont déjà calculées et stockées), build_student_profile et
    build_early_profile. Vide (colonnes présentes, 0 ligne) si `student_ids`
    est vide plutôt que de lever — un batch entièrement composé de nouveaux
    élèves n'a rien à fusionner."""
    columns = [
        "student_pseudo", "niveau", "classe", "tranche_age", "matiere",
        "c1", "c2", "c3", "c4", "activites",
        "c1_colonne_existe", "c2_colonne_existe", "c3_colonne_existe",
        "c4_colonne_existe", "activites_colonne_existe",
        "moyenne_matiere", "tendance_matiere", "remarque",
    ]
    if not student_ids:
        return pd.DataFrame(columns=columns)

    grades_rows = client.select(
        "grades", {"select": GRADES_SELECT, "student_id": f"in.({','.join(student_ids)})"}
    )
    grades_df = pd.DataFrame(grades_rows)
    if grades_df.empty:
        return pd.DataFrame(columns=columns)

    students_rows = client.select(
        "students", {"select": STUDENTS_SELECT, "id": f"in.({','.join(student_ids)})"}
    )
    students_df = pd.DataFrame(students_rows)
    if students_df.empty:
        return pd.DataFrame(columns=columns)
    students_df["tranche_age"] = students_df["age"].apply(age_to_band)

    merged = grades_df.merge(
        students_df[["id", "student_pseudo", "niveau", "classe", "tranche_age"]],
        left_on="student_id",
        right_on="id",
        how="left",
    )
    merged = merged.rename(columns={"subject_code": "matiere", "remarque_fr": "remarque"})
    return merged[columns]
