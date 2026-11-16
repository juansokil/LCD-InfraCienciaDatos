import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
import plotly.express as px


@st.cache_resource
def _crear_motor():
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
        host=os.environ["WAREHOUSE_HOST"],
        port=int(os.environ["WAREHOUSE_PORT"]),
        database=os.environ["WAREHOUSE_DB"],
    )
    return create_engine(url, connect_args={"connect_timeout": 5})


def _leer_gold(consulta: str) -> pd.DataFrame:
    with _crear_motor().connect() as conexion:
        return pd.read_sql_query(text(consulta), conexion)


def cargar_ultimo_pronostico() -> pd.DataFrame:
    return _leer_gold("SELECT * FROM gold.v_ultimo_pronostico")


def cargar_comparacion_ciudades() -> pd.DataFrame:
    return _leer_gold("SELECT * FROM gold.v_comparacion_ciudades")


def render_dashboard() -> None:
    st.set_page_config(page_title="Pronóstico Open-Meteo | G04", layout="wide")
    st.title("Pronóstico Open-Meteo")
    st.caption("Comparación de pronósticos para cinco ciudades argentinas · G04")

    try:
        pronostico = cargar_ultimo_pronostico()
        comparacion = cargar_comparacion_ciudades()
    except KeyError:
        st.info("La conexión con el warehouse todavía no está configurada.")
        return
    except (SQLAlchemyError, ValueError):
        st.warning("No pudimos consultar Gold. Revisá la conexión y actualizá la página.")
        return

    if pronostico.empty or comparacion.empty:
        st.info("Todavía no hay pronósticos disponibles en Gold.")
        return

    _mostrar_pronosticos(pronostico, comparacion)

def _mostrar_pronosticos(
    pronostico: pd.DataFrame,
    comparacion: pd.DataFrame,
) -> None:    
    datos = pronostico.copy()
    datos = datos.rename(columns={
    "fecha_pronostico": "fecha",
    "ciudad_nombre": "nombre",
    })
    datos["fecha"] = pd.to_datetime(datos["fecha"]).dt.date

    ciudades = sorted(datos["nombre"].unique())
    fecha_min = datos["fecha"].min()
    fecha_max = datos["fecha"].max()

    ciudades_elegidas = st.sidebar.multiselect(
        "Ciudades",
        options=ciudades,
        default=ciudades,
    )
    fechas = st.sidebar.date_input(
        "Fechas del pronóstico",
        value=(fecha_min, fecha_max),
        min_value=fecha_min,
        max_value=fecha_max,
    )

    if len(fechas) != 2:
        st.info("Elegí la fecha inicial y la fecha final.")
        return

    inicio, fin = fechas
    filtrado = datos.loc[
        datos["nombre"].isin(ciudades_elegidas)
        & datos["fecha"].between(inicio, fin)
    ].sort_values(["fecha", "nombre"])

    if filtrado.empty:
        st.info("No hay pronósticos para la selección actual.")
        return

    ultima_consulta = pd.to_datetime(
        filtrado["fecha_consulta_utc"], utc=True
    ).max()
    hora_argentina = ultima_consulta.tz_convert("America/Argentina/Buenos_Aires")
    st.caption(
        f"Última consulta de la selección · "
        f"{hora_argentina.strftime('%d/%m/%Y %H:%M')} (hora argentina)"
    )

    st.subheader("Alertas del pronóstico")
    st.caption("Umbrales del proyecto · máxima de 35 °C o más y precipitación de 20 mm o más.")

    alertas = comparacion.copy()
    alertas = alertas.rename(columns={
        "fecha_pronostico": "fecha",
        "ciudad_nombre": "nombre",
    })
    alertas["fecha"] = pd.to_datetime(alertas["fecha"]).dt.date

    if "alerta_calor" not in alertas.columns:
        alertas["alerta_calor"] = alertas["alerta_temperatura"].eq(
            "ALERTA: Calor Extremo"
    )

    if "alerta_lluvia" not in alertas.columns:
        alertas["alerta_lluvia"] = alertas["alerta_precipitacion"].eq(
            "ALERTA: Lluvias Intensas"
    )
    alertas = alertas.loc[
        alertas["nombre"].isin(ciudades_elegidas)
        & alertas["fecha"].between(inicio, fin)
        & (alertas["alerta_calor"] | alertas["alerta_lluvia"])
    ].sort_values(["fecha", "nombre"])

    if alertas.empty:
        st.info("No hay alertas para la selección actual.")
    else:
        st.dataframe(
            alertas[
                ["nombre", "fecha", "temp_max_c", "precipitacion_mm",
                 "alerta_calor", "alerta_lluvia"]
            ].rename(
                columns={
                    "nombre": "Ciudad",
                    "fecha": "Fecha",
                    "temp_max_c": "Máxima (°C)",
                    "precipitacion_mm": "Precipitación (mm)",
                    "alerta_calor": "Calor",
                    "alerta_lluvia": "Precipitación",
                }
            ),
            hide_index=True,
        )

    temperaturas = filtrado.melt(
        id_vars=["fecha", "nombre"],
        value_vars=["temp_max_c", "temp_min_c"],
        var_name="serie",
        value_name="temperatura_c",
    )
    temperaturas["serie"] = temperaturas["serie"].map(
        {"temp_max_c": "Máxima", "temp_min_c": "Mínima"}
    )

    grafico_temperaturas = px.line(
        temperaturas,
        x="fecha",
        y="temperatura_c",
        color="nombre",
        line_dash="serie",
        markers=True,
        title="Temperaturas máximas y mínimas",
        labels={
            "fecha": "Fecha del pronóstico",
            "temperatura_c": "Temperatura (°C)",
            "nombre": "Ciudad",
            "serie": "Tipo",
        },
    )
    st.plotly_chart(grafico_temperaturas, use_container_width=True)

    grafico_precipitacion = px.bar(
        filtrado,
        x="fecha",
        y="precipitacion_mm",
        color="nombre",
        barmode="group",
        title="Precipitación pronosticada por día",
        labels={
            "fecha": "Fecha del pronóstico",
            "precipitacion_mm": "Precipitación (mm)",
            "nombre": "Ciudad",
        },
    )
    st.plotly_chart(grafico_precipitacion, use_container_width=True)

    st.subheader("Ranking por temperatura máxima")

    dias_disponibles = sorted(filtrado["fecha"].unique())
    dia_ranking = st.selectbox("Día del ranking", options=dias_disponibles, format_func=lambda dia: dia.strftime("%d/%m/%Y"),)

    ranking = (filtrado.loc[filtrado["fecha"] == dia_ranking,["nombre", "temp_max_c"],].sort_values(["temp_max_c", "nombre"], ascending=[False, True]).rename(columns={"nombre": "Ciudad", "temp_max_c": "Máxima (°C)"}))
    st.dataframe(ranking, hide_index=True)

    st.subheader("Pronósticos seleccionados")
    st.dataframe(
        filtrado[
            ["nombre", "fecha", "temp_max_c", "temp_min_c", "precipitacion_mm"]
        ].rename(
            columns={
                "nombre": "Ciudad",
                "fecha": "Fecha",
                "temp_max_c": "Máxima (°C)",
                "temp_min_c": "Mínima (°C)",
                "precipitacion_mm": "Precipitación (mm)",
            }
        ),
        hide_index=True,
    )

if __name__ == "__main__":
    render_dashboard()