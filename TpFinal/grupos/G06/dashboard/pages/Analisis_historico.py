
# G06 - Análisis Histórico
# Análisis de la evolución de las condiciones climáticas.
# La información se consulta desde la capa Gold del warehouse.

import streamlit as st
import pandas as pd
import plotly.express as px
from db import leer
from tema import aplicar_tema

aplicar_tema()


# CONFIGURACIÓN VISUAL DE LOS GRÁFICOS

def configurar_grafico(fig):
    fig.update_layout(
        paper_bgcolor="#F6F7F3",
        plot_bgcolor="#FFFFFF",
        font=dict(
            family="DM Sans",
            color="#343A35",
            size=13
        ),
        title=dict(
            font=dict(
                family="DM Sans",
                color="#344E41",
                size=19
            )
        ),
        legend=dict(
            font=dict(color="#343A35", size=12),
            title_font=dict(color="#343A35")
        ),
        xaxis=dict(
            color="#343A35",
            tickfont=dict(color="#343A35", size=12),
            title_font=dict(color="#344E41"),
            showgrid=False,
            linecolor="#DCE3DA"
        ),
        yaxis=dict(
            color="#343A35",
            tickfont=dict(color="#343A35", size=12),
            title_font=dict(color="#344E41"),
            gridcolor="#E1E6DE",
            linecolor="#DCE3DA"
        )
    )

    fig.update_xaxes(
        tickfont=dict(color="#343A35", size=12),
        title_font=dict(color="#344E41")
    )

    fig.update_yaxes(
        tickfont=dict(color="#343A35", size=12),
        title_font=dict(color="#344E41")
    )

    fig.update_traces(
        selector=dict(type="bar"),
        textfont=dict(color="#343A35", size=12)
    )

    return fig


# ENCABEZADO

st.title("📊 Análisis Histórico del Clima")
st.caption("TP Final G06 - Infraestructura para Ciencia de Datos")

st.markdown(
    "Explorá la evolución climática de los destinos analizados "
    "y compará sus condiciones a lo largo del tiempo."
)

st.divider()


# FILTROS

st.subheader("Filtros de análisis")

destinos = ["Purmamarca", "Bariloche", "Puerto Iguazú"]
anios = list(range(2021, 2027))

col1, col2 = st.columns(2)

with col1:
    destino = st.selectbox(
        "Seleccioná un destino",
        destinos
    )

with col2:
    periodo = st.selectbox(
        "Período",
        ["Todos los años"] + [str(anio) for anio in anios]
    )

if periodo == "Todos los años":
    anios_seleccionados = anios
else:
    anios_seleccionados = [int(periodo)]

st.divider()


# DATOS DE DEMOSTRACIÓN

