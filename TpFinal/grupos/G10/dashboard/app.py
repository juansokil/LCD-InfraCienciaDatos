
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from plotly.subplots import make_subplots
from db import obtener_pronosticos

# ==========================================
# CONFIGURACION DE LA PAGINA
# ==========================================

st.set_page_config(
    page_title="LogiWeather",
    page_icon="🌦️",
    layout="wide"
)


# ==========================================
# CARGA DE DATOS DESDE GOLD
# ==========================================

@st.cache_data(ttl=60)
def cargar_datos():
    return obtener_pronosticos()


# ==========================================
# ENCABEZADO
# ==========================================

st.title("🌦️ LogiWeather")

st.caption(
    "Centro de planificación meteorológica y operativa"
)

st.markdown(
    "Anticipá riesgos meteorológicos y planificá "
    "incentivos para las operaciones de reparto."
)

if st.button("Actualizar datos"):
    cargar_datos.clear()


# ==========================================
# CONEXION A POSTGRESQL
# ==========================================

try:
    df = cargar_datos()

except Exception:
    logging.exception(
        "Error al consultar la capa Gold"
    )

    st.warning(
        "No se pudieron consultar los datos de Gold. "
        "Verificá que PostgreSQL esté funcionando "
        "y que el pipeline haya terminado correctamente."
    )

    st.stop()


if df.empty:
    st.info(
        "Todavía no hay pronósticos disponibles. "
        "Esperando la primera ejecución del pipeline."
    )

    st.stop()


# ==========================================
# VALIDACION DE LOS RESULTADOS
# ==========================================

columnas_alertas = [
    "nivel_alerta_lluvia",
    "incentivo_lluvia",
    "nivel_alerta_calor",
    "incentivo_calor",
    "nivel_alerta",
    "incentivo_recomendado"
]

if df[columnas_alertas].isna().any().any():

    st.warning(
        "Hay pronósticos pendientes de clasificación. "
        "Esperá a que finalice el procesamiento de Gold."
    )

    st.stop()


# ==========================================
# FILTROS DEL DASHBOARD
# ==========================================

st.sidebar.title("LogiWeather")

st.sidebar.caption(
    "Planificación meteorológica y operativa"
)

st.sidebar.divider()

st.sidebar.header("Filtros")

# Seleccion de ciudad

ciudades = sorted(
    df["ciudad"].unique().tolist()
)

ciudad_seleccionada = st.sidebar.selectbox(
    "Ciudad",
    options=["Todas las ciudades"] + ciudades
)

# Seleccion del periodo

periodo = st.sidebar.radio(
    "Período de análisis",
    options=[
        "Próximos 7 días",
        "Pronósticos anteriores",
        "Todos los registros"
    ],
    index=0
)

# Zonas horarias de las ciudades

zonas_horarias = {
    "new_york": "America/New_York",
    "miami": "America/New_York",
    "chicago": "America/Chicago",
    "houston": "America/Chicago",
    "los_angeles": "America/Los_Angeles"
}

# Fecha actual en cada ciudad

hoy_por_ciudad = {
    ciudad_id: datetime.now(
        ZoneInfo(zona)
    ).date()
    for ciudad_id, zona in zonas_horarias.items()
}

df_filtrado = df.copy()

df_filtrado["hoy_local"] = (
    df_filtrado["ciudad_id"].map(
        hoy_por_ciudad
    )
)

df_filtrado["fecha_dia"] = (
    df_filtrado["fecha_pronostico"].dt.date
)

# Aplicar filtro de ciudad

if ciudad_seleccionada != "Todas las ciudades":

    df_filtrado = df_filtrado[
        df_filtrado["ciudad"] == ciudad_seleccionada
    ]

# Aplicar filtro de periodo

if periodo == "Próximos 7 días":

    df_filtrado = df_filtrado[
        (
            df_filtrado["fecha_dia"]
            >= df_filtrado["hoy_local"]
        )
        &
        (
            df_filtrado["fecha_dia"]
            <= (
                df_filtrado["hoy_local"]
                + timedelta(days=6)
            )
        )
    ]

elif periodo == "Pronósticos anteriores":

    df_filtrado = df_filtrado[
        df_filtrado["fecha_dia"]
        < df_filtrado["hoy_local"]
    ]

