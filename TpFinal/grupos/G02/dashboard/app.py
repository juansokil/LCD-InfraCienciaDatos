"""
Dashboard del TP Final · Open-Meteo

Regla de arquitectura: este tablero SOLO ejecuta SELECT sobre el esquema gold.
No consulta Open-Meteo ni transforma JSON: todo eso ya lo hicieron Bronze y Silver.
"""
import os
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import psycopg2
import streamlit as st

st.set_page_config(page_title="Clima en ciudades argentinas", page_icon="🌦️", layout="wide")

TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# Umbrales didácticos (los mismos que las banderas de gold.v_pronostico)
UMBRAL_CALOR, UMBRAL_FRIO, UMBRAL_LLUVIA, UMBRAL_VIENTO = 35, 0, 10, 40


# ---------------------------------------------------------------------------
# Acceso a datos
# ---------------------------------------------------------------------------
def get_connection():
    return psycopg2.connect(
        host=os.getenv("WAREHOUSE_HOST", "warehouse"),
        port=os.getenv("WAREHOUSE_PORT", "5432"),
        dbname=os.getenv("WAREHOUSE_DB", "weather_dw"),
        user=os.getenv("WAREHOUSE_USER", "weather"),
        password=os.getenv("WAREHOUSE_PASSWORD", "weather_db_password"),
        connect_timeout=5,
    )


@st.cache_data(ttl=30)
def run_query(sql: str) -> pd.DataFrame:
    with closing(get_connection()) as conn, conn.cursor() as cur:
        cur.execute(sql)
        columns = [col[0] for col in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=columns)
    # psycopg2 devuelve NUMERIC como Decimal: se pasa a float para graficar
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].astype(float)
    return df


def load_data():
    ultimo = run_query("SELECT * FROM gold.v_clima_ultimo")
    evolucion = run_query(
        """
        SELECT c.city_name, f.captured_at, f.temperature_c
        FROM gold.fact_clima_actual f
        JOIN gold.dim_ciudad c ON c.city_id = f.city_id
        ORDER BY f.captured_at
        """
    )
    pronostico = run_query("SELECT * FROM gold.v_pronostico ORDER BY city_name, full_date")
    return ultimo, evolucion, pronostico


# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
st.title("🌦️ Clima en ciudades argentinas")

try:
    ultimo, evolucion, pronostico = load_data()
except Exception as exc:  # Gold todavía no existe o la base no responde
    st.error(
        "No se pudo leer el esquema gold. Verificá que el stack esté levantado y que los DAGs "
        "open_meteo_bronze → open_meteo_silver → open_meteo_gold hayan terminado en Airflow."
    )
    st.code(str(exc))
    st.stop()

if ultimo.empty or pronostico.empty:
    st.info("Todavía no hay datos en Gold. Esperá a que terminen los tres DAGs en Airflow.")
    st.stop()

evolucion["captured_at"] = pd.to_datetime(evolucion["captured_at"], utc=True).dt.tz_convert(TZ)
ultimo["captured_at"] = pd.to_datetime(ultimo["captured_at"], utc=True).dt.tz_convert(TZ)
pronostico["full_date"] = pd.to_datetime(pronostico["full_date"])
pronostico["loaded_at"] = pd.to_datetime(pronostico["loaded_at"], utc=True).dt.tz_convert(TZ)

ultima_captura = ultimo["captured_at"].max()
ultimo_pronostico = pronostico["loaded_at"].max()
st.caption(
    f"Última captura de clima: {ultima_captura:%d/%m/%Y %H:%M} · "
    f"Último pronóstico cargado en Gold: {ultimo_pronostico:%d/%m/%Y %H:%M} (hora de Argentina)"
)

with st.expander("Contexto: El Niño y alcance de este tablero", expanded=True):
    st.markdown(
        """
**El Niño está activo.** Según el Climate Prediction Center de NOAA (informe del 12/11/2026),
hay condiciones de El Niño y se espera que se siga intensificando hasta principios de 2027.

Este tablero monitorea el **tiempo actual y el pronóstico a 7 días** de cinco ciudades argentinas
y destaca los días extremos (calor, frío, lluvia y viento).

**Alcance:** con pocos días de datos no es posible atribuir ninguno de esos eventos al fenómeno.
Para eso haría falta compararlos con promedios históricos de cada ciudad.
        """
    )

