import streamlit as st
from db import run_query
import plotly.express as px


sql_saturacion_estaciones= """
    SELECT
        network_id,
        station_id,
        station_name,
        dia_semana,
        hora,
        COUNT(*) AS snapshots_observados,
        COUNT(*) FILTER (WHERE saturada) AS snapshots_saturados,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE saturada) / NULLIF(COUNT(*), 0),
            1
        ) AS porcentaje_saturacion
    FROM gold.vw_citybikes_saturacion
    GROUP BY
        network_id,
        station_id,
        station_name,
        dia_semana,
        hora
    ORDER by
        porcentaje_saturacion desc,
        network_id,
        station_id,
        dia_semana,
        hora;
"""

df = run_query(sql_saturacion_estaciones)
if df.empty:
    st.info("Todavía no hay datos de saturación.")
    st.stop()

red = st.selectbox("Red", sorted(df["network_id"].unique()))
df_red = df[df["network_id"] == red].copy()

def crear_heatmap_saturacion(df):

    if df.empty:
        st.info("Todavía no hay datos de saturación.")
        st.stop()

    # Elegir una red para no mezclar estaciones de distintas ciudades.
    # red = st.selectbox("Red", sorted(df["network_id"].unique()))
    # df_red = df[df["network_id"] == red].copy()

    # 1. Mapa de calor: día de la semana × hora
    por_horario = (
        df_red.groupby(["dia_semana", "hora"], as_index=False)[
            ["snapshots_observados", "snapshots_saturados"]
        ]
        .sum()
    )
    por_horario["porcentaje"] = (
        100 * por_horario["snapshots_saturados"]
        / por_horario["snapshots_observados"]
    )

    dias = {
        1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves",
        5: "Viernes", 6: "Sábado", 7: "Domingo",
    }
    matriz = (
        por_horario.pivot(
            index="dia_semana", columns="hora", values="porcentaje"
        )
        .reindex(index=range(1, 8), columns=range(24))
    )
    matriz.index = [dias[d] for d in matriz.index]

    fig_calor = px.imshow(
        matriz,
        aspect="auto",
        text_auto=".1f",
        color_continuous_scale=[[0.0, "#2a9d8f"], [0.5, "#f4a261"], [1.0, "#d62828"]],
        zmin=0,
        zmax=100,
        labels={
            "x": "Hora del día",
            "y": "Día de la semana",
            "color": "Saturación (%)",
        },
    )
    return fig_calor
    

def crear_grafico_top_estaciones_saturacion(df):
    # 2. Ranking de las diez estaciones con mayor saturación
    if df.empty:
            st.info("Todavía no hay datos de saturación.")
            st.stop()
    
    # Elegir una red para no mezclar estaciones de distintas ciudades.
    # red = st.selectbox("Red", sorted(df["network_id"].unique()))
    # df_red = df[df["network_id"] == red].copy()

    por_estacion = (
        df_red.groupby(
            ["station_id", "station_name"], as_index=False
        )[["snapshots_observados", "snapshots_saturados"]]
        .sum()
    )
    por_estacion["porcentaje"] = (
        100 * por_estacion["snapshots_saturados"]
        / por_estacion["snapshots_observados"]
    )
    por_estacion["estacion"] = por_estacion["station_name"]
    # (
    #     por_estacion["station_name"] + " (" + por_estacion["station_id"] + ")"
    # )

    top10 = (
        por_estacion.nlargest(10, "porcentaje")
        .sort_values("porcentaje")
    )

    fig_estaciones = px.bar(
        top10,
        x="porcentaje",
        y="estacion",
        orientation="h",
        hover_data=["snapshots_observados", "snapshots_saturados", "station_id"],
        labels={
            "porcentaje": "Snapshots saturados (%)",
            "estacion": "Estación",
            "snapshots_observados": "Snapshots observados",
            "snapshots_saturados": "Snapshots saturados",
        },
    )
    
    fig_estaciones.update_xaxes(range=[0, 100])
    return fig_estaciones

# 1.
st.subheader("¿En qué días y horarios hay más saturación?")
st.plotly_chart(crear_heatmap_saturacion(df_red), use_container_width=True)

st.subheader("Estaciones con mayor porcentaje de saturación")
st.plotly_chart(crear_grafico_top_estaciones_saturacion(df_red), use_container_width=True)