def crear_demo_historico():
    valores = {
        "Purmamarca": {
            "temperaturas": [24, 23, 21, 18, 15, 12, 11, 13, 16, 19, 21, 23],
            "lluvias": [120, 110, 95, 60, 30, 15, 10, 15, 25, 45, 80, 105],
            "agradables": [65, 68, 72, 78, 82, 88, 90, 88, 85, 80, 72, 66]
        },
        "Bariloche": {
            "temperaturas": [18, 17, 14, 10, 7, 4, 3, 5, 8, 11, 14, 17],
            "lluvias": [60, 55, 50, 45, 40, 35, 30, 35, 40, 50, 55, 65],
            "agradables": [90, 88, 78, 65, 52, 38, 30, 35, 48, 62, 75, 85]
        },
        "Puerto Iguazú": {
            "temperaturas": [27, 27, 25, 22, 19, 17, 17, 19, 21, 23, 25, 27],
            "lluvias": [180, 170, 150, 120, 90, 70, 60, 75, 100, 130, 160, 190],
            "agradables": [48, 55, 65, 78, 85, 90, 92, 90, 82, 70, 58, 48]
        }
    }

    filas = []

    nombres_meses = [
        "Enero", "Febrero", "Marzo", "Abril",
        "Mayo", "Junio", "Julio", "Agosto",
        "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    for nombre_destino, datos in valores.items():
        for anio in anios:
            variacion = (anio - 2023) * 0.3

            for mes_numero in range(1, 13):
                filas.append({
                    "destino": nombre_destino,
                    "anio": anio,
                    "mes": mes_numero,
                    "nombre_mes": nombres_meses[mes_numero - 1],
                    "temperatura_media": (
                        datos["temperaturas"][mes_numero - 1] + variacion
                    ),
                    "precipitaciones": (
                        datos["lluvias"][mes_numero - 1]
                        + (anio - 2023) * 3
                    ),
                    "pct_dias_agradables": (
                        datos["agradables"][mes_numero - 1]
                    )
                })

    return pd.DataFrame(filas)


def obtener_datos():
    datos = leer(
        """
        SELECT
            c.destino,
            t.anio,
            t.mes,
            t.nombre_mes,
            AVG(f.temperatura_media) AS temperatura_media,
            SUM(f.precipitacion_mm) AS precipitaciones,
            AVG(
                CASE
                    WHEN f.es_dia_agradable THEN 100.0
                    ELSE 0.0
                END
            ) AS pct_dias_agradables
        FROM gold.fact_clima_diario f
        INNER JOIN gold.dim_ciudad c
            ON f.ciudad_id = c.ciudad_id
        INNER JOIN gold.dim_tiempo t
            ON f.fecha = t.fecha
        GROUP BY
            c.destino,
            t.anio,
            t.mes,
            t.nombre_mes
        ORDER BY
            c.destino,
            t.anio,
            t.mes
        """
    )

    if datos is not None and not datos.empty:
        return datos, True

    return crear_demo_historico(), False


datos, datos_reales = obtener_datos()

if not datos_reales:
    st.warning(
        "Modo demostración: los gráficos utilizan datos ficticios. "
        "Se reemplazarán automáticamente cuando se carguen los datos en Gold."
    )


# PREPARACIÓN DE LOS DATOS

datos_destino = datos[
    (datos["destino"] == destino) &
    (datos["anio"].isin(anios_seleccionados))
].copy()

datos_destinos = datos[
    datos["anio"].isin(anios_seleccionados)
].copy()

orden_meses_espanol = [
    "Enero", "Febrero", "Marzo", "Abril",
    "Mayo", "Junio", "Julio", "Agosto",
    "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

nombres_espanol = {
    "January": "Enero",
    "February": "Febrero",
    "March": "Marzo",
    "April": "Abril",
    "May": "Mayo",
    "June": "Junio",
    "July": "Julio",
    "August": "Agosto",
    "September": "Septiembre",
    "October": "Octubre",
    "November": "Noviembre",
    "December": "Diciembre"
}

datos_destino["nombre_mes"] = datos_destino["nombre_mes"].replace(
    nombres_espanol
)

datos_destinos["nombre_mes"] = datos_destinos["nombre_mes"].replace(
    nombres_espanol
)


# INDICADORES GENERALES

st.subheader(f"Resumen climático — {destino}")

if not datos_destino.empty:

    temperatura_promedio = datos_destino["temperatura_media"].mean()
    lluvia_promedio = datos_destino["precipitaciones"].mean()
    agradables_promedio = datos_destino["pct_dias_agradables"].mean()

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Temperatura media",
        f"{temperatura_promedio:.1f} °C"
    )

    col2.metric(
        "Precipitación mensual promedio",
        f"{lluvia_promedio:.1f} mm"
    )

    col3.metric(
        "Días agradables",
        f"{agradables_promedio:.1f}%"
    )

else:
    st.info("No hay datos disponibles para los filtros seleccionados.")


st.divider()


# EVOLUCIÓN DE TEMPERATURAS

st.subheader("Evolución de la temperatura")

if not datos_destino.empty:

    temperatura_anual = (
        datos_destino.groupby("anio", as_index=False)
        .agg(temperatura_media=("temperatura_media", "mean"))
    )

    fig_temperatura = px.line(
        temperatura_anual,
        x="anio",
        y="temperatura_media",
        markers=True,
        title=f"Temperatura media anual — {destino}",
        labels={
            "anio": "Año",
            "temperatura_media": "Temperatura media (°C)"
        }
    )

    fig_temperatura.update_traces(
        line_color="#477A50",
        marker_color="#344E41",
        marker_size=9
    )

    fig_temperatura.update_xaxes(
        tickmode="linear",
        dtick=1
    )

    fig_temperatura = configurar_grafico(fig_temperatura)

    st.plotly_chart(
        fig_temperatura,
        use_container_width=True,
        theme=None
    )


# PRECIPITACIONES MENSUALES

st.subheader("Comportamiento de las precipitaciones")

if not datos_destino.empty:

    fig_precipitaciones = px.bar(
        datos_destino,
        x="nombre_mes",
        y="precipitaciones",
        color="anio",
        barmode="group",
        title=f"Precipitaciones mensuales — {destino}",
        labels={
            "nombre_mes": "Mes",
            "precipitaciones": "Precipitaciones (mm)",
            "anio": "Año"
        },
        category_orders={
            "nombre_mes": orden_meses_espanol
        }
    )

    fig_precipitaciones = configurar_grafico(fig_precipitaciones)

    st.plotly_chart(
        fig_precipitaciones,
        use_container_width=True,
        theme=None
    )


# PORCENTAJE DE DÍAS AGRADABLES

st.subheader("Frecuencia de días agradables")

if not datos_destino.empty:

    agradables_anuales = (
        datos_destino.groupby("anio", as_index=False)
        .agg(pct_dias_agradables=("pct_dias_agradables", "mean"))
    )

    fig_agradables = px.bar(
        agradables_anuales,
        x="anio",
        y="pct_dias_agradables",
        text="pct_dias_agradables",
        title=f"Porcentaje de días agradables — {destino}",
        labels={
            "anio": "Año",
            "pct_dias_agradables": "Días agradables (%)"
        }
    )

    fig_agradables.update_traces(
        marker_color="#75866A",
        texttemplate="%{text:.1f}%",
        textposition="outside",
        textfont=dict(color="#343A35", size=12)
    )

    fig_agradables.update_yaxes(range=[0, 110])

    fig_agradables = configurar_grafico(fig_agradables)

    st.plotly_chart(
        fig_agradables,
        use_container_width=True,
        theme=None
    )


# COMPARACIÓN ENTRE DESTINOS

st.divider()
st.subheader("Comparación histórica entre destinos")

if not datos_destinos.empty:

    comparacion = (
        datos_destinos.groupby("destino", as_index=False)
        .agg(
            temperatura_media=("temperatura_media", "mean"),
            precipitaciones=("precipitaciones", "mean"),
            pct_dias_agradables=("pct_dias_agradables", "mean")
        )
    )

    fig_comparacion = px.bar(
        comparacion,
        x="destino",
        y="pct_dias_agradables",
        color="destino",
        text="pct_dias_agradables",
        title="Porcentaje promedio de días agradables por destino",
        labels={
            "destino": "Destino",
            "pct_dias_agradables": "Días agradables (%)"
        }
    )

    fig_comparacion.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
        textfont=dict(color="#343A35", size=12)
    )

    fig_comparacion.update_yaxes(range=[0, 110])

    fig_comparacion = configurar_grafico(fig_comparacion)

    st.plotly_chart(
        fig_comparacion,
        use_container_width=True,
        theme=None
    )

    st.markdown("**Resumen comparativo**")

    tabla = comparacion.rename(columns={
        "destino": "Destino",
        "temperatura_media": "Temperatura media (°C)",
        "precipitaciones": "Precipitación mensual promedio (mm)",
        "pct_dias_agradables": "Días agradables (%)"
    })

    st.dataframe(
        tabla.round(1),
        use_container_width=True,
        hide_index=True
    )

else:
    st.info("No hay datos suficientes para comparar los destinos.")


# ACLARACIÓN FINAL

st.caption(
    "El análisis histórico permite identificar patrones climáticos "
    "y comparar las condiciones de los destinos. "
    "Los resultados no constituyen un pronóstico meteorológico."
)