# ---------------------------------------------------------------------------
# Filtros (barra lateral)
# ---------------------------------------------------------------------------
st.sidebar.header("Filtros")
if st.sidebar.button("Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

todas = sorted(ultimo["city_name"].unique())
ciudades = st.sidebar.multiselect("Ciudades", todas, default=todas)
if not ciudades:
    st.warning("Elegí al menos una ciudad en la barra lateral.")
    st.stop()

min_f, max_f = pronostico["full_date"].min().date(), pronostico["full_date"].max().date()
hoy = datetime.now(TZ).date()
inicio_defecto = hoy if min_f <= hoy <= max_f else min_f
rango = st.sidebar.date_input(
    "Fechas del pronóstico",
    value=(inicio_defecto, max_f),
    min_value=min_f,
    max_value=max_f,
)
if isinstance(rango, (tuple, list)) and len(rango) == 2:
    desde, hasta = rango
else:  # el usuario todavía está eligiendo la segunda fecha
    desde, hasta = inicio_defecto, max_f

ultimo_f = ultimo[ultimo["city_name"].isin(ciudades)]
pron_f = pronostico[
    pronostico["city_name"].isin(ciudades)
    & (pronostico["full_date"].dt.date >= desde)
    & (pronostico["full_date"].dt.date <= hasta)
].copy()
pron_f["Fecha"] = pron_f["full_date"].dt.strftime("%d/%m/%Y")

tab1, tab2, tab3 = st.tabs(["Situación actual", "Pronóstico de 7 días", "Días destacados"])

# ---------------------------------------------------------------------------
# Pestaña 1 · Situación actual
# ---------------------------------------------------------------------------
with tab1:
    st.caption("¿Cómo están las condiciones meteorológicas ahora en las ciudades seleccionadas?")
    temps = ultimo_f.dropna(subset=["temperature_c"])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Temperatura promedio", f"{ultimo_f['temperature_c'].mean():.1f} °C")
    if not temps.empty:
        cal = temps.loc[temps["temperature_c"].idxmax()]
        fri = temps.loc[temps["temperature_c"].idxmin()]
        k2.metric("Ciudad más cálida", cal["city_name"], f"{cal['temperature_c']:.1f} °C", delta_color="off")
        k3.metric("Ciudad más fría", fri["city_name"], f"{fri['temperature_c']:.1f} °C", delta_color="off")
    k4.metric("Humedad promedio", f"{ultimo_f['humidity_pct'].mean():.0f} %")

    izq, der = st.columns(2)
    with izq:
        st.subheader("Temperatura actual por ciudad")
        fig = px.bar(
            ultimo_f, x="city_name", y="temperature_c", text_auto=".1f",
            labels={"city_name": "Ciudad", "temperature_c": "Temperatura (°C)"},
        )
        st.plotly_chart(fig, use_container_width=True)
    with der:
        st.subheader("Evolución de las capturas")
        c_min, c_max = evolucion["captured_at"].min().date(), evolucion["captured_at"].max().date()
        periodo = st.date_input("Período de capturas", value=(c_min, c_max), min_value=c_min, max_value=c_max)
        c_desde, c_hasta = periodo if isinstance(periodo, (tuple, list)) and len(periodo) == 2 else (c_min, c_max)
        evo_f = evolucion[
            evolucion["city_name"].isin(ciudades)
            & (evolucion["captured_at"].dt.date >= c_desde)
            & (evolucion["captured_at"].dt.date <= c_hasta)
        ]
        fig = px.line(
            evo_f, x="captured_at", y="temperature_c", color="city_name", markers=True,
            labels={"captured_at": "Captura", "temperature_c": "Temperatura (°C)", "city_name": "Ciudad"},
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Detalle por ciudad")
    detalle = ultimo_f.assign(Captura=ultimo_f["captured_at"].dt.strftime("%d/%m/%Y %H:%M"))[
        ["city_name", "Captura", "temperature_c", "apparent_temperature_c", "humidity_pct",
         "precipitation_mm", "wind_speed_kmh", "weather_description"]
    ].rename(columns={
        "city_name": "Ciudad", "temperature_c": "Temperatura (°C)", "apparent_temperature_c": "Sensación térmica (°C)",
        "humidity_pct": "Humedad (%)", "precipitation_mm": "Precipitación (mm)",
        "wind_speed_kmh": "Viento (km/h)", "weather_description": "Estado del tiempo",
    })
    st.dataframe(detalle, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Pestaña 2 · Pronóstico de 7 días
# ---------------------------------------------------------------------------
with tab2:
    st.caption("¿Qué diferencias se esperan entre ciudades durante la próxima semana?")
    if pron_f.empty:
        st.info("No hay pronóstico para las ciudades y fechas elegidas.")
    else:
        variable = st.radio("Temperatura a graficar", ["Máxima", "Mínima"], horizontal=True)
        col_temp = "temperature_max_c" if variable == "Máxima" else "temperature_min_c"

        izq, der = st.columns(2)
        with izq:
            st.subheader(f"Temperatura {variable.lower()} pronosticada")
            fig = px.line(
                pron_f, x="full_date", y=col_temp, color="city_name", markers=True,
                labels={"full_date": "Fecha", col_temp: "Temperatura (°C)", "city_name": "Ciudad"},
            )
            st.plotly_chart(fig, use_container_width=True)
        with der:
            st.subheader("Precipitación acumulada pronosticada")
            fig = px.bar(
                pron_f, x="full_date", y="precipitation_sum_mm", color="city_name", barmode="group",
                labels={"full_date": "Fecha", "precipitation_sum_mm": "Precipitación (mm)", "city_name": "Ciudad"},
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Pronóstico diario")
        tabla = pron_f[[
            "city_name", "Fecha", "weather_description", "temperature_max_c", "temperature_min_c",
            "precipitation_sum_mm", "wind_speed_max_kmh",
        ]].rename(columns={
            "city_name": "Ciudad", "weather_description": "Estado del tiempo",
            "temperature_max_c": "Máxima (°C)", "temperature_min_c": "Mínima (°C)",
            "precipitation_sum_mm": "Lluvia (mm)", "wind_speed_max_kmh": "Viento máx. (km/h)",
        })
        st.dataframe(tabla, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Pestaña 3 · Días destacados
# ---------------------------------------------------------------------------
def listado(titulo, mascara, columna, etiqueta):
    st.subheader(titulo)
    filas = pron_f[mascara].sort_values("full_date")
    if filas.empty:
        st.info("No se encontraron días que cumplan el criterio.")
    else:
        st.dataframe(
            filas[["city_name", "Fecha", columna]].rename(columns={"city_name": "Ciudad", columna: etiqueta}),
            use_container_width=True, hide_index=True,
        )


with tab3:
    st.caption("Días pronosticados por Open-Meteo (no son mediciones) que superan los umbrales de referencia.")
    c1, c2 = st.columns(2)
    with c1:
        listado(f"🔥 Días calurosos (máxima ≥ {UMBRAL_CALOR} °C)", pron_f["dia_caluroso"], "temperature_max_c", "Máxima (°C)")
        listado(f"🌧️ Días lluviosos (≥ {UMBRAL_LLUVIA} mm)", pron_f["dia_lluvioso"], "precipitation_sum_mm", "Lluvia (mm)")
    with c2:
        listado(f"❄️ Días fríos (mínima ≤ {UMBRAL_FRIO} °C)", pron_f["dia_frio"], "temperature_min_c", "Mínima (°C)")
        listado(f"💨 Días ventosos (viento máx. ≥ {UMBRAL_VIENTO} km/h)", pron_f["dia_ventoso"], "wind_speed_max_kmh", "Viento máx. (km/h)")
    st.caption(
        "Los umbrales son didácticos y configurables. No equivalen a alertas oficiales ni reemplazan "
        "los avisos de los organismos meteorológicos."
    )