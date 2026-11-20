

# G06 - Semáforo del Viajero
# Visualización de condiciones climáticas históricas.
# Datos reales consultados exclusivamente desde la capa Gold.

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

anio = st.selectbox(
    "Año para consultar indicadores",
    list(range(2021, 2027))
)

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


# CONSULTAS A GOLD

def obtener_mejor_epoca():
    datos = leer("""
        SELECT *
        FROM gold.v_mejor_epoca
        ORDER BY destino, mes
    """)

    if datos is None:
        return pd.DataFrame()

    return datos


def obtener_historico(destino):
    datos = leer("""
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
    """, {"ciudad": destino})

    if datos is None:
        return pd.DataFrame()

    return datos


def clasificar_mes(favorables, precaucion, desfavorables):

    porcentajes = {
        "FAVORABLE": favorables,
        "PRECAUCIÓN": precaucion,
        "DESFAVORABLE": desfavorables
    }

    estado = max(porcentajes, key=porcentajes.get)

    if estado == "FAVORABLE":
        color = "#477A50"
        descripcion = (
            "Predominan los días con condiciones favorables "
            "para viajar durante este mes."
        )

    elif estado == "PRECAUCIÓN":
        color = "#B28A36"
        descripcion = (
            "Predominan los días con condiciones variables. "
            "Se recomienda planificar el viaje con precaución."
        )

    else:
        color = "#B6534B"
        descripcion = (
            "Predominan los días con condiciones desfavorables. "
            "Se recomienda considerar otro período para viajar."
        )

    return estado, color, descripcion


# RESULTADO DEL SEMÁFORO

st.subheader("Resultado del Semáforo")

datos_epoca = obtener_mejor_epoca()

if datos_epoca.empty:
    st.warning(
        "No hay datos disponibles en gold.v_mejor_epoca. Revisá la carga Gold."
    )

