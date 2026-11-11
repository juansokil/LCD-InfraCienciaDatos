"""
Data contract de CityBikes: lectura del YAML + modelo Pydantic por fila +
evaluador de `quality_rules`.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Optional

import yaml


def load_contract(path: str | os.PathLike) -> dict:
    """Lee y parsea un contrato YAML."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# Tipo del YAML -> tipo de Python. Pydantic convierte al validar: bronze guarda
# todo como texto y de aca sale tipado ("12" -> 12, "True" -> True).
_TYPE_MAP = {
    "integer": int,
    "string": str,
    "numeric": float,
    "float": float,
    "date": date,
    "timestamp": datetime,
    "boolean": bool,
}

# Regla del YAML (`rules:` de cada columna) -> argumento de pydantic.Field
_FIELD_RULE_MAP = {
    "gt": "gt",
    "ge": "ge",
    "lt": "lt",
    "le": "le",
    "min_length": "min_length",
    "max_length": "max_length",
    "regex": "pattern",
}


def build_pydantic_from_contract(contract: dict, model_name: str | None = None):
    """Arma un modelo Pydantic a partir del `schema` del contrato.

    Cada columna del YAML pasa a ser un campo:
        type     -> tipo de Python
        nullable -> Optional[T] con default None; si no, campo obligatorio
        rules    -> restricciones de pydantic.Field (ge, le, ...)

    Devuelve la CLASE. Silver la usa fila por fila:
        Contrato = build_pydantic_from_contract(contract)
        Contrato(**fila)   # lanza ValidationError si la fila no cumple

    Valida UNA fila contra si misma (tipos y rangos). Lo que necesita mirar
    el lote entero (unique, fresh) va por `evaluar_reglas`.
    """
    from pydantic import Field, create_model  # lazy: bronze no lo necesita

    name = model_name or f"{contract.get('dataset', 'Contract').title()}Contract"
    fields: dict[str, tuple[Any, Any]] = {}

    for col in contract.get("schema", []) or []:
        col_name = col["name"]
        yaml_type = col.get("type", "string")
        if yaml_type not in _TYPE_MAP:
            raise ValueError(f"tipo '{yaml_type}' desconocido en columna '{col_name}'")
        py_type = _TYPE_MAP[yaml_type]

        rules = col.get("rules", {}) or {}
        desconocidas = sorted(set(rules) - set(_FIELD_RULE_MAP))
        if desconocidas:
            # Mismo criterio que ReglaDesconocida: nada se ignora en silencio.
            raise ValueError(f"rules {desconocidas} no soportadas en columna '{col_name}'")
        field_kwargs = {_FIELD_RULE_MAP[k]: v for k, v in rules.items()}

        if col.get("nullable", False):
            fields[col_name] = (Optional[py_type], Field(col.get("default"), **field_kwargs))
        else:
            fields[col_name] = (py_type, Field(..., **field_kwargs))

    return create_model(name, **fields)


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
