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
