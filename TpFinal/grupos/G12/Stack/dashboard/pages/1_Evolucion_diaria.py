"""
Evolución diaria — ¿cómo cambia la actividad sísmica día a día?

Lee la estrella de Gold: gold.fact_sismos_diarios JOIN gold.dim_region.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from db import JOULES_POR_TON_TNT, boton_actualizar, exigir_gold, run_query

st.set_page_config(page_title="G12 · Evolución diaria", page_icon="📈", layout="wide")
boton_actualizar()
st.title("📈 Evolución diaria")
st.caption("Fuente: `gold.fact_sismos_diarios` ⋈ `gold.dim_region`")

exigir_gold()

fact = run_query(
    """
    SELECT f.event_date, r.region, f.cantidad_sismos, f.magnitud_promedio,
           f.magnitud_maxima, f.energia_total_joules, f.alertas_tsunami
    FROM gold.fact_sismos_diarios f
    JOIN gold.dim_region r USING (region_id)
    """
)
fact["event_date"] = pd.to_datetime(fact["event_date"])

# --- Filtros ------------------------------------------------------------------
st.sidebar.header("Filtros")
desde, hasta = fact["event_date"].min().date(), fact["event_date"].max().date()
rango = st.sidebar.date_input("Período", value=(desde, hasta), min_value=desde, max_value=hasta)
# Mientras el usuario elige, date_input devuelve una sola fecha.
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    desde, hasta = rango

regiones_por_actividad = (
    fact.groupby("region")["cantidad_sismos"].sum().sort_values(ascending=False).index.tolist()
)
elegidas = st.sidebar.multiselect(
    "Regiones (vacío = todas)", regiones_por_actividad, placeholder="Todas las regiones"
)

filtro = fact["event_date"].between(pd.Timestamp(desde), pd.Timestamp(hasta))
if elegidas:
    filtro &= fact["region"].isin(elegidas)
datos = fact[filtro]

if datos.empty:
    st.warning("No hay sismos para ese filtro. Probá con otro período o más regiones.")
    st.stop()

# --- KPIs del filtro ----------------------------------------------------------
dias = datos["event_date"].nunique()
total = int(datos["cantidad_sismos"].sum())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Sismos", f"{total:,}".replace(",", "."))
c2.metric("Promedio por día", f"{total / dias:.1f}")
c3.metric("Magnitud máxima", f"{datos['magnitud_maxima'].max():.1f}")
c4.metric("Alertas de tsunami", int(datos["alertas_tsunami"].sum()))

# --- Serie diaria -------------------------------------------------------------
# La magnitud promedio del día se pondera por cantidad de sismos de cada región:
# promediar los promedios le daria el mismo peso a una region con 1 sismo que
# a otra con 50.
datos = datos.assign(_suma_mag=datos["magnitud_promedio"] * datos["cantidad_sismos"])
por_dia = (
    datos.groupby("event_date")
    .agg(
        sismos=("cantidad_sismos", "sum"),
        magnitud_maxima=("magnitud_maxima", "max"),
        _suma_mag=("_suma_mag", "sum"),
        energia=("energia_total_joules", "sum"),
    )
    .reset_index()
)
por_dia["magnitud_promedio"] = por_dia["_suma_mag"] / por_dia["sismos"]
por_dia["energia_t_tnt"] = por_dia["energia"] / JOULES_POR_TON_TNT

izq, der = st.columns(2)
with izq:
    st.subheader("Sismos por día")
    fig = px.bar(por_dia, x="event_date", y="sismos", labels={"event_date": "Fecha", "sismos": "Sismos"})
    st.plotly_chart(fig, use_container_width=True)
with der:
    st.subheader("Magnitud por día")
    fig = px.line(
        por_dia.melt(
            id_vars="event_date",
            value_vars=["magnitud_maxima", "magnitud_promedio"],
            var_name="medida",
            value_name="magnitud",
        ).replace({"magnitud_maxima": "Máxima", "magnitud_promedio": "Promedio"}),
        x="event_date",
        y="magnitud",
        color="medida",
        markers=True,
        labels={"event_date": "Fecha", "magnitud": "Magnitud", "medida": ""},
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Energía liberada por día")
st.caption(
    "En toneladas de TNT equivalentes, escala logarítmica: cada punto de magnitud "
    "libera unas 32 veces más energía, así que un solo sismo grande domina el día."
)
fig = px.bar(
    por_dia,
    x="event_date",
    y="energia_t_tnt",
    log_y=True,
    labels={"event_date": "Fecha", "energia_t_tnt": "t TNT"},
)
st.plotly_chart(fig, use_container_width=True)

# --- Qué regiones explican la actividad ---------------------------------------
st.subheader("Qué regiones aportan los sismos de cada día")
top_n = 8
principales = regiones_por_actividad if elegidas else regiones_por_actividad[:top_n]
apilado = datos.assign(
    region=datos["region"].where(datos["region"].isin(principales), "Otras")
).groupby(["event_date", "region"], as_index=False)["cantidad_sismos"].sum()
fig = px.bar(
    apilado,
    x="event_date",
    y="cantidad_sismos",
    color="region",
    labels={"event_date": "Fecha", "cantidad_sismos": "Sismos", "region": "Región"},
)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Ver la tabla de hechos filtrada"):
    st.dataframe(
        datos.drop(columns="_suma_mag").sort_values(["event_date", "cantidad_sismos"], ascending=[False, False]),
        hide_index=True,
        use_container_width=True,
        column_config={
            "event_date": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "region": "Región",
            "cantidad_sismos": "Sismos",
            "magnitud_promedio": st.column_config.NumberColumn("Mag. prom.", format="%.2f"),
            "magnitud_maxima": st.column_config.NumberColumn("Mag. máx.", format="%.1f"),
            "energia_total_joules": st.column_config.NumberColumn("Energía (J)", format="%.2e"),
            "alertas_tsunami": "Tsunami",
        },
    )