# Verificar disponibilidad de datos

if df_filtrado.empty:

    st.warning(
        "No hay pronósticos disponibles "
        "para los filtros seleccionados."
    )

    st.stop()

# Seleccion de rango de fechas

fechas_disponibles = sorted(
    df_filtrado["fecha_dia"].unique().tolist()
)

if len(fechas_disponibles) > 1:

    fecha_desde, fecha_hasta = (
        st.sidebar.select_slider(
            "Rango de fechas",
            options=fechas_disponibles,
            value=(
                fechas_disponibles[0],
                fechas_disponibles[-1]
            ),
            format_func=lambda fecha: (
                fecha.strftime("%d/%m")
            )
        )
    )

else:

    fecha_desde = fechas_disponibles[0]
    fecha_hasta = fechas_disponibles[0]

    st.sidebar.caption(
        "Fecha disponible: "
        + fecha_desde.strftime("%d/%m/%Y")
    )

# Aplicar filtro de fechas

df_filtrado = df_filtrado[
    (
        df_filtrado["fecha_dia"]
        >= fecha_desde
    )
    &
    (
        df_filtrado["fecha_dia"]
        <= fecha_hasta
    )
].copy()

# Informacion de los filtros

st.sidebar.divider()

st.sidebar.caption(
    "Fuente meteorológica: Open-Meteo"
)

st.sidebar.caption(
    "Actualización del pipeline: cada hora"
)

st.sidebar.caption(
    "Datos consultados desde PostgreSQL Gold"
)


# ==========================================
# ULTIMA ACTUALIZACION
# ==========================================

ultima_ingesta = df["ingested_at"].max()

ultima_ingesta_argentina = (
    ultima_ingesta.tz_convert(
        "America/Argentina/Buenos_Aires"
    )
)

st.caption(
    "Última ingesta disponible: "
    + ultima_ingesta_argentina.strftime(
        "%d/%m/%Y %H:%M"
    )
    + " h (Argentina)"
)



# ==========================================
# INDICADORES PRINCIPALES
# ==========================================

st.subheader("Resumen operativo")

