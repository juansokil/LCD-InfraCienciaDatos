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

station_number y station_name salen de una regex: se calculan en Python, fila a
fila, al validar. Las otras tres son aritmetica sobre la fila y las calcula
Postgres con un UPDATE despues de cargar (DERIVADAS_SQL), sin pandas.
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


DERIVADAS_SQL = {
    "docks_fuera_servicio": """CASE WHEN "slots" IS NOT NULL
             THEN GREATEST("slots" - ("free_bikes" + "empty_slots"), 0) END""",
    "ocupacion": """CASE WHEN "free_bikes" + "empty_slots" > 0
             THEN "free_bikes"::double precision / ("free_bikes" + "empty_slots") END""",
    # timestamptz AT TIME ZONE zona -> timestamp sin zona, en hora local.
    "snapshot_local": '"snapshot_ts" AT TIME ZONE :tz_local',
}


def sql_derivadas(tabla: str, filtro: str) -> str:
    """UPDATE que completa las columnas de DERIVADAS_SQL en las filas del filtro.

    Necesita el parametro `tz_local` (TZ_LOCAL) ademas de los del filtro.
    """
    asignaciones = ",\n            ".join(f'"{c}" = {e}' for c, e in DERIVADAS_SQL.items())
    return f"""
        UPDATE {tabla}
        SET {asignaciones}
        WHERE {filtro}
    """
