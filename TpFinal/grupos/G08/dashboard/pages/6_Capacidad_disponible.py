import pandas as pd
import plotly.express as px
import streamlit as st

from db import run_query


UMBRAL_SNAPSHOT_MINUTOS = 15  # Tres ciclos del pipeline, que corre cada 5 minutos.

st.title("Capacidad realmente disponible")
st.caption(
    "Estado más reciente por estación: capacidad física, servicio de alquiler/devolución "
    "y frescura de los datos."
)

sql_estado = """
    WITH ultima_estacion AS (
        SELECT DISTINCT ON (s.network_id, s.station_id)
            s.network_id,
            s.station_id,
            COALESCE(s.station_name, s.name) AS station_name,
            s.snapshot_ts,
            s.source_last_updated,
            s.free_bikes,
            s.empty_slots,
            s.slots,
            s.docks_fuera_servicio,
            s.renting,
            s."returning",
            s._quality_flags,
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.snapshot_ts)) / 60.0
                AS minutos_sin_snapshot
        FROM silver.citybikes_stations s
        ORDER BY s.network_id, s.station_id, s.snapshot_ts DESC
    )
    SELECT
        u.network_id,
        u.station_id,
        u.station_name,
        z.ciudad,
        z.zona,
        z.zona_padre,
        z.zona_nivel,
        u.snapshot_ts,
        u.source_last_updated,
        u.free_bikes,
        u.empty_slots,
        u.slots,
        u.docks_fuera_servicio,
        u.renting,
        u."returning",
        u._quality_flags,
        u.minutos_sin_snapshot
    FROM ultima_estacion u
    LEFT JOIN silver.citybikes_station_zone z
      ON z.network_id = u.network_id
     AND z.station_id = u.station_id
    ORDER BY u.network_id, z.zona, u.station_name
"""

df = run_query(sql_estado)
if df.empty:
    st.info("Todavía no hay observaciones Silver para analizar.")
    st.stop()

df["minutos_sin_snapshot"] = pd.to_numeric(
    df["minutos_sin_snapshot"], errors="coerce"
).astype(float)

# Los flags vienen de las reglas de calidad Silver. Un source_last_updated nulo
# también se considera dato de operador no verificable.
df["operador_viejo_o_sin_dato"] = (
    df["_quality_flags"].fillna("").str.contains("operador_fresco", regex=False)
    | df["source_last_updated"].isna()
)
df["snapshot_reciente"] = (
    df["minutos_sin_snapshot"] <= UMBRAL_SNAPSHOT_MINUTOS
)
df["datos_confiables"] = df["snapshot_reciente"] & ~df["operador_viejo_o_sin_dato"]

redes = sorted(df["network_id"].dropna().unique())
red = st.selectbox("Red", redes, key="red_capacidad_disponible")
df_red = df[df["network_id"] == red].copy()

if red == "ecobici-buenos-aires":
    nivel = st.selectbox(
        "Desglosar CABA por",
        ["Barrio", "Comuna"],
        key="nivel_zona_capacidad",
    )
    if nivel == "Barrio":
        df_red["zona_grafico"] = df_red["zona"].where(
            df_red["zona_nivel"] == "barrio", "Sin barrio asignado"
        ).fillna("Sin barrio asignado")
    else:
        df_red["zona_grafico"] = df_red["zona_padre"].where(
            df_red["zona_nivel"] == "barrio", "Sin comuna asignada"
        ).fillna("Sin comuna asignada")
else:
    nivel = "Ciudad"
    df_red["zona_grafico"] = (
        df_red["ciudad"].fillna(df_red["zona"]).fillna("Sin ciudad asignada")
    )

# Las filas viejas siguen apareciendo en los indicadores, pero no se usan para
# afirmar que la capacidad esté disponible ahora.
capacidad_conocida = df_red["datos_confiables"] & df_red["slots"].notna()
df_red["slots_confiables"] = df_red["slots"].where(capacidad_conocida, 0).fillna(0)
df_red["bicis_retirables"] = df_red["free_bikes"].where(
    capacidad_conocida & df_red["renting"].eq(True), 0
).fillna(0)
df_red["anclajes_devolucion"] = df_red["empty_slots"].where(
    capacidad_conocida & df_red["returning"].eq(True), 0
).fillna(0)
df_red["anclajes_fuera_servicio"] = df_red["docks_fuera_servicio"].where(
    capacidad_conocida, 0
).fillna(0)

sin_alquiler = int(df_red["renting"].eq(False).sum())
alquiler_desconocido = int(df_red["renting"].isna().sum())
sin_snapshot = int((~df_red["snapshot_reciente"]).sum())
operador_viejo = int(df_red["operador_viejo_o_sin_dato"].sum())
anclajes_fuera = int(df_red["anclajes_fuera_servicio"].sum())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Estaciones", f"{len(df_red):,}".replace(",", "."))
k2.metric("No alquilan", f"{sin_alquiler:,}".replace(",", "."))
k3.metric("Estado de alquiler desconocido", f"{alquiler_desconocido:,}".replace(",", "."))
k4.metric(
    f"Sin snapshot > {UMBRAL_SNAPSHOT_MINUTOS} min",
    f"{sin_snapshot:,}".replace(",", "."),
)
k5.metric("Anclajes fuera de servicio¹", f"{anclajes_fuera:,}".replace(",", "."))
st.caption(
    f"Dato de operador viejo o ausente (>60 min según Silver): "
    f"{operador_viejo:,} estación(es). ¹Se cuentan anclajes reportados en estaciones "
    "con snapshot reciente, dato de operador fresco y capacidad conocida."
)