st.caption(
    f"{ciudad_seleccionada} | "
    f"{fecha_desde.strftime('%d/%m/%Y')} "
    f"al {fecha_hasta.strftime('%d/%m/%Y')}"
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    with st.container(border=True):
        st.metric(
            label="Ciudades monitoreadas",
            value=df_filtrado[
                "ciudad_id"
            ].nunique()
        )

with col2:
    with st.container(border=True):
        st.metric(
            label="Pronósticos",
            value=len(df_filtrado)
        )

with col3:
    with st.container(border=True):
        st.metric(
            label="Pronósticos con alerta",
            value=int(
                (
                    df_filtrado["nivel_alerta"]
                    != "SIN_ALERTA"
                ).sum()
            )
        )

with col4:
    with st.container(border=True):
        st.metric(
            label="Incentivo máximo",
            value=(
                f'{df_filtrado["incentivo_recomendado"].max():.0f}%'
            )
        )

st.divider()


# ==========================================
# NAVEGACION DEL DASHBOARD
# ==========================================

tab_mapa, tab_pronostico, tab_alertas, tab_datos = (
    st.tabs(
        [
            "🗺️ Mapa operativo",
            "🌤️ Pronóstico por ciudad",
            "⚠️ Alertas e incentivos",
            "📊 Datos de Gold"
        ]
    )
)

with tab_mapa:

    # ==========================================
    # MAPA DE ALERTAS METEOROLOGICAS
    # ==========================================

    st.subheader("Mapa de alertas operativas")

    st.caption(
        "Visualizá el nivel de riesgo meteorológico "
        "de cada ciudad para una fecha determinada."
    )

    # Fechas disponibles segun los filtros

    fechas_mapa = sorted(
        df_filtrado["fecha_dia"].unique().tolist()
    )

    fecha_mapa = st.selectbox(
        "Fecha del mapa",
        options=fechas_mapa,
        format_func=lambda fecha: fecha.strftime(
            "%d/%m/%Y"
        )
    )

    # Seleccionar los pronosticos del dia

    df_mapa = df_filtrado[
        df_filtrado["fecha_dia"] == fecha_mapa
    ].copy()

    # Colores de alertas

    colores_alertas = {
        "SIN_ALERTA": "#22C55E",
        "BAJA": "#FACC15",
        "MEDIA": "#F97316",
        "ALTA": "#EF4444"
    }

    orden_alertas = [
        "SIN_ALERTA",
        "BAJA",
        "MEDIA",
        "ALTA"
    ]

    # Descripcion de los niveles

    nombres_alertas = {
        "SIN_ALERTA": "Sin alerta",
        "BAJA": "Baja",
        "MEDIA": "Media",
        "ALTA": "Alta"
    }

    df_mapa["alerta_visual"] = (
        df_mapa["nivel_alerta"].map(
            nombres_alertas
        )
    )

    colores_mapa = {
        nombres_alertas[nivel]: color
        for nivel, color in colores_alertas.items()
    }

    # Crear mapa interactivo

    fig_mapa = px.scatter_geo(
        df_mapa,

        lat="latitud",
        lon="longitud",

        color="alerta_visual",

        color_discrete_map=colores_mapa,

        category_orders={
            "alerta_visual": [
                "Sin alerta",
                "Baja",
                "Media",
                "Alta"
            ]
        },

        hover_name="ciudad",

        text="ciudad",

        hover_data={
            "latitud": False,
            "longitud": False,
            "alerta_visual": True,
            "temperatura_max": ":.1f",
            "temperatura_min": ":.1f",
            "probabilidad_lluvia": True,
            "precipitacion_mm": ":.1f",
            "nivel_alerta_lluvia": True,
            "nivel_alerta_calor": True,
            "incentivo_lluvia": ":.0f",
            "incentivo_calor": ":.0f",
            "incentivo_recomendado": ":.0f"
        },

        labels={
            "alerta_visual": "Nivel de alerta",
            "temperatura_max": "Temp. máxima (°C)",
            "temperatura_min": "Temp. mínima (°C)",
            "probabilidad_lluvia": "Prob. lluvia (%)",
            "precipitacion_mm": "Precipitación (mm)",
            "nivel_alerta_lluvia": "Alerta lluvia",
            "nivel_alerta_calor": "Alerta calor",
            "incentivo_lluvia": "Incentivo lluvia (%)",
            "incentivo_calor": "Incentivo calor (%)",
            "incentivo_recomendado": "Incentivo general (%)"
        },

        scope="usa"
    )

    # Personalizar los marcadores

    fig_mapa.update_traces(
        marker=dict(
            size=17,
            line=dict(
                width=2,
                color="#F1F5F9"
            )
        ),

        textposition="top center",

        textfont=dict(
            size=13,
            color="#F1F5F9"
        )
    )

    # Personalizar el mapa

    fig_mapa.update_geos(
        projection_type="albers usa",

        bgcolor="#0B1220",

        showland=True,
        landcolor="#17243A",

        showlakes=True,
        lakecolor="#0B1220",

        showsubunits=True,
        subunitcolor="#475569",

        showframe=False
    )

    # Personalizar el diseño general

    fig_mapa.update_layout(
        height=480,

        paper_bgcolor="#0B1220",
        plot_bgcolor="#0B1220",

        font=dict(
            color="#F1F5F9",
            size=13
        ),

        margin=dict(
            l=10,
            r=10,
            t=20,
            b=20
        ),

        legend=dict(
            title="Nivel de alerta",
            orientation="h",
            yanchor="bottom",
            y=-0.08,
            xanchor="center",
            x=0.5
        )
    )

    # Mostrar el mapa

    st.plotly_chart(
        fig_mapa,
        use_container_width=True,
        config={
            "displayModeBar": False
        }
    )

    st.caption(
        "Verde: sin alerta | Amarillo: baja | "
        "Naranja: media | Rojo: alta. "
        "El color representa el mayor nivel de "
        "riesgo entre lluvia y calor."
    )


    # Resumen operativo de la fecha seleccionada

    st.markdown(
        "#### Situación operativa del día"
    )

    df_resumen_dia = df_mapa[
        [
            "ciudad",
            "temperatura_max",
            "probabilidad_lluvia",
            "precipitacion_mm",
            "nivel_alerta",
            "incentivo_recomendado"
        ]
    ].sort_values(
        "incentivo_recomendado",
        ascending=False
    )

    st.dataframe(
        df_resumen_dia,
        hide_index=True,
        use_container_width=True,

        column_config={

            "ciudad": "Ciudad",

            "temperatura_max":
                st.column_config.NumberColumn(
                    "Temperatura máxima (°C)",
                    format="%.1f"
                ),

            "probabilidad_lluvia":
                st.column_config.NumberColumn(
                    "Probabilidad de lluvia (%)",
                    format="%d"
                ),

            "precipitacion_mm":
                st.column_config.NumberColumn(
                    "Precipitación (mm)",
                    format="%.1f"
                ),

            "nivel_alerta":
                "Nivel de alerta",

            "incentivo_recomendado":
                st.column_config.ProgressColumn(
                    "Incentivo recomendado (%)",
                    min_value=0,
                    max_value=75,
                    format="%.0f%%"
                )
        }
    )

    st.divider()

with tab_pronostico:
    # ==========================================
    # PRONOSTICO METEOROLOGICO POR CIUDAD
    # ==========================================

    st.subheader("Pronóstico meteorológico por ciudad")

    st.caption(
        "Analizá las condiciones meteorológicas y "
        "las recomendaciones operativas de cada día."
    )

    # Ciudades disponibles segun los filtros

    ciudades_pronostico = sorted(
        df_filtrado["ciudad"].unique().tolist()
    )

    ciudad_pronostico = st.selectbox(
        "Ciudad para analizar",
        options=ciudades_pronostico,
        key="ciudad_pronostico"
    )

    # Seleccionar los registros de la ciudad

    df_ciudad = df_filtrado[
        df_filtrado["ciudad"] == ciudad_pronostico
    ].sort_values(
        "fecha_pronostico"
    ).copy()


    # ==========================================
    # ICONOS Y DESCRIPCIONES METEOROLOGICAS
    # ==========================================

    def obtener_clima(codigo):

        if codigo == 0:
            return "☀️", "Despejado"

        elif codigo in [1, 2]:
            return "🌤️", "Parcialmente nublado"

        elif codigo == 3:
            return "☁️", "Nublado"

        elif codigo in [45, 48]:
            return "🌫️", "Niebla"

        elif codigo in [51, 53, 55, 56, 57]:
            return "🌦️", "Llovizna"

        elif codigo in [61, 63, 65, 66, 67]:
            return "🌧️", "Lluvia"

        elif codigo in [71, 73, 75, 77]:
            return "❄️", "Nieve"

        elif codigo in [80, 81, 82]:
            return "🌧️", "Chubascos"

        elif codigo in [85, 86]:
            return "🌨️", "Chubascos de nieve"

        elif codigo in [95, 96, 99]:
            return "⛈️", "Tormenta"

        else:
            return "🌡️", "Sin descripción"


    dias_semana = {
        0: "Lunes",
        1: "Martes",
        2: "Miércoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sábado",
        6: "Domingo"
    }


    # ==========================================
    # TARJETAS METEOROLOGICAS DIARIAS
    # ==========================================

    st.markdown(
        f"#### Pronóstico diario — {ciudad_pronostico}"
    )

    # Mostrar hasta siete tarjetas

    df_tarjetas = df_ciudad.head(7)

    if len(df_ciudad) > 7:

        st.caption(
            "Se muestran los primeros siete días "
            "del período seleccionado. Los gráficos "
            "incluyen todo el período."
        )

    columnas_dias = st.columns(
        len(df_tarjetas)
    )

    for columna, (_, fila) in zip(
        columnas_dias,
        df_tarjetas.iterrows()
    ):

        fecha = fila["fecha_pronostico"]

        dia_nombre = dias_semana[
            fecha.weekday()
        ]

        icono, descripcion = obtener_clima(
            fila["weather_code"]
        )

        alerta = fila["nivel_alerta"]

        incentivo = fila[
            "incentivo_recomendado"
        ]

        color_alerta = colores_alertas.get(
            alerta,
            "#94A3B8"
        )

        with columna:

            with st.container(border=True):

                st.markdown(
                    f"**{dia_nombre}**"
                )

                st.caption(
                    fecha.strftime("%d/%m")
                )

                st.markdown(
                    f"## {icono}"
                )

                st.caption(descripcion)

                st.markdown(
                    f'### {fila["temperatura_max"]:.1f} °C'
                )

                st.caption(
                    f'Mín. {fila["temperatura_min"]:.1f} °C'
                )

                st.divider()

                st.caption(
                    f'💧 Lluvia: '
                    f'{fila["probabilidad_lluvia"]:.0f}%'
                )

                st.caption(
                    f'🌧️ {fila["precipitacion_mm"]:.1f} mm'
                )

                st.markdown(
                    f"""
                    <span style="
                        color: {color_alerta};
                        font-weight: 600;
                    ">
                        {nombres_alertas.get(alerta, alerta)}
                    </span>
                    """,
                    unsafe_allow_html=True
                )

                st.markdown(
                    f"**+{incentivo:.0f}%**"
                )

                st.caption(
                    "Incentivo recomendado"
                )


    st.caption(
        "Las temperaturas y precipitaciones "
        "corresponden al pronóstico diario. "
        "Los incentivos se obtienen directamente "
        "de la capa Gold."
    )


    # ==========================================
    # GRAFICOS METEOROLOGICOS
    # ==========================================

    st.markdown(
        "#### Evolución meteorológica"
    )

    col_temperatura, col_lluvia = st.columns(2)


    # ==========================================
    # GRAFICO DE TEMPERATURAS
    # ==========================================

    with col_temperatura:

        fig_temperatura = go.Figure()

        fig_temperatura.add_trace(
            go.Scatter(
                x=df_ciudad["fecha_pronostico"],
                y=df_ciudad["temperatura_max"],

                name="Temperatura máxima",

                mode="lines+markers",

                line=dict(
                    color="#FB923C",
                    width=3
                ),

                marker=dict(
                    size=8
                ),

                hovertemplate=(
                    "%{x|%d/%m/%Y}"
                    "<br>Máxima: %{y:.1f} °C"
                    "<extra></extra>"
                )
            )
        )

        fig_temperatura.add_trace(
            go.Scatter(
                x=df_ciudad["fecha_pronostico"],
                y=df_ciudad["temperatura_min"],

                name="Temperatura mínima",

                mode="lines+markers",

                line=dict(
                    color="#38BDF8",
                    width=3
                ),

                marker=dict(
                    size=8
                ),

                hovertemplate=(
                    "%{x|%d/%m/%Y}"
                    "<br>Mínima: %{y:.1f} °C"
                    "<extra></extra>"
                )
            )
        )

        fig_temperatura.update_layout(

            title="Temperaturas máximas y mínimas",

            template="plotly_dark",

            height=360,

            paper_bgcolor="#0B1220",
            plot_bgcolor="#0B1220",

            font=dict(
                color="#F1F5F9"
            ),

            margin=dict(
                l=15,
                r=15,
                t=60,
                b=30
            ),

            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.35,
                xanchor="center",
                x=0.5
            )
        )

        fig_temperatura.update_xaxes(
            tickformat="%d/%m",
            gridcolor="#26354A"
        )

        fig_temperatura.update_yaxes(
            title_text="Temperatura (°C)",
            gridcolor="#26354A"
        )

        st.plotly_chart(
            fig_temperatura,
            use_container_width=True,
            config={
                "displayModeBar": False
            }
        )


    # ==========================================
    # GRAFICO DE LLUVIAS
    # ==========================================

    with col_lluvia:

        fig_lluvia = make_subplots(
            specs=[
                [
                    {
                        "secondary_y": True
                    }
                ]
            ]
        )

        # Barras de precipitacion acumulada

        fig_lluvia.add_trace(
            go.Bar(
                x=df_ciudad["fecha_pronostico"],
                y=df_ciudad["precipitacion_mm"],

                name="Precipitación (mm)",

                marker_color="#38BDF8",

                hovertemplate=(
                    "%{x|%d/%m/%Y}"
                    "<br>Precipitación: %{y:.1f} mm"
                    "<extra></extra>"
                )
            ),
            secondary_y=False
        )

        # Linea de probabilidad de lluvia

        fig_lluvia.add_trace(
            go.Scatter(
                x=df_ciudad["fecha_pronostico"],
                y=df_ciudad["probabilidad_lluvia"],

                name="Probabilidad de lluvia (%)",

                mode="lines+markers",

                line=dict(
                    color="#A78BFA",
                    width=3
                ),

                marker=dict(
                    size=8
                ),

                hovertemplate=(
                    "%{x|%d/%m/%Y}"
                    "<br>Probabilidad: %{y:.0f}%"
                    "<extra></extra>"
                )
            ),
            secondary_y=True
        )

        fig_lluvia.update_layout(

            title="Precipitaciones y probabilidad",

            template="plotly_dark",

            height=360,

            paper_bgcolor="#0B1220",
            plot_bgcolor="#0B1220",

            font=dict(
                color="#F1F5F9"
            ),

            margin=dict(
                l=15,
                r=15,
                t=60,
                b=30
            ),

            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.35,
                xanchor="center",
                x=0.5
            )
        )

        fig_lluvia.update_xaxes(
            tickformat="%d/%m",
            gridcolor="#26354A"
        )

        fig_lluvia.update_yaxes(
            title_text="Precipitación (mm)",
            rangemode="tozero",
            gridcolor="#26354A",
            secondary_y=False
        )

        fig_lluvia.update_yaxes(
            title_text="Probabilidad (%)",
            range=[0, 100],
            showgrid=False,
            secondary_y=True
        )

        st.plotly_chart(
            fig_lluvia,
            use_container_width=True,
            config={
                "displayModeBar": False
            }
        )

    st.divider()

