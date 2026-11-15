
# G06 - Semáforo del Viajero
# Visualización de condiciones climáticas históricas.
# Versión de demostración con datos ficticios.
# La versión final consultará la capa Gold del warehouse.

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

st.title("🌿 Semáforo del Viajero")
st.caption("TP Final G06 - Infraestructura para Ciencia de Datos")

st.markdown(
    "Consultá las condiciones climáticas históricas de tu próximo destino."
)
st.divider()


# SELECCIÓN DE DESTINO

destinos = {
    "Noroeste": ["Purmamarca"],
    "Patagonia": ["Bariloche"],
    "Noreste": ["Puerto Iguazú"]
}

meses_por_temporada = {
    "Verano": ["Diciembre", "Enero", "Febrero"],
    "Otoño": ["Marzo", "Abril", "Mayo"],
    "Invierno": ["Junio", "Julio", "Agosto"],
    "Primavera": ["Septiembre", "Octubre", "Noviembre"]
}

numero_mes = {
    "Enero": 1,
    "Febrero": 2,
    "Marzo": 3,
    "Abril": 4,
    "Mayo": 5,
    "Junio": 6,
    "Julio": 7,
    "Agosto": 8,
    "Septiembre": 9,
    "Octubre": 10,
    "Noviembre": 11,
    "Diciembre": 12
}

meses = list(numero_mes.keys())

st.subheader("Seleccioná tu destino")

col1, col2, col3 = st.columns(3)

with col1:
    region = st.selectbox("Región", list(destinos.keys()))

with col2:
    ciudad = st.selectbox("Destino", destinos[region])

with col3:
    temporada = st.selectbox(
        "Temporada",
        list(meses_por_temporada.keys())
    )

mes = st.selectbox(
    "Mes de viaje",
    meses_por_temporada[temporada]
)

anio = st.selectbox("Año", [2021, 2022, 2023, 2024, 2025])

consultar = st.button(
    "🔎 Consultar destino",
    type="primary",
    use_container_width=True
)

if consultar:
    st.session_state["consulta_realizada"] = {
        "region": region,
        "ciudad": ciudad,
        "temporada": temporada,
        "mes": mes,
        "anio": anio
    }

st.divider()


# DATOS DE DEMOSTRACIÓN

def crear_demo_mejor_epoca():
    valores = {
        "Purmamarca": {
            "Noroeste": [65, 68, 72, 78, 82, 88, 90, 88, 85, 80, 72, 66]
        },
        "Bariloche": {
            "Patagonia": [90, 88, 78, 65, 52, 38, 30, 35, 48, 62, 75, 85]
        },
        "Puerto Iguazú": {
            "Noreste": [48, 55, 65, 78, 85, 90, 92, 90, 82, 70, 58, 48]
        }
    }

    filas = []

    for destino, regiones in valores.items():
        region_destino = list(regiones.keys())[0]

        for mes_numero, porcentaje in enumerate(regiones[region_destino], start=1):
            filas.append({
                "destino": destino,
                "nombre_mes": meses[mes_numero - 1],
                "mes": mes_numero,
                "dias_observados": 150,
                "pct_dias_agradables": porcentaje,
                "pct_dias_lluviosos": max(5, 100 - porcentaje),
                "temp_media": 12 + mes_numero,
                "temp_max_promedio": 18 + mes_numero,
                "temp_min_promedio": 7 + mes_numero,
                "lluvia_mm_por_mes": 30 + (mes_numero * 8),
                "rafaga_promedio_kmh": 20 + mes_numero,
                "horas_luz_promedio": 7 + (mes_numero % 4),
                "dias_temp_extrema": max(0, 12 - mes_numero),
                "ranking_en_destino": 1
            })

    return pd.DataFrame(filas)


def crear_demo_historico(destino):
    datos = {
        "Purmamarca": {
            "temperaturas": [24, 23, 21, 18, 15, 12, 11, 13, 16, 19, 21, 23],
            "lluvias": [120, 110, 95, 60, 30, 15, 10, 15, 25, 45, 80, 105]
        },
        "Bariloche": {
            "temperaturas": [18, 17, 14, 10, 7, 4, 3, 5, 8, 11, 14, 17],
            "lluvias": [60, 55, 50, 45, 40, 35, 30, 35, 40, 50, 55, 65]
        },
        "Puerto Iguazú": {
            "temperaturas": [27, 27, 25, 22, 19, 17, 17, 19, 21, 23, 25, 27],
            "lluvias": [180, 170, 150, 120, 90, 70, 60, 75, 100, 130, 160, 190]
        }
    }

    filas = []

    for anio_demo in range(2021, 2026):
        for mes_numero in range(1, 13):
            variacion = (anio_demo - 2023) * 0.3

            filas.append({
                "anio": anio_demo,
                "mes": mes_numero,
                "nombre_mes": meses[mes_numero - 1],
                "temperatura_media": (
                    datos[destino]["temperaturas"][mes_numero - 1]
                    + variacion
                ),
                "precipitaciones": (
                    datos[destino]["lluvias"][mes_numero - 1]
                    + (anio_demo - 2023) * 3
                )
            })

    return pd.DataFrame(filas)


