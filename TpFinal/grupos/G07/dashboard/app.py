"""Dashboard del Grupo G07 — Sismos USGS, sobre las tablas Gold."""
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine

st.set_page_config(page_title="USGS Sismos · G07", layout="wide")

DB_DSN = os.environ.get(
    "USGS_DB_DSN",
    "postgresql://admin:admin@postgres:5432/InfraCienciaDatos",
)


@st.cache_resource
def get_engine():
    return create_engine(DB_DSN, pool_pre_ping=True)


@st.cache_data(ttl=60)
def cargar_gold() -> pd.DataFrame:
    sql = """
        SELECT f.sismo_id,
               f.magnitud,
               f.profundidad_km,
               f.latitud,
               f.longitud,
               f.es_tsunami,
               f.cantidad,
               d.fecha,
               d.anio,
               d.mes,
               d.nombre_mes,
               d.dia_semana,
               r.nombre_region
        FROM gold.fact_sismos f
        JOIN gold.dim_fecha  d ON d.fecha_id  = f.fecha_id
        JOIN gold.dim_region r ON r.region_id = f.region_id
        ORDER BY d.fecha DESC, f.magnitud DESC
    """
    return pd.read_sql(sql, get_engine())


df = cargar_gold()

st.title("🌎 USGS Earthquakes — Grupo G07")
st.caption(
    "Arquitectura Medallion · Bronze → Silver → Gold · "
    "USGS (últimos 30 días, M2.5+)"
)

if df.empty:
    st.warning(
        "No hay datos en Gold todavía. "
        "Verificá que el pipeline (bronze → silver → gold) haya corrido."
    )
    st.stop()

# ---------------- Filtros (sidebar) ----------------
st.sidebar.header("Filtros")

fecha_min = df["fecha"].min().date()
fecha_max = df["fecha"].max().date()
rango = st.sidebar.date_input(
    "Rango de fechas",
    value=(fecha_min, fecha_max),
    min_value=fecha_min,
    max_value=fecha_max,
)
if isinstance(rango, tuple) and len(rango) == 2:
    desde, hasta = rango
else:
    desde = hasta = rango

regiones = ["Todas"] + sorted(df["nombre_region"].dropna().unique())
region_sel = st.sidebar.selectbox("Región", regiones)

mag_min, mag_max = float(df["magnitud"].min()), float(df["magnitud"].max())
mag_rango = st.sidebar.slider(
    "Magnitud",
    min_value=mag_min,
    max_value=mag_max,
    value=(mag_min, mag_max),
    step=0.1,
)

# ---------------- Filtrado ----------------
mask = (
    (df["fecha"].dt.date >= desde)
    & (df["fecha"].dt.date <= hasta)
    & (df["magnitud"] >= mag_rango[0])
    & (df["magnitud"] <= mag_rango[1])
)
if region_sel != "Todas":
    mask &= df["nombre_region"] == region_sel

dff = df[mask].copy()

# ---------------- KPIs ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Sismos", f"{len(dff):,}")
c2.metric(
    "Magnitud promedio",
    f"{dff['magnitud'].mean():.2f}" if len(dff) else "-",
)
c3.metric(
    "Magnitud máxima",
    f"{dff['magnitud'].max():.2f}" if len(dff) else "-",
)
c4.metric("Con tsunami", f"{int(dff['es_tsunami'].sum()):,}")

# ---------------- Serie diaria ----------------
st.subheader("Sismos por día")
por_dia = (
    dff.groupby("fecha").size().reset_index(name="sismos").sort_values("fecha")
)
if not por_dia.empty:
    fig = px.bar(
        por_dia,
        x="fecha",
        y="sismos",
        labels={"fecha": "Fecha", "sismos": "Sismos"},
        color_discrete_sequence=["#c0392b"],
    )
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)

# ---------------- Distribución + top regiones ----------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Distribución de magnitudes")
    if not dff.empty:
        fig = px.histogram(
            dff,
            x="magnitud",
            nbins=25,
            labels={"magnitud": "Magnitud"},
            color_discrete_sequence=["#c0392b"],
        )
        fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Top 10 regiones")
    top = (
        dff.groupby("nombre_region")
        .size()
        .reset_index(name="sismos")
        .sort_values("sismos", ascending=False)
        .head(10)
    )
    if not top.empty:
        fig = px.bar(
            top,
            x="sismos",
            y="nombre_region",
            orientation="h",
            labels={"sismos": "Sismos", "nombre_region": "Región"},
            color_discrete_sequence=["#2c3e50"],
        )
        fig.update_layout(
            yaxis=dict(autorange="reversed"),
            margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

# ---------------- Mapa ----------------
st.subheader("Mapa de sismos")
mapa = dff.dropna(subset=["latitud", "longitud"])
if not mapa.empty:
    fig = px.scatter_geo(
        mapa,
        lat="latitud",
        lon="longitud",
        color="magnitud",
        size="magnitud",
        hover_name="nombre_region",
        hover_data={
            "sismo_id": True,
            "profundidad_km": True,
            "fecha": "|%Y-%m-%d",
            "magnitud": ":.2f",
        },
        color_continuous_scale="Reds",
        projection="natural earth",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=520)
    st.plotly_chart(fig, use_container_width=True)

# ---------------- Tabla ----------------
st.subheader("Últimos 20 sismos")
tabla = (
    dff[["fecha", "nombre_region", "magnitud", "profundidad_km", "es_tsunami"]]
    .sort_values("fecha", ascending=False)
    .head(20)
)
st.dataframe(tabla, use_container_width=True, hide_index=True)

st.caption(
    f"Fuente: gold.fact_sismos + dim_fecha + dim_region · "
    f"{len(df):,} sismos en total · Actualización: cada corrida del pipeline"
)