with tab_alertas:
    # ==========================================
    # ALERTAS E INCENTIVOS OPERATIVOS
    # ==========================================

    st.subheader("Alertas e incentivos operativos")

    st.caption(
        "Identificá las ciudades y fechas que "
        "requieren atención y consultá los "
        "incentivos recomendados."
    )

    # Seleccionar pronosticos con alerta

    df_alertas = df_filtrado[
        df_filtrado["nivel_alerta"] != "SIN_ALERTA"
    ].copy()

    # Ordenar por incentivo y fecha

    df_alertas = df_alertas.sort_values(
        [
            "incentivo_recomendado",
            "fecha_pronostico",
            "ciudad"
        ],
        ascending=[False, True, True]
    ).reset_index(drop=True)


    # ==========================================
    # INDICADORES DE ALERTAS
    # ==========================================

    col_a1, col_a2, col_a3 = st.columns(3)

    with col_a1:

        with st.container(border=True):

            st.metric(
                "Alertas por lluvia",
                int(
                    (
                        df_alertas["nivel_alerta_lluvia"]
                        != "SIN_ALERTA"
                    ).sum()
                )
            )

    with col_a2:

        with st.container(border=True):

            st.metric(
                "Alertas por calor",
                int(
                    (
                        df_alertas["nivel_alerta_calor"]
                        != "SIN_ALERTA"
                    ).sum()
                )
            )

    with col_a3:

        with st.container(border=True):

            st.metric(
                "Alertas de prioridad alta",
                int(
                    (
                        df_alertas["nivel_alerta"]
                        == "ALTA"
                    ).sum()
                )
            )


    # ==========================================
    # TABLA DE ALERTAS PRIORITARIAS
    # ==========================================

    if df_alertas.empty:

        st.success(
            "No se identificaron alertas "
            "meteorológicas para las ciudades "
            "y fechas seleccionadas."
        )

    else:

        st.markdown(
            "#### Situaciones que requieren atención"
        )

        st.caption(
            "Ordenadas por incentivo recomendado, "
            "de mayor a menor."
        )

        columnas_prioridad = [
            "ciudad",
            "fecha_pronostico",
            "nivel_alerta_lluvia",
            "incentivo_lluvia",
            "nivel_alerta_calor",
            "incentivo_calor",
            "nivel_alerta",
            "incentivo_recomendado"
        ]

        st.dataframe(
            df_alertas[columnas_prioridad],

            hide_index=True,
            use_container_width=True,

            column_config={

                "ciudad": "Ciudad",

                "fecha_pronostico":
                    st.column_config.DateColumn(
                        "Fecha",
                        format="DD/MM/YYYY"
                    ),

                "nivel_alerta_lluvia":
                    "Alerta lluvia",

                "incentivo_lluvia":
                    st.column_config.NumberColumn(
                        "Incentivo lluvia (%)",
                        format="%.0f"
                    ),

                "nivel_alerta_calor":
                    "Alerta calor",

                "incentivo_calor":
                    st.column_config.NumberColumn(
                        "Incentivo calor (%)",
                        format="%.0f"
                    ),

                "nivel_alerta":
                    "Prioridad general",

                "incentivo_recomendado":
                    st.column_config.ProgressColumn(
                        "Incentivo recomendado (%)",
                        min_value=0,
                        max_value=75,
                        format="%.0f%%"
                    )
            }
        )


        # ======================================
        # DETALLE DE UNA ALERTA
        # ======================================

        st.markdown(
            "#### Analizar una recomendación"
        )

        opciones_alerta = [
            (
                f'{fila["ciudad"]} | '
                f'{fila["fecha_pronostico"]:%d/%m/%Y}'
            )
            for _, fila in df_alertas.iterrows()
        ]

        alerta_seleccionada = st.selectbox(
            "Seleccioná una ciudad y fecha",
            options=opciones_alerta,
            key="detalle_alerta_operativa"
        )

        indice_alerta = opciones_alerta.index(
            alerta_seleccionada
        )

        detalle = df_alertas.iloc[
            indice_alerta
        ]

        ciudad_detalle = detalle["ciudad"]

        fecha_detalle = detalle[
            "fecha_pronostico"
        ].strftime("%d/%m/%Y")

        nivel_detalle = detalle["nivel_alerta"]

        color_detalle = colores_alertas.get(
            nivel_detalle,
            "#94A3B8"
        )


        # ======================================
        # TARJETA DE RECOMENDACION OPERATIVA
        # ======================================

        with st.container(border=True):

            st.markdown(
                f"### {ciudad_detalle}"
            )

            st.caption(
                f"Fecha del pronóstico: {fecha_detalle}"
            )

            st.markdown(
                f"""
                <span style="
                    color: {color_detalle};
                    font-size: 18px;
                    font-weight: 600;
                ">
                    Prioridad general:
                    {nombres_alertas.get(
                        nivel_detalle,
                        nivel_detalle
                    )}
                </span>
                """,
                unsafe_allow_html=True
            )

            st.divider()

            col_clima1, col_clima2, col_clima3 = (
                st.columns(3)
            )

            col_clima1.metric(
                "Temperatura máxima",
                f'{detalle["temperatura_max"]:.1f} °C'
            )

            col_clima2.metric(
                "Probabilidad de lluvia",
                f'{detalle["probabilidad_lluvia"]:.0f}%'
            )

            col_clima3.metric(
                "Precipitación acumulada",
                f'{detalle["precipitacion_mm"]:.1f} mm'
            )

            st.divider()

            col_inc1, col_inc2, col_inc3 = (
                st.columns(3)
            )

            with col_inc1:

                st.metric(
                    "Incentivo por lluvia",
                    f'{detalle["incentivo_lluvia"]:.0f}%'
                )

                st.caption(
                    "Alerta: "
                    + nombres_alertas.get(
                        detalle["nivel_alerta_lluvia"],
                        detalle["nivel_alerta_lluvia"]
                    )
                )

            with col_inc2:

                st.metric(
                    "Incentivo por calor",
                    f'{detalle["incentivo_calor"]:.0f}%'
                )

                st.caption(
                    "Alerta: "
                    + nombres_alertas.get(
                        detalle["nivel_alerta_calor"],
                        detalle["nivel_alerta_calor"]
                    )
                )

            with col_inc3:

                st.metric(
                    "Incentivo general recomendado",
                    f'{detalle["incentivo_recomendado"]:.0f}%'
                )

                st.caption(
                    "Mayor incentivo entre lluvia y calor"
                )

            st.divider()

            # Distinguir recomendaciones vigentes
            # de pronosticos de fechas anteriores

            es_historico = (
                detalle["fecha_dia"]
                < detalle["hoy_local"]
            )

            if es_historico:

                st.markdown(
                    "#### Recomendación histórica"
                )

                st.write(
                    f"Para el {fecha_detalle}, "
                    f"el pronóstico almacenado de "
                    f"{ciudad_detalle} generó una "
                    f"recomendación de incentivo "
                    f"adicional del "
                    f'{detalle["incentivo_recomendado"]:.0f}%.'
                )

            else:

                st.markdown(
                    "#### Recomendación operativa"
                )

                st.write(
                    f"Se recomienda evaluar un "
                    f"incentivo adicional del "
                    f'{detalle["incentivo_recomendado"]:.0f}% '
                    f"para los repartidores de "
                    f"{ciudad_detalle} durante el "
                    f"{fecha_detalle}, de acuerdo "
                    f"con las condiciones "
                    f"meteorológicas pronosticadas."
                )

            st.caption(
                "Recomendación simulada. Su aplicación "
                "efectiva depende de las políticas "
                "de la empresa y de las condiciones "
                "de seguridad para realizar entregas."
            )

    st.divider()