def obtener_mejor_epoca():
    datos = leer(
        """
        SELECT *
        FROM gold.v_mejor_epoca
        ORDER BY destino, mes
        """
    )

    if datos is not None and not datos.empty:
        return datos, True

    return crear_demo_mejor_epoca(), False


def obtener_historico(destino):
    datos = leer(
        """
        SELECT
            t.anio,
            t.mes,
            t.nombre_mes,
            AVG(f.temperatura_media) AS temperatura_media,
            SUM(f.precipitacion_mm) AS precipitaciones
        FROM gold.fact_clima_diario f
        INNER JOIN gold.dim_ciudad c
            ON f.ciudad_id = c.ciudad_id
        INNER JOIN gold.dim_tiempo t
            ON f.fecha = t.fecha
        WHERE c.destino = :ciudad
        GROUP BY t.anio, t.mes, t.nombre_mes
        ORDER BY t.anio, t.mes
        """,
        {"ciudad": destino}
    )

    if datos is not None and not datos.empty:
        return datos, True

    return crear_demo_historico(destino), False


# RESULTADO DEL SEMÁFORO

st.subheader("Resultado del Semáforo")

datos_epoca, datos_reales = obtener_mejor_epoca()

if not datos_reales:
    st.warning(
        "Modo demostración: los resultados que aparecen a continuación "
        "son ficticios y se reemplazarán automáticamente cuando Gold tenga datos."
    )

if "consulta_realizada" in st.session_state:

    consulta = st.session_state["consulta_realizada"]
    mes_numero = numero_mes[consulta["mes"]]

    resultado = datos_epoca[
        (datos_epoca["destino"] == consulta["ciudad"]) &
        (datos_epoca["mes"] == mes_numero)
    ]

    if not resultado.empty:

        datos = resultado.iloc[0]
        porcentaje = float(datos["pct_dias_agradables"])

        if porcentaje >= 60:
            estado = "FAVORABLE"
            color = "#477A50"
            descripcion = (
                "Este período presenta una proporción alta de días agradables."
            )
            recomendacion = "Es una buena época para planificar tu viaje."

        elif porcentaje >= 30:
            estado = "PRECAUCIÓN"
            color = "#B28A36"
            descripcion = (
                "Las condiciones pueden ser variables durante este período."
            )
            recomendacion = (
                "Revisá las condiciones climáticas antes de viajar."
            )

        else:
            estado = "DESFAVORABLE"
            color = "#B6534B"
            descripcion = (
                "Este período presenta una proporción baja de días agradables."
            )
            recomendacion = (
                "Considerá elegir otro mes para viajar."
            )

        st.info(f"💡 Recomendación: {recomendacion}")

        st.caption(
            f"Destino: {consulta['ciudad']} | "
            f"Temporada: {consulta['temporada']} | "
            f"Mes: {consulta['mes']}"
        )

        st.markdown(f"""
        <div style="
            background-color: #FFFFFF;
            border: 1px solid #E1E6DE;
            border-left: 8px solid {color};
            padding: 24px;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(53, 81, 61, 0.08);
        ">
            <h2 style="color: {color}; margin: 0;">
                ● {estado}
            </h2>
            <p style="color: #343C32 !important;">
                {descripcion}
            </p>
            <h3 style="color: #343C32;">
                {porcentaje:.1f}% de días agradables
            </h3>
        </div>
        """, unsafe_allow_html=True)

        st.caption(
            f"Período histórico analizado: {int(datos['dias_observados'])} días observados."
        )

    else:
        st.warning(
            "No se encontraron datos para este destino y mes."
        )

else:
    st.info("Seleccioná los filtros y presioná «Consultar destino».")


# INDICADORES CLIMÁTICOS

st.subheader("Indicadores Climáticos")

