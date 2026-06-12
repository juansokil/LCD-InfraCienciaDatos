import streamlit as st
import pandas as pd
from db import get_engine
import plotly.express as px

st.set_page_config(page_title="Condiciones Actuales", page_icon="🌡️", layout="wide")
st.title("🌡️ Condiciones Actuales por Provincia")
st.caption("Última medición disponible en Gold — actualización horaria")

@st.cache_data(ttl=3600)
def cargar_datos():
    engine = get_engine()
    query = """
        SELECT
            p.nombre_provincia,
            f.fecha,
            f.temp_promedio_c,
            f.temp_max_real_c,
            f.temp_min_real_c,
            f.lluvia_total_mm,
            f.confort_termico,
            w.descripcion   AS condicion,
            w.categoria,
            w.es_alerta
        FROM gold.fact_clima_diario f
        JOIN gold.dim_provincia    p ON f.id_provincia  = p.id_provincia
        JOIN gold.dim_weather_code w ON (
            SELECT weather_code
            FROM silver.clima_actual s
            WHERE s.id_provincia = f.id_provincia
              AND DATE(s.fecha_hora) = f.fecha
            ORDER BY s.fecha_hora DESC
            LIMIT 1
        ) = w.code
        WHERE f.fecha = (SELECT MAX(fecha) FROM gold.fact_clima_diario)
        ORDER BY f.temp_promedio_c DESC
    """
    return pd.read_sql(query, engine)

df = cargar_datos()

if df.empty:
    st.warning("Sin datos disponibles. Verificá que el pipeline esté corriendo.")
    st.stop()

st.subheader(f"📅 {df['fecha'].iloc[0].strftime('%d de %B de %Y')}")
cols = st.columns(5)

for i, row in df.iterrows():
    alerta = "🚨" if row["es_alerta"] else ""
    cols[i].metric(
        label=f"{alerta} {row['nombre_provincia']}",
        value=f"{row['temp_promedio_c']}°C",
        delta=f"Máx {row['temp_max_real_c']}° / Mín {row['temp_min_real_c']}°",
    )

st.divider()

st.subheader("Detalle por provincia")

ICONOS = {
    "despejado": "☀️", "nublado": "☁️", "niebla": "🌫️",
    "llovizna":  "🌦️", "lluvia":  "🌧️", "nieve":  "❄️",
    "tormenta":  "⛈️",
}

df["condicion_display"] = df.apply(
    lambda r: f"{ICONOS.get(r['categoria'], '')} {r['condicion']}", axis=1
)

tabla = df[[
    "nombre_provincia", "condicion_display", "confort_termico",
    "temp_promedio_c", "lluvia_total_mm"
]].copy()

tabla.columns = [
    "Provincia", "Condición", "Confort",
    "Temp. Promedio (°C)", "Lluvia Total (mm)"
]


st.dataframe(tabla, use_container_width=True, hide_index=True)

st.divider()
st.subheader("🕐 Evolución horaria de hoy")

@st.cache_data(ttl=1800)
def cargar_horario():
    engine = get_engine()
    query = """
        SELECT
            p.nombre_provincia,
            s.fecha_hora,
            s.temperatura_c,
            s.sensacion_termica_c,
            s.lluvia_mm
        FROM silver.clima_actual s
        JOIN gold.dim_provincia p ON s.id_provincia = p.id_provincia
        WHERE DATE(s.fecha_hora) = (
            SELECT MAX(DATE(fecha_hora)) FROM silver.clima_actual
        )
        ORDER BY s.fecha_hora
    """
    return pd.read_sql(query, engine)

df_horario = cargar_horario()

if not df_horario.empty:
    fig_horario = px.line(
        df_horario,
        x="fecha_hora",
        y="temperatura_c",
        color="nombre_provincia",
        markers=True,
        labels={
            "fecha_hora":      "Hora",
            "temperatura_c":   "Temperatura (°C)",
            "nombre_provincia": "Provincia",
        },
    )
    fig_horario.update_layout(
        hovermode="x unified",
        margin=dict(t=20),
        xaxis_title="Hora del día",
    )
    st.plotly_chart(fig_horario, use_container_width=True)

    resumen = df_horario.groupby("nombre_provincia").agg(
        registros    =("temperatura_c", "count"),
        temp_min     =("temperatura_c", "min"),
        temp_max     =("temperatura_c", "max"),
        lluvia_total =("lluvia_mm",     "sum"),
    ).reset_index()
    resumen.columns = [
        "Provincia", "Mediciones hoy",
        "Mín (°C)", "Máx (°C)", "Lluvia (mm)"
    ]
    st.dataframe(resumen, use_container_width=True, hide_index=True)
else:
    st.info("Todavía no hay datos horarios para hoy.")