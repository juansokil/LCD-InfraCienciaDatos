import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from comun import ESCALA_SATURACION, selector_red, selector_tipo_dia, tasa
from db import requiere_gold, run_query

PARES_POR_HORA = 12  # Un par de snapshots consecutivos cubre 5 minutos.

st.title("Mapa de estaciones")
st.caption(
    "Cada punto es una estación, ubicada con las coordenadas que informa la API. "
    "El color muestra la métrica elegida y el tamaño, la cantidad de anclajes."
)
requiere_gold()

c1, c2 = st.columns(2)
with c1:
    red, red_nombre, _ = selector_red("red_mapa")
with c2:
    tipos_dia = selector_tipo_dia("tipo_dia_mapa")

# Etiqueta -> (columna, escala, rango, formato del hover).
METRICAS = {
    "Tiempo sin bicis (%)": ("sin_bicis_pct", ESCALA_SATURACION, (0, 100), ".1f"),
    "Tiempo sin anclajes libres (%)": ("sin_anclajes_pct", ESCALA_SATURACION, (0, 100), ".1f"),
    "Ocupación promedio (%)": ("ocupacion_pct", "RdBu", (0, 100), ".1f"),
    "Uso por hora observada (retiros + devoluciones)": ("uso_hora", "Viridis", None, ".2f"),
}
c3, c4 = st.columns(2)
with c3:
    metrica = st.selectbox("Métrica", list(METRICAS), key="metrica_mapa")
with c4:
    desde, hasta = st.slider("Franja horaria (hora local)", 0, 23, (0, 23), key="franja_mapa")

columna, escala, rango, formato = METRICAS[metrica]

df = run_query("""
    SELECT
        d.station_id,
        COALESCE(d.station_name, d.station_id) AS estacion,
        d.zona, d.zona_padre, d.zona_nivel,
        d.latitude, d.longitude, d.slots,
        sum(f.snapshots_validos)      AS snapshots_validos,
        sum(f.snapshots_sin_bicis)    AS snapshots_sin_bicis,
        sum(f.snapshots_sin_anclajes) AS snapshots_sin_anclajes,
        sum(f.ocupacion_promedio * f.snapshots_validos)
            FILTER (WHERE f.ocupacion_promedio IS NOT NULL) AS ocupacion_ponderada,
        sum(f.snapshots_validos)
            FILTER (WHERE f.ocupacion_promedio IS NOT NULL) AS snapshots_con_ocupacion,
        sum(f.pares_comparados)       AS pares,
        sum(f.retiros_estimados + f.devoluciones_estimadas) AS movimientos
    FROM gold.dim_estacion d
    JOIN gold.fact_estacion_hora f USING (network_id, station_id)
    JOIN gold.dim_fecha df USING (fecha)
    WHERE d.network_id = :red
      AND df.tipo_dia = ANY(CAST(:tipos AS text[]))
      AND f.hora BETWEEN :desde AND :hasta
      AND d.latitude IS NOT NULL AND d.longitude IS NOT NULL
    GROUP BY d.station_id, d.station_name, d.zona, d.zona_padre, d.zona_nivel,
             d.latitude, d.longitude, d.slots
""", {"red": red, "tipos": tipos_dia, "desde": desde, "hasta": hasta})
if df.empty:
    st.info("No hay estaciones con datos para esta red, días y franja horaria.")
    st.stop()

numericas = [c for c in df.columns if c not in ("station_id", "estacion", "zona", "zona_padre", "zona_nivel")]
df[numericas] = df[numericas].apply(pd.to_numeric).astype(float)

df["sin_bicis_pct"] = tasa(df["snapshots_sin_bicis"], df["snapshots_validos"])
df["sin_anclajes_pct"] = tasa(df["snapshots_sin_anclajes"], df["snapshots_validos"])
df["ocupacion_pct"] = tasa(df["ocupacion_ponderada"], df["snapshots_con_ocupacion"])
df["uso_hora"] = tasa(df["movimientos"], df["pares"] / PARES_POR_HORA) / 100
df["zona_hover"] = np.where(
    df["zona_nivel"] == "barrio",
    df["zona"].fillna("") + " · " + df["zona_padre"].fillna(""),
    df["zona"].fillna("—"),
)

# Mismo criterio que el ranking de la pagina 1: con pocos snapshots una
# estacion puede salir 0% o 100% por casualidad.
# Para el uso, como en la pagina 5, al menos una hora observada (12 pares): con
# un par suelto una estacion sale con un uso enorme y estira la escala.
base = "pares" if columna == "uso_hora" else "snapshots_validos"
piso = PARES_POR_HORA if columna == "uso_hora" else 1
tope = int(df[base].max())
if tope < piso:
    st.info("Todavía no hay suficientes snapshots para esta métrica con estos filtros.")
    st.stop()
minimo = st.slider(
    "Mínimo de snapshots observados por estación (12 ≈ 1 hora)",
    min_value=piso, max_value=max(tope, piso + 1), value=min(max(12, piso), tope),
    key=f"minimo_mapa_{piso}",
)
mostrar = df[(df[base] >= minimo) & df[columna].notna()].copy()
if mostrar.empty:
    st.info("Ninguna estación alcanza ese mínimo de snapshots.")
    st.stop()

# Tamano por anclajes; las estaciones sin dato de slots van con el tamano medio.
mostrar["tamano"] = mostrar["slots"].fillna(mostrar["slots"].median()).fillna(10).clip(lower=1)


def encuadre(lat: pd.Series, lon: pd.Series) -> tuple[dict, float]:
    """Centro y zoom aproximados para que entren todas las estaciones."""
    extension = max(lat.max() - lat.min(), lon.max() - lon.min(), 0.005)
    zoom = float(np.clip(np.log2(360 / extension) - 0.6, 3, 16))
    return {"lat": float(lat.mean()), "lon": float(lon.mean())}, zoom


centro, zoom = encuadre(mostrar["latitude"], mostrar["longitude"])
figura = px.scatter_map(
    mostrar,
    lat="latitude",
    lon="longitude",
    color=columna,
    size="tamano",
    size_max=14,
    color_continuous_scale=escala,
    range_color=rango,
    center=centro,
    zoom=zoom,
    map_style="carto-positron",
    height=650,
    custom_data=["estacion", "zona_hover", "slots", "snapshots_validos", columna],
    labels={columna: metrica},
)
figura.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
        f"{metrica}: %{{customdata[4]:{formato}}}<br>"
        "Anclajes: %{customdata[2]:.0f}<br>"
        "Snapshots válidos: %{customdata[3]:.0f}<extra></extra>"
    )
)
figura.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0})

st.subheader(f"{metrica} · {red_nombre}")
st.plotly_chart(figura, use_container_width=True)

ocultas = len(df) - len(mostrar)
st.caption(
    f"{len(mostrar)} estaciones en el mapa"
    + (f"; {ocultas} {'queda' if ocultas == 1 else 'quedan'} afuera por no llegar al "
       "mínimo de snapshots o no tener el dato." if ocultas else ".")
    + " En la ocupación, rojo = estación vacía y azul = estación llena."
    + " El uso es un mínimo (ver página 5)."
)
