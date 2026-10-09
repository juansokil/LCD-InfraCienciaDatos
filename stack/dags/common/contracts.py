"""
Data Contract loader + validador de FORMA (Bronze) + builder de Pydantic (Silver).

El mismo contrato YAML alimenta dos capas del medallion:

    contrato YAML --> load_contract()
                  |--> validate_file_shape()       (Bronze / clase03)
                  |       valida FORMA del archivo
                  |       (extension, encoding, delimiter, columnas presentes)
                  |
                  '--> build_pydantic_from_contract()  (Silver / clase04)
                          construye un BaseModel dinamico que valida
                          tipos + nullable + rules fila por fila
"""

from __future__ import annotations

import csv
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import yaml


# Mapeo de format.type del contrato -> extensiones validas
_VALID_EXTENSIONS = {
    "csv": {".csv"},
    "json": {".json"},
    "jsonl": {".jsonl", ".ndjson"},
    "parquet": {".parquet"},
    "excel": {".xlsx", ".xls"},
}


class ContractViolation(Exception):
    """Excepcion lanzada cuando un archivo no respeta el contrato.

    Atributos:
        section: seccion del contrato violada (`format`, `schema`, ...)
        rule:    regla concreta (`extension`, `encoding`, `required_columns`, ...)
        details: dict serializable con info del incumplimiento
    """

    def __init__(self, section: str, rule: str, message: str, **details: Any):
        super().__init__(message)
        self.section = section
        self.rule = rule
        self.message = message
        self.details = {"section": section, "rule": rule, "message": message, **details}


