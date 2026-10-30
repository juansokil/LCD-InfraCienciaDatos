"""
Data contract de CityBikes: lectura del YAML + evaluador de `quality_rules`.
"""

from __future__ import annotations

import os

import yaml


def load_contract(path: str | os.PathLike) -> dict:
    """Lee y parsea un contrato YAML."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class ReglaDesconocida(ValueError):
    """Regla del YAML que no esta en _REGLAS. Falla ruidosamente: una regla
    que no se aplica en silencio vuelve decorativo al contrato."""


# Cada regla devuelve una MASCARA booleana: True = esa fila VIOLA la regla.
# Los nulos no violan reglas de comparacion: eso lo reporta `not_null`.

def _r_not_null(df, r):
    return df[r["column"]].isna()


def _r_non_negative(df, r):
    import pandas as pd
    s = pd.to_numeric(df[r["column"]], errors="coerce")
    return s.notna() & (s < 0)


def _r_unique(df, r):
    """De CONJUNTO: marca todas las filas de cada combinacion repetida."""
    return df.duplicated(subset=r["columns"], keep=False)


def _r_in_set(df, r):
    return df[r["column"]].notna() & ~df[r["column"]].isin(set(r["values"]))


def _r_fresh(df, r):
    """Atraso del dato EN LA CAPTURA (compared_to), no contra el reloj de ahora."""
    import pandas as pd
    ts = pd.to_datetime(df[r["column"]], errors="coerce", utc=True)
    ref = pd.to_datetime(df[r["compared_to"]], errors="coerce", utc=True)
    atraso_min = (ref - ts).dt.total_seconds() / 60
    return ts.notna() & ref.notna() & (atraso_min > float(r["max_age_minutes"]))


_REGLAS = {
    "not_null": _r_not_null,
    "non_negative": _r_non_negative,
    "unique": _r_unique,
    "in_set": _r_in_set,
    "fresh": _r_fresh,
}

SEVERIDADES = ("error", "warning")


def nombre_regla(r: dict) -> str:
    """Etiqueta estable para reportar la regla."""
    if r.get("name"):
        return r["name"]
    objetivo = r.get("column") or ",".join(r.get("columns", []))
    return f"{r['rule']}:{objetivo}"


def evaluar_reglas(df, contract: dict) -> list[dict]:
    """Aplica las `quality_rules` del contrato sobre un DataFrame.

    Devuelve un dict por regla: {"nombre", "rule", "severidad", "violaciones",
    "filas", "mask"}. El llamador decide que hacer con cada severidad
    (error -> cuarentena, warning -> pasa marcado).
    """
    import pandas as pd

    resultados = []
    for r in contract.get("quality_rules", []) or []:
        if r.get("rule") not in _REGLAS:
            raise ReglaDesconocida(
                f"regla '{r.get('rule')}' no implementada. Conocidas: {sorted(_REGLAS)}"
            )
        sev = r.get("severity", "error")
        if sev not in SEVERIDADES:
            raise ReglaDesconocida(f"severidad '{sev}' invalida en '{nombre_regla(r)}'")
        mask = pd.Series([], dtype=bool) if df.empty else _REGLAS[r["rule"]](df, r).fillna(False)
        resultados.append({
            "nombre": nombre_regla(r),
            "rule": r["rule"],
            "severidad": sev,
            "violaciones": int(mask.sum()),
            "filas": int(len(df)),
            "mask": mask,
        })
    return resultados
