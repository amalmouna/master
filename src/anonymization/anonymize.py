"""Étape C — résolution d'identité et pseudonymisation.

Aucune donnée nominative ne doit exister au-delà de cette étape (ni artefact, ni base,
ni frontend). Le sel HMAC est lu depuis la variable d'environnement MASSAR_SALT ; à
défaut, un sel local est généré et stocké hors dépôt (data/artifacts/.salt, gitignored)
pour rester stable d'un run à l'autre sans jamais être committé.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import date

import pandas as pd

SALT_ENV_VAR = "MASSAR_SALT"
SALT_FILE_DEFAULT = "data/artifacts/.salt"
PSEUDO_LENGTH = 16

AGE_BANDS = [
    (0, 11, "<=11"),
    (12, 12, "12"),
    (13, 13, "13"),
    (14, 14, "14"),
    (15, 15, "15"),
    (16, 200, ">=16"),
]


def get_or_create_salt(salt_file: str = SALT_FILE_DEFAULT) -> bytes:
    env_salt = os.environ.get(SALT_ENV_VAR)
    if env_salt:
        return env_salt.encode("utf-8")
    if os.path.exists(salt_file):
        with open(salt_file, "rb") as f:
            return f.read()
    os.makedirs(os.path.dirname(salt_file), exist_ok=True)
    new_salt = os.urandom(32)
    with open(salt_file, "wb") as f:
        f.write(new_salt)
    return new_salt


def pseudonymize_code(student_code: str, salt: bytes) -> str:
    digest = hmac.new(salt, str(student_code).encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:PSEUDO_LENGTH]


def dob_to_age(dob_raw, reference_date: date) -> float | None:
    """Âge au 1er septembre de l'année scolaire. dob_raw peut être un datetime,
    une date, ou une chaîne 'DD-MM-YYYY'."""
    if dob_raw is None:
        return None
    dob = None
    if hasattr(dob_raw, "year") and hasattr(dob_raw, "month"):
        dob = dob_raw
    elif isinstance(dob_raw, str):
        for fmt_sep in ("-", "/"):
            parts = dob_raw.strip().split(fmt_sep)
            if len(parts) == 3:
                try:
                    d, m, y = (int(p) for p in parts)
                    dob = date(y, m, d)
                    break
                except ValueError:
                    continue
    if dob is None:
        return None
    dob_date = dob if isinstance(dob, date) else dob.date()
    age = reference_date.year - dob_date.year - (
        (reference_date.month, reference_date.day) < (dob_date.month, dob_date.day)
    )
    return age


def age_to_band(age) -> str | None:
    if age is None or (isinstance(age, float) and pd.isna(age)):
        return None
    for low, high, label in AGE_BANDS:
        if low <= age <= high:
            return label
    return None


def anonymize_dataframe(
    df: pd.DataFrame, reference_date: date, salt_file: str = SALT_FILE_DEFAULT
) -> pd.DataFrame:
    salt = get_or_create_salt(salt_file)
    out = df.copy()
    out["student_pseudo"] = out["student_code"].apply(lambda c: pseudonymize_code(c, salt))
    out["age"] = out["dob_raw"].apply(lambda d: dob_to_age(d, reference_date))
    out["tranche_age"] = out["age"].apply(age_to_band)

    pii_columns = ["id_interne", "student_code", "nom_complet", "dob_raw", "age"]
    out = out.drop(columns=[c for c in pii_columns if c in out.columns])

    cols = ["student_pseudo", "tranche_age"] + [
        c for c in out.columns if c not in ("student_pseudo", "tranche_age")
    ]
    return out[cols]


def assert_no_pii(df: pd.DataFrame) -> None:
    forbidden = {"id_interne", "student_code", "nom_complet", "dob_raw", "age"}
    leaked = forbidden & set(df.columns)
    if leaked:
        raise ValueError(f"Colonnes PII résiduelles détectées après anonymisation : {leaked}")