def load_contract(path: str | os.PathLike) -> dict:
    """Lee y parsea un contrato YAML."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def validate_file_shape(filepath: str | os.PathLike, contract: dict) -> None:
    """Valida la FORMA de un archivo contra un contrato.

    Lanza `ContractViolation` ante el primer incumplimiento.
    Retorna `None` si el archivo respeta la forma declarada.
    """
    fmt = contract.get("format", {})
    expected_type = fmt.get("type")
    expected_encoding = fmt.get("encoding", "utf-8")
    expected_delimiter = fmt.get("delimiter", ",")
    expected_header = fmt.get("header", True)

    schema = contract.get("schema", []) or []
    required_cols = [col["name"] for col in schema]

    evol = contract.get("evolution_policy", {}) or {}
    allow_new = evol.get("allow_new_columns", True)
    allow_missing = evol.get("allow_missing_columns", True)

    path = Path(filepath)
    ext = path.suffix.lower()

    # ---- Regla 1: extension del archivo coincide con format.type --------
    valid_exts = _VALID_EXTENSIONS.get(expected_type, set())
    if ext not in valid_exts:
        raise ContractViolation(
            section="format",
            rule="extension",
            message=f"format.type esperado '{expected_type}', recibido extension '{ext}'",
            expected_type=expected_type,
            received_extension=ext,
        )

    # ---- Regla 2: el archivo se puede abrir con el encoding declarado ---
    # (solo aplica a formatos basados en texto)
    if expected_type in {"csv", "json", "jsonl"}:
        try:
            with open(path, "r", encoding=expected_encoding) as fh:
                _ = fh.read(4096)
        except UnicodeDecodeError as e:
            raise ContractViolation(
                section="format",
                rule="encoding",
                message=f"no se pudo leer el archivo con encoding '{expected_encoding}': {e}",
                expected_encoding=expected_encoding,
            ) from e

    # ---- Reglas 3-6: especificas de CSV ---------------------------------
    if expected_type == "csv":
        with open(path, "r", encoding=expected_encoding, newline="") as fh:
            sample = fh.read(8192)
            if not sample:
                raise ContractViolation(
                    section="format",
                    rule="empty",
                    message="el archivo CSV esta vacio",
                )

            # Sniff del delimitador
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                detected_delim = dialect.delimiter
            except csv.Error:
                detected_delim = expected_delimiter  # asumimos ok si no detecta

            if detected_delim != expected_delimiter:
                raise ContractViolation(
                    section="format",
                    rule="delimiter",
                    message=f"delimiter esperado '{expected_delimiter}', detectado '{detected_delim}'",
                    expected=expected_delimiter,
                    detected=detected_delim,
                )

            # Header: leemos primera linea
            fh.seek(0)
            reader = csv.reader(fh, delimiter=expected_delimiter)
            try:
                first_row = next(reader)
            except StopIteration:
                raise ContractViolation(
                    section="format",
                    rule="empty",
                    message="el archivo CSV esta vacio",
                )

            if expected_header:
                received_cols = [c.strip() for c in first_row]

                # Columnas requeridas presentes
                missing = [c for c in required_cols if c not in received_cols]
                if missing and not allow_missing:
                    raise ContractViolation(
                        section="schema",
                        rule="required_columns",
                        message=f"faltan columnas requeridas: {missing}",
                        missing=missing,
                        received=received_cols,
                        expected=required_cols,
                    )

                # Columnas extra (si la politica las prohibe)
                extras = [c for c in received_cols if c not in required_cols]
                if extras and not allow_new:
                    raise ContractViolation(
                        section="evolution_policy",
                        rule="allow_new_columns",
                        message=f"el contrato no permite columnas nuevas, se encontraron: {extras}",
                        extras=extras,
                        received=received_cols,
                        expected=required_cols,
                    )


# =====================================================================
# Builder Pydantic dinamico (Silver / clase04)
# ---------------------------------------------------------------------
# Toma el contrato YAML y construye un BaseModel de Pydantic en runtime.
# Reemplaza al `VentaContract` hardcodeado: ahora cambiar el contrato
# (agregar columnas, ajustar reglas) NO requiere tocar el DAG.
# =====================================================================

# YAML type -> Python type
_TYPE_MAP = {
    "integer": int,
    "string": str,
    "numeric": float,
    "float": float,
    "date": date,
    "timestamp": datetime,
    "boolean": bool,
}

# YAML rule -> kwarg de pydantic.Field
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
    """Construye un BaseModel de Pydantic a partir de un contrato YAML.

    Mapea cada entrada de `contract.schema[*]` a un campo del modelo:
        - `type`     -> tipo Python (int, str, float, date, datetime, EmailStr)
        - `nullable` -> envuelve en Optional[T] y default = None (o `default:`)
        - `rules`    -> kwargs de pydantic.Field (gt, ge, min_length, ...)

    Devuelve la *clase* del modelo (no una instancia). El DAG la usa asi:

        Contract = build_pydantic_from_contract(load_contract(YAML_PATH))
        instancia = Contract(**fila)   # lanza ValidationError si no cumple

    Importacion lazy de pydantic para no obligar al modulo Bronze a tenerlo.
    """
    from pydantic import EmailStr, Field, create_model  # lazy

    name = model_name or f"{contract.get('dataset', 'Contract').title()}Contract"
    schema = contract.get("schema", []) or []

    fields: dict[str, tuple[Any, Any]] = {}

    for col in schema:
        col_name = col["name"]
        yaml_type = col.get("type", "string")
        nullable = bool(col.get("nullable", False))
        rules = col.get("rules", {}) or {}
        default = col.get("default", None)

        # Resolucion del tipo Python
        if yaml_type == "email":
            py_type = EmailStr
        elif yaml_type in _TYPE_MAP:
            py_type = _TYPE_MAP[yaml_type]
        else:
            raise ValueError(
                f"tipo YAML desconocido para columna '{col_name}': '{yaml_type}'"
            )

        # Mapeo de rules a kwargs de Field
        field_kwargs = {
            _FIELD_RULE_MAP[k]: v for k, v in rules.items() if k in _FIELD_RULE_MAP
        }

        # Construccion del campo
        if nullable:
            annotation = Optional[py_type]
            field_default = default if default is not None else None
            fields[col_name] = (annotation, Field(field_default, **field_kwargs))
        else:
            # Required: sin default, Field(...) marca obligatorio
            fields[col_name] = (py_type, Field(..., **field_kwargs))

    return create_model(name, **fields)


# =====================================================================
# Evaluador de `quality_rules` (Silver / clase04)
# ---------------------------------------------------------------------
# POR QUE ESTO EXISTE, Y NO ES OTRO CAMPO DE PYDANTIC
#
# `build_pydantic_from_contract` valida FILA POR FILA: recibe un registro y
# decide si cumple. Eso alcanza para tipos y rangos ("current_price > 0"),
# y no alcanza para nada mas:
#
#   - `unique` mira el CONJUNTO. Una fila sola nunca es duplicada.
#   - `high_24h >= low_24h` mira DOS COLUMNAS a la vez.
#   - la frescura mira la fila CONTRA EL RELOJ.
#
# Se puede meter todo en un `model_validator`, pero termina siendo un
# evaluador de reglas escondido adentro de Pydantic. Mejor tenerlo afuera y
# que se vea: esto recibe el DataFrame entero y devuelve, por regla, que filas
# la violan.
#
# POR QUE REGLAS CON NOMBRE Y NO UNA EXPRESION
#
# Seria mas corto declarar `expr: "high_24h >= low_24h"` y hacerle eval(). Y
# seria peor: un contrato con eval adentro es codigo disfrazado de
# configuracion, y ejecuta lo que sea que alguien escriba en el YAML. Las
# herramientas reales (dbt tests, Great Expectations, Soda) usan expectativas
# CON NOMBRE. Agregar una regla nueva es sumar una entrada a _REGLAS.
# =====================================================================


class ReglaDesconocida(ValueError):
    """Una `quality_rule` que el evaluador no sabe aplicar.

    Falla RUIDOSAMENTE a proposito. La version anterior descartaba en silencio
    lo que no entendia (`if k in _FIELD_RULE_MAP`), y asi es como un contrato
    se vuelve decorativo: sigue declarando reglas, el DAG sigue en verde, y
    nadie valida nada. Una regla que no se puede aplicar es un error de
    contrato, no un detalle.
    """


def _serie(df, col):
    import pandas as pd
    if col not in df.columns:
        raise ReglaDesconocida(f"la regla referencia la columna '{col}', "
                               f"que no esta en el dato")
    return pd.to_numeric(df[col], errors="coerce")


# Cada regla devuelve una MASCARA booleana: True = esta fila VIOLA la regla.
# Ojo con los nulos: `NaN > 5` es False, asi que un nulo nunca "viola" una
# regla de comparacion. Es deliberado -- la ausencia de dato la reporta
# `not_null`, no las reglas de rango. Una sola cosa por regla.

def _r_not_null(df, r):
    col = r["column"]
    return df[col].isna() if col in df.columns else _serie(df, col).isna()


def _r_positive(df, r):
    s = _serie(df, r["column"])
    return s.notna() & (s <= 0)


def _r_non_negative(df, r):
    s = _serie(df, r["column"])
    return s.notna() & (s < 0)


def _r_ordered(df, r):
    """columns: [a, b] -> se espera a <= b."""
    a, b = r["columns"]
    sa, sb = _serie(df, a), _serie(df, b)
    return sa.notna() & sb.notna() & (sa > sb)


def _r_within_columns(df, r):
    """column dentro de [min_column, max_column]."""
    s = _serie(df, r["column"])
    lo = _serie(df, r["min_column"])
    hi = _serie(df, r["max_column"])
    return s.notna() & lo.notna() & hi.notna() & ((s < lo) | (s > hi))


def _r_ratio_close(df, r):
    """column ~= producto de `equals`, con tolerancia relativa."""
    objetivo = _serie(df, r["column"])
    producto = None
    for c in r["equals"]:
        s = _serie(df, c)
        producto = s if producto is None else producto * s
    tol = float(r.get("tolerance", 0.01))
    err = (objetivo - producto).abs() / objetivo.abs()
    return objetivo.notna() & producto.notna() & (objetivo != 0) & (err > tol)


def _r_unique(df, r):
    """De CONJUNTO: marca TODAS las filas de cada combinacion repetida.

    Se marcan todas y no solo las copias: cuando hay un duplicado no se sabe
    cual es "la buena". Esa decision es de la logica de dedup, no de la
    validacion.
    """
    cols = r.get("columns") or [r["column"]]
    faltan = [c for c in cols if c not in df.columns]
    if faltan:
        raise ReglaDesconocida(f"la regla unique referencia {faltan}, "
                               f"que no estan en el dato")
    return df.duplicated(subset=cols, keep=False)


def _r_fresh(df, r):
    """El dato venia viejo DE ORIGEN cuando lo capturamos.

    `compared_to` es la clave del asunto. Si se compara contra el reloj de
    ahora, en una tabla historica TODA fila termina violando la regla por el
    solo hecho de tener dias: la de ayer "tiene 24 horas de atraso". Eso no
    mide frescura, mide antiguedad -- y la antiguedad de un snapshot viejo es
    correcta, no un defecto.

    Lo que interesa es cuanto atraso traia el dato EN EL MOMENTO DE LA CAPTURA:
    `snapshot_ts - last_updated`. Ese numero no cambia con el paso del tiempo,
    y es el que dice si la fuente nos esta dando algo actual.

    Sin `compared_to` cae a "ahora", que sirve para validar un lote recien
    ingestado pero no para revalidar historia.
    """
    import pandas as pd
    ts = pd.to_datetime(df[r["column"]], errors="coerce", utc=True)
    ref_col = r.get("compared_to")
    if ref_col:
        if ref_col not in df.columns:
            raise ReglaDesconocida(
                f"la regla fresh compara contra '{ref_col}', que no esta en el dato")
        ref = pd.to_datetime(df[ref_col], errors="coerce", utc=True)
    else:
        ref = pd.Series(pd.Timestamp.utcnow(), index=df.index)
    limite = float(r["max_age_minutes"])
    atraso_min = (ref - ts).dt.total_seconds() / 60
    return ts.notna() & ref.notna() & (atraso_min > limite)


def _r_in_set(df, r):
    permitidos = set(r["values"])
    return df[r["column"]].notna() & ~df[r["column"]].isin(permitidos)


_REGLAS = {
    "not_null": _r_not_null,
    "positive": _r_positive,
    "non_negative": _r_non_negative,
    "ordered": _r_ordered,
    "within_columns": _r_within_columns,
    "ratio_close": _r_ratio_close,
    "unique": _r_unique,
    "fresh": _r_fresh,
    "in_set": _r_in_set,
}

SEVERIDADES = ("error", "warning")


def nombre_regla(r: dict) -> str:
    """Etiqueta estable para reportar la regla (la usa quality_runs)."""
    if r.get("name"):
        return r["name"]
    objetivo = r.get("column") or ",".join(r.get("columns", []) or [])
    return f"{r['rule']}:{objetivo}" if objetivo else r["rule"]


def evaluar_reglas(df, contract: dict) -> list[dict]:
    """Aplica las `quality_rules` del contrato sobre un DataFrame.

    Devuelve una lista de dicts, uno por regla:
        {"nombre", "rule", "severidad", "violaciones", "filas", "mask"}

    `mask` es una Serie booleana alineada con `df`: True = esa fila viola.
    El llamador decide que hacer con cada severidad -- este modulo no sabe
    nada de cuarentena ni de Airflow, solo de reglas.
    """
    import pandas as pd

    resultados = []
    for r in contract.get("quality_rules", []) or []:
        tipo = r.get("rule")
        if tipo not in _REGLAS:
            raise ReglaDesconocida(
                f"regla '{tipo}' declarada en el contrato "
                f"'{contract.get('dataset')}' y no implementada. "
                f"Conocidas: {sorted(_REGLAS)}. "
                f"Agregala a _REGLAS en common/contracts.py o sacala del YAML."
            )
        sev = r.get("severity", "error")
        if sev not in SEVERIDADES:
            raise ReglaDesconocida(
                f"severidad '{sev}' invalida en la regla '{nombre_regla(r)}'. "
                f"Validas: {SEVERIDADES}"
            )
        if df.empty:
            mask = pd.Series([], dtype=bool)
        else:
            mask = _REGLAS[tipo](df, r).fillna(False)
        resultados.append({
            "nombre": nombre_regla(r),
            "rule": tipo,
            "severidad": sev,
            "violaciones": int(mask.sum()),
            "filas": int(len(df)),
            "mask": mask,
        })
    return resultados
