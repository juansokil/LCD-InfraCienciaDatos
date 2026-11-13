"""Piezas de UI que comparten las paginas del dashboard."""

import pandas as pd
import streamlit as st

from db import run_query

ESCALA_SATURACION = [[0.0, "#2a9d8f"], [0.5, "#f4a261"], [1.0, "#d62828"]]
DIAS = {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves",
        5: "Viernes", 6: "Sábado", 7: "Domingo"}


def formato_entero(valor) -> str:
    return f"{int(valor):,}".replace(",", ".")


def selector_red(key: str) -> tuple[str, str, bool]:
    """Selectbox de red. Devuelve (network_id, nombre, tiene_barrios)."""
    redes = run_query("""
        SELECT network_id,
               max(red_nombre) AS red_nombre,
               bool_or(zona_nivel = 'barrio') AS tiene_barrios
        FROM gold.dim_estacion
        GROUP BY network_id
        ORDER BY network_id
    """)
    por_etiqueta = {
        f"{fila.red_nombre} ({fila.network_id})": fila.network_id
        for fila in redes.itertuples()
    }
    red = por_etiqueta[st.selectbox("Red", list(por_etiqueta), key=key)]
    fila = redes[redes["network_id"] == red].iloc[0]
    return red, fila["red_nombre"], bool(fila["tiene_barrios"])


def selector_tipo_dia(key: str) -> list[str]:
    """Filtro de dias, contra gold.dim_fecha.tipo_dia."""
    eleccion = st.selectbox("Días incluidos", ["Todos", "Días hábiles", "Fin de semana"], key=key)
    return {"Todos": ["Hábil", "Fin de semana"],
            "Días hábiles": ["Hábil"],
            "Fin de semana": ["Fin de semana"]}[eleccion]


def columna_zona(df: pd.DataFrame, tiene_barrios: bool, key: str) -> tuple[pd.DataFrame, str]:
    """Agrega `zona_grafico` segun el nivel elegido. Devuelve (df, nivel).

    Las estaciones de CABA que quedaron fuera de los poligonos tienen
    zona_nivel = 'ciudad' (fallback de silver) y se agrupan aparte.
    """
    df = df.copy()
    if tiene_barrios:
        nivel = st.selectbox("Desglosar por", ["Barrio", "Comuna"], key=key)
        columna = "zona" if nivel == "Barrio" else "zona_padre"
        df["zona_grafico"] = (
            df[columna].where(df["zona_nivel"] == "barrio")
            .fillna(f"Sin {nivel.lower()} asignado/a")
        )
    else:
        nivel = "Ciudad"
        df["zona_grafico"] = df["ciudad"].fillna(df["zona"]).fillna("Sin ciudad")
    return df, nivel


def tasa(numerador: pd.Series, denominador: pd.Series) -> pd.Series:
    """Porcentaje con denominador 0 -> NaN (celda vacia, no 0%)."""
    return 100 * numerador / denominador.where(denominador > 0)