if "consulta_realizada" in st.session_state and not datos_epoca.empty:

    consulta = st.session_state["consulta_realizada"]
    mes_numero = numero_mes[consulta["mes"]]

    resultado = datos_epoca[
        (datos_epoca["destino"] == consulta["ciudad"]) &
        (datos_epoca["mes"] == mes_numero)
    ]

    if not resultado.empty and pd.notna(
        resultado.iloc[0]["pct_dias_favorables"]
    ):

        datos = resultado.iloc[0]

        favorables = float(datos["pct_dias_favorables"])
        precaucion = float(datos["pct_dias_precaucion"])
        desfavorables = float(datos["pct_dias_desfavorables"])

        estado, color, descripcion = clasificar_mes(
            favorables,
            precaucion,
            desfavorables
        )

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
        </div>
        """, unsafe_allow_html=True)

        col_verde, col_amarillo, col_rojo = st.columns(3)

        col_verde.metric(
            "🟢 Favorables",
            f"{favorables:.1f}%"
        )

        col_amarillo.metric(
            "🟡 Precaución",
            f"{precaucion:.1f}%"
        )

        col_rojo.metric(
            "🔴 Desfavorables",
            f"{desfavorables:.1f}%"
        )

        st.info(
            "💡 Estos porcentajes corresponden a días históricos del mes "
            "seleccionado. Son criterios turísticos orientativos, "
            "no alertas meteorológicas oficiales."
        )

        st.caption(
            f"Período histórico analizado: "
            f"{int(datos['dias_observados'])} días clasificados; "
            f"{int(datos['dias_sin_dato'])} sin clasificación. "
            "La recomendación mensual combina la proporción "
            "de días favorables y desfavorables."
        )

    else:
        st.warning(
            "No se encontraron datos clasificados para este destino y mes."
        )

elif "consulta_realizada" not in st.session_state:
    st.info(
        "Seleccioná los filtros y presioná «Consultar destino»."
    )


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
        indicadores is None
        or indicadores.empty
        or pd.isna(indicadores.iloc[0]["temp_media"])
    ):
        st.warning(
            "No hay indicadores para el destino, mes y año seleccionados."
        )
        datos_indicadores = None

    else:
        datos_indicadores = indicadores.iloc[0]

    if datos_indicadores is not None:

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Temperatura media",
            f"{datos_indicadores['temp_media']:.1f} °C"
        )

        col2.metric(
            "Temperatura máxima",
            f"{datos_indicadores['temp_max']:.1f} °C"
        )

        col3.metric(
            "Precipitaciones",
            f"{datos_indicadores['precipitaciones']:.1f} mm"
        )

        col4.metric(
            "Horas de luz",
            f"{datos_indicadores['horas_luz']:.1f} h"
        )

else:
    st.info(
        "Los indicadores aparecerán después de consultar un destino."
    )


# HISTÓRICO CLIMÁTICO

st.subheader("Comportamiento histórico")

if "consulta_realizada" in st.session_state:

    consulta = st.session_state["consulta_realizada"]

    historico = obtener_historico(consulta["ciudad"])

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

        fig_temperatura = configurar_grafico(
            fig_temperatura
        )

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

        fig_lluvia = configurar_grafico(
            fig_lluvia
        )

        st.plotly_chart(
            fig_lluvia,
            use_container_width=True,
            theme=None
        )

    else:
        st.warning(
            "No hay datos históricos disponibles."
        )

else:
    st.info(
        "Los gráficos aparecerán después de consultar un destino."
    )


# COMPARACIÓN DE DESTINOS

st.divider()
st.subheader("¿Cuál es la mejor época para viajar?")

if not datos_epoca.empty:

    comparacion = (
        datos_epoca
        .sort_values(["destino", "ranking_en_destino", "mes"])
        .groupby("destino", as_index=False)
        .first()
        .sort_values("pct_dias_favorables", ascending=False)
    )

    if not comparacion.empty:

        mejor = comparacion.iloc[0]

        st.success(
            f"🏆 Entre los mejores meses de cada destino, "
            f"{mejor['destino']} en {mejor['nombre_mes']} "
            f"presenta el mayor porcentaje de días favorables "
            f"({mejor['pct_dias_favorables']:.1f}%)."
        )

        fig_comparacion = px.bar(
            comparacion,
            x="destino",
            y="pct_dias_favorables",
            color="destino",
            text="pct_dias_favorables",
            title="Mejor mes de cada destino según días favorables",
            labels={
                "destino": "Destino",
                "pct_dias_favorables": "Días favorables (%)"
            }
        )

        fig_comparacion.update_traces(
            texttemplate="%{text:.1f}%",
            textposition="outside",
            textfont=dict(color="#343A35", size=13)
        )

        fig_comparacion.update_yaxes(
            range=[0, 110]
        )

        fig_comparacion = configurar_grafico(
            fig_comparacion
        )

        st.plotly_chart(
            fig_comparacion,
            use_container_width=True,
            theme=None
        )

        st.caption(
            "El gráfico compara el mes mejor posicionado de cada destino, "
            "según el ranking calculado en Gold."
        )


# CONDICIONES CLIMÁTICAS RECIENTES

st.divider()
st.subheader("🌤️ Condiciones climáticas recientes")

st.caption(
    "Últimos datos horarios disponibles de Open-Meteo, "
    "procesados por Bronze, Silver y Gold."
)

datos_horarios = leer("""
    SELECT
        destino,
        fecha_hora,
        temperatura_2m,
        precipitacion_mm,
        rafagas_viento_kmh
    FROM gold.v_clima_horario
    ORDER BY fecha_hora DESC
""")

if datos_horarios is not None and not datos_horarios.empty:

    ciudad_horaria = st.selectbox(
        "Destino para consultar datos recientes",
        sorted(datos_horarios["destino"].unique()),
        key="ciudad_horaria"
    )

    datos_ciudad = datos_horarios[
        datos_horarios["destino"] == ciudad_horaria
    ].sort_values("fecha_hora", ascending=False)

    ultimo = datos_ciudad.iloc[0]

    st.caption(
        f"Último registro disponible (UTC): "
        f"{ultimo['fecha_hora']}"
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Temperatura",
        f"{ultimo['temperatura_2m']:.1f} °C"
    )

    col2.metric(
        "Precipitaciones",
        f"{ultimo['precipitacion_mm']:.1f} mm"
    )

    col3.metric(
        "Ráfagas de viento",
        f"{ultimo['rafagas_viento_kmh']:.1f} km/h"
    )

    st.markdown(
        "**Evolución de la temperatura horaria**"
    )

    fig_horaria = px.line(
        datos_ciudad.sort_values("fecha_hora"),
        x="fecha_hora",
        y="temperatura_2m",
        markers=True,
        title=f"Temperatura horaria — {ciudad_horaria}",
        labels={
            "fecha_hora": "Fecha y hora (UTC)",
            "temperatura_2m": "Temperatura (°C)"
        }
    )

    st.plotly_chart(
        configurar_grafico(fig_horaria),
        use_container_width=True
    )

else:
    st.warning(
        "No hay datos horarios disponibles en Gold."
    )