if "consulta_realizada" in st.session_state:

    consulta = st.session_state["consulta_realizada"]
    mes_numero = numero_mes[consulta["mes"]]

    indicadores = leer(
        """
        SELECT
            AVG(f.temperatura_media) AS temp_media,
            AVG(f.temperatura_maxima) AS temp_max,
            SUM(f.precipitacion_mm) AS precipitaciones,
            AVG(f.horas_luz) AS horas_luz
        FROM gold.fact_clima_diario f
        INNER JOIN gold.dim_ciudad c
            ON f.ciudad_id = c.ciudad_id
        INNER JOIN gold.dim_tiempo t
            ON f.fecha = t.fecha
        WHERE c.destino = :ciudad
          AND t.anio = :anio
          AND t.mes = :mes
        """,
        {
            "ciudad": consulta["ciudad"],
            "anio": consulta["anio"],
            "mes": mes_numero
        }
    )

    if (
        indicadores is not None
        and not indicadores.empty
        and pd.notna(indicadores.iloc[0]["temp_media"])
    ):
        datos_indicadores = indicadores.iloc[0]
        indicadores_reales = True

    else:
        datos_demo = datos_epoca[
            (datos_epoca["destino"] == consulta["ciudad"]) &
            (datos_epoca["mes"] == mes_numero)
        ]

        datos_indicadores = datos_demo.iloc[0]
        indicadores_reales = False

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Temperatura media",
        f"{datos_indicadores['temp_media'] if indicadores_reales else datos_indicadores['temp_media']:.1f} °C"
    )

    temperatura_maxima = (
        datos_indicadores["temp_max"]
        if indicadores_reales
        else datos_indicadores["temp_max_promedio"]
    )

    col2.metric(
        "Temperatura máxima",
        f"{temperatura_maxima:.1f} °C"
    )

    if indicadores_reales:
        col3.metric(
            "Precipitaciones",
            f"{datos_indicadores['precipitaciones']:.1f} mm"
        )
        col4.metric(
            "Horas de luz",
            f"{datos_indicadores['horas_luz']:.1f} h"
        )
    else:
        col3.metric(
            "Precipitaciones",
            f"{datos_indicadores['lluvia_mm_por_mes']:.1f} mm"
        )
        col4.metric(
            "Horas de luz",
            f"{datos_indicadores['horas_luz_promedio']:.1f} h"
        )

    if not indicadores_reales:
        st.caption("Indicadores de demostración: valores ficticios.")

else:
    st.info("Los indicadores aparecerán después de consultar un destino.")


# HISTÓRICO CLIMÁTICO

st.subheader("Comportamiento histórico")

if "consulta_realizada" in st.session_state:

    consulta = st.session_state["consulta_realizada"]

    historico, historico_real = obtener_historico(consulta["ciudad"])

    if not historico_real:
        st.caption(
            "Gráficos de demostración: datos ficticios para probar la visualización."
        )

    if not historico.empty:

        st.markdown("**Temperatura media por mes**")

        fig_temperatura = px.line(
            historico,
            x="nombre_mes",
            y="temperatura_media",
            color="anio",
            markers=True,
            title=f"Temperatura media — {consulta['ciudad']}",
            labels={
                "nombre_mes": "Mes",
                "temperatura_media": "Temperatura media (°C)",
                "anio": "Año"
            },
            category_orders={"nombre_mes": meses}
        )

        fig_temperatura.update_traces(
            line=dict(width=2),
            marker=dict(size=7)
        )

        fig_temperatura = configurar_grafico(fig_temperatura)

        st.plotly_chart(
            fig_temperatura,
            use_container_width=True,
            theme=None
        )

        st.markdown("**Precipitaciones por mes**")

        fig_lluvia = px.bar(
            historico,
            x="nombre_mes",
            y="precipitaciones",
            color="anio",
            barmode="group",
            title=f"Precipitaciones mensuales — {consulta['ciudad']}",
            labels={
                "nombre_mes": "Mes",
                "precipitaciones": "Precipitaciones (mm)",
                "anio": "Año"
            },
            category_orders={"nombre_mes": meses}
        )

        fig_lluvia = configurar_grafico(fig_lluvia)

        st.plotly_chart(
            fig_lluvia,
            use_container_width=True,
            theme=None
        )

    else:
        st.warning("No hay datos históricos disponibles.")

else:
    st.info("Los gráficos aparecerán después de consultar un destino.")


# COMPARACIÓN DE DESTINOS

st.divider()
st.subheader("¿Cuál es la mejor época para viajar?")

comparacion = (
    datos_epoca
    .sort_values("pct_dias_agradables", ascending=False)
    .groupby("destino", as_index=False)
    .first()
    .sort_values("pct_dias_agradables", ascending=False)
)

if not comparacion.empty:

    mejor = comparacion.iloc[0]

    st.success(
        f"🏆 Según los datos disponibles, {mejor['destino']} "
        f"en {mejor['nombre_mes']} presenta el mayor porcentaje "
        f"de días agradables ({mejor['pct_dias_agradables']:.1f}%)."
    )

    fig_comparacion = px.bar(
        comparacion,
        x="destino",
        y="pct_dias_agradables",
        color="destino",
        text="pct_dias_agradables",
        title="Mejor mes de cada destino según días agradables",
        labels={
            "destino": "Destino",
            "pct_dias_agradables": "Días agradables (%)"
        }
    )

    fig_comparacion.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
        textfont=dict(color="#343A35", size=13)
    )

    fig_comparacion.update_yaxes(range=[0, 110])

    fig_comparacion = configurar_grafico(fig_comparacion)

    st.plotly_chart(
        fig_comparacion,
        use_container_width=True,
        theme=None
    )



