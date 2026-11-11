"""
Columnas DERIVADAS de silver.citybikes_stations.

No vienen de la API (no estan en el contrato): silver las calcula a partir de
las del contrato para que gold no repita la cuenta.

    station_number        numero de estacion que EcoBici/Nordelta ponen al
                          principio del nombre ("001 - ADUANA" -> 1).
    station_name          nombre sin ese numero y con un solo criterio de
                          mayusculas. `name` queda tal cual vino.
    docks_fuera_servicio  slots - (free_bikes + empty_slots): anclajes que la
                          estacion tiene pero no estan disponibles.
    ocupacion             free_bikes / (free_bikes + empty_slots), sobre la
                          capacidad OPERATIVA, no sobre `slots`.
    snapshot_local        snapshot_ts en hora de Argentina (sin zona), para
                          agrupar por hora del dia y dia de la semana.
"""

from __future__ import annotations

import re

# Columna -> tipo de Postgres.
DERIVADAS = {
    "station_number": "integer",
    "station_name": "text",
    "docks_fuera_servicio": "integer",
    "ocupacion": "double precision",
    "snapshot_local": "timestamp",
}
TZ_LOCAL = "America/Argentina/Buenos_Aires"

# Palabras que van en minuscula al pasar un nombre de MAYUSCULAS a titulo,
# salvo que sean la primera.
_MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "e", "en", "a", "al",
               "por", "con", "o", "u"}
_ROMANOS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
# Siglas que aparecen en nombres de MAYUSCULAS y tienen que seguir asi.
_SIGLAS = {"uba", "uca", "uade", "utn", "itba", "pami", "heca", "ypf", "cd"}
_RE_NUMERO = re.compile(r"^\s*(\d+)\s*-\s*(.+)$")


def _a_titulo(texto: str) -> str:
    salida = []
    for i, p in enumerate(texto.lower().split()):
        if p in _ROMANOS or p in _SIGLAS:
            salida.append(p.upper())
        elif i > 0 and p in _MINUSCULAS:
            salida.append(p)
        else:
            salida.append(p.title())
    return " ".join(salida)


def nombre_estacion(nombre):
    """'001 - FACULTAD DE DERECHO' -> (1, 'Facultad de Derecho').

    Solo se cambian las mayusculas de los nombres que vienen TODO en mayuscula
    (la mitad de EcoBici). Los que ya vienen mezclados se respetan: ahi la API
    trae siglas y abreviaturas bien escritas ("Fac. de Ingeniería", "CC Echesortu").
    """
    if nombre is None:
        return None, None
    numero = None
    m = _RE_NUMERO.match(nombre)
    if m:
        numero, nombre = int(m.group(1)), m.group(2)
    nombre = " ".join(nombre.split())
    if nombre == nombre.upper() and any(ch.isalpha() for ch in nombre):
        nombre = _a_titulo(nombre)
    return numero, nombre or None


def agregar_derivadas(df):
    """Suma las columnas de DERIVADAS a un DataFrame de silver ya tipado."""
    import pandas as pd

    if df.empty:
        for col in DERIVADAS:
            df[col] = pd.Series(dtype=object)
        return df

    partes = df["name"].map(nombre_estacion)
    df["station_number"] = pd.array([p[0] for p in partes], dtype="Int64")
    df["station_name"] = [p[1] for p in partes]

    libres = pd.to_numeric(df["free_bikes"]).astype("Int64")
    vacios = pd.to_numeric(df["empty_slots"]).astype("Int64")
    slots = pd.to_numeric(df["slots"]).astype("Int64")
    operativa = libres + vacios
    df["docks_fuera_servicio"] = (slots - operativa).clip(lower=0)
    df["ocupacion"] = (libres / operativa.where(operativa > 0)).astype("Float64")

    df["snapshot_local"] = (
        pd.to_datetime(df["snapshot_ts"], utc=True)
        .dt.tz_convert(TZ_LOCAL)
        .dt.tz_localize(None)
    )
    return df