with tab_datos:
    # ==========================================
    # TABLA DE PRONOSTICOS
    # ==========================================

    st.subheader("Pronósticos y recomendaciones")

    st.caption(
        "Información obtenida del modelo dimensional Gold"
    )

    columnas_tabla = [
        "ciudad",
        "fecha_pronostico",
        "temperatura_max",
        "temperatura_min",
        "probabilidad_lluvia",
        "precipitacion_mm",
        "nivel_alerta_lluvia",
        "incentivo_lluvia",
        "nivel_alerta_calor",
        "incentivo_calor",
        "incentivo_recomendado"
    ]

    st.dataframe(
        df_filtrado[columnas_tabla],
        use_container_width=True,
        hide_index=True,

        column_config={

            "ciudad": "Ciudad",

            "fecha_pronostico": st.column_config.DateColumn(
                "Fecha",
                format="DD/MM/YYYY"
            ),

            "temperatura_max": st.column_config.NumberColumn(
                "Temp. máxima (°C)",
                format="%.1f"
            ),

            "temperatura_min": st.column_config.NumberColumn(
                "Temp. mínima (°C)",
                format="%.1f"
            ),

            "probabilidad_lluvia": st.column_config.NumberColumn(
                "Prob. lluvia (%)",
                format="%d"
            ),

            "precipitacion_mm": st.column_config.NumberColumn(
                "Precipitación (mm)",
                format="%.1f"
            ),

            "nivel_alerta_lluvia": "Alerta lluvia",

            "incentivo_lluvia": st.column_config.NumberColumn(
                "Incentivo lluvia (%)",
                format="%.0f"
            ),

            "nivel_alerta_calor": "Alerta calor",

            "incentivo_calor": st.column_config.NumberColumn(
                "Incentivo calor (%)",
                format="%.0f"
            ),

            "incentivo_recomendado": st.column_config.NumberColumn(
                "Incentivo general (%)",
                format="%.0f"
            )
        }
    )

    # Descargar los pronosticos seleccionados

    datos_exportar = df_filtrado[
        columnas_tabla
    ].copy()

    datos_exportar["fecha_pronostico"] = (
        datos_exportar["fecha_pronostico"]
        .dt.strftime("%Y-%m-%d")
    )

    csv = datos_exportar.to_csv(
        index=False,
        sep=";",
        decimal=","
    ).encode("utf-8-sig")

    st.download_button(
        label="📥 Descargar pronósticos e incentivos",
        data=csv,
        file_name="logiweather_pronosticos.csv",
        mime="text/csv"
    )


# ==========================================
# ACLARACIONES DEL PROYECTO
# ==========================================

st.divider()

st.info(
    "Los incentivos son recomendaciones simuladas "
    "basadas en reglas de negocio meteorológicas. "
    "No representan remuneraciones efectivamente "
    "pagadas a repartidores."
)

st.caption(
    "LogiWeather | TP Final - Grupo 10 | "
    "Infraestructura para Ciencia de Datos"
)