conteos_capacidad = [
    "slots_confiables",
    "bicis_retirables",
    "anclajes_devolucion",
    "anclajes_fuera_servicio",
]
por_zona = df_red.groupby("zona_grafico", as_index=False)[conteos_capacidad].sum()
denominador = por_zona["slots_confiables"].where(por_zona["slots_confiables"] > 0)
por_zona["pct_bicis_retirables"] = (
    100 * por_zona["bicis_retirables"] / denominador
)
por_zona["pct_anclajes_devolucion"] = (
    100 * por_zona["anclajes_devolucion"] / denominador
)
por_zona["pct_anclajes_fuera"] = (
    100 * por_zona["anclajes_fuera_servicio"] / denominador
)

capacidad_larga = por_zona.melt(
    id_vars=["zona_grafico", *conteos_capacidad],
    value_vars=[
        "pct_bicis_retirables",
        "pct_anclajes_devolucion",
        "pct_anclajes_fuera",
    ],
    var_name="tipo_capacidad",
    value_name="porcentaje",
).dropna(subset=["porcentaje"])
capacidad_larga["tipo_capacidad"] = capacidad_larga["tipo_capacidad"].map({
    "pct_bicis_retirables": "Bicis disponibles para retirar",
    "pct_anclajes_devolucion": "Anclajes disponibles para devolver",
    "pct_anclajes_fuera": "Anclajes fuera de servicio",
})

if capacidad_larga.empty:
    st.info("No hay capacidad instalada conocida con datos suficientemente recientes.")
else:
    orden_zonas = (
        por_zona.sort_values("slots_confiables", ascending=True)["zona_grafico"].tolist()
    )
    fig_capacidad = px.bar(
        capacidad_larga,
        x="porcentaje",
        y="zona_grafico",
        color="tipo_capacidad",
        barmode="group",
        orientation="h",
        hover_data=conteos_capacidad,
        color_discrete_map={
            "Bicis disponibles para retirar": "#2a9d8f",
            "Anclajes disponibles para devolver": "#277da1",
            "Anclajes fuera de servicio": "#d62828",
        },
        labels={
            "porcentaje": "Parte de anclajes instalados (%)",
            "zona_grafico": nivel,
            "tipo_capacidad": "Medida",
            "slots_confiables": "Anclajes instalados (datos confiables)",
            "bicis_retirables": "Bicis disponibles para retirar",
            "anclajes_devolucion": "Anclajes disponibles para devolver",
            "anclajes_fuera_servicio": "Anclajes fuera de servicio",
        },
    )
    fig_capacidad.update_xaxes(range=[0, 100], ticksuffix="%")
    fig_capacidad.update_yaxes(categoryorder="array", categoryarray=orden_zonas)
    fig_capacidad.update_layout(
        height=max(450, min(950, 32 * len(orden_zonas))),
        legend_title_text="",
    )
    st.subheader(f"Capacidad reportada por {nivel.lower()}")
    st.plotly_chart(fig_capacidad, use_container_width=True)

# La tabla separa disponibilidad física de los problemas de servicio y frescura.
tabla = por_zona.merge(
    df_red.groupby("zona_grafico", as_index=False)
    .agg(
        estaciones=("station_id", "nunique"),
        estaciones_no_alquilan=("renting", lambda valores: valores.eq(False).sum()),
        estaciones_alquiler_desconocido=("renting", lambda valores: valores.isna().sum()),
        estaciones_sin_snapshot_reciente=(
            "snapshot_reciente", lambda valores: (~valores).sum()
        ),
        estaciones_operador_viejo=("operador_viejo_o_sin_dato", "sum"),
    ),
    on="zona_grafico",
    how="left",
)
tabla = tabla.rename(columns={
    "zona_grafico": nivel,
    "slots_confiables": "Anclajes instalados con datos confiables",
    "bicis_retirables": "Bicis para retirar",
    "anclajes_devolucion": "Anclajes para devolver",
    "anclajes_fuera_servicio": "Anclajes fuera de servicio",
    "pct_bicis_retirables": "% de capacidad con bicis para retirar",
    "pct_anclajes_devolucion": "% de capacidad con anclajes para devolver",
    "pct_anclajes_fuera": "% de anclajes fuera de servicio",
    "estaciones": "Estaciones",
    "estaciones_no_alquilan": "No alquilan",
    "estaciones_alquiler_desconocido": "Alquiler desconocido",
    "estaciones_sin_snapshot_reciente": "Sin snapshot reciente",
    "estaciones_operador_viejo": "Operador viejo/sin dato",
})
st.subheader("Detalle por zona")
st.dataframe(tabla, use_container_width=True, hide_index=True)

st.caption(
    "La capacidad se calcula con estaciones que reportaron en los últimos "
    f"{UMBRAL_SNAPSHOT_MINUTOS} minutos y cuyo dato de operador tiene menos de 60 minutos. "
    "El porcentaje de bicis retirables y el de anclajes para devolver son medidas "
    "independientes; no deben sumarse. Las estaciones desactualizadas se muestran aparte "
    "porque su capacidad actual es desconocida."
)
