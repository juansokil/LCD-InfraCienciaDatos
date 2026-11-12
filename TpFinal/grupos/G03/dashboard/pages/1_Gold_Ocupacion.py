import pandas as pd
import plotly.express as px
import streamlit as st

from db import run_query


st.set_page_config(
    page_title="Ecobici CABA · Disponibilidad",
    page_icon="\U0001F6B2",
    layout="wide",
)


# =========================================================
# ENCABEZADO
# =========================================================

st.title(
    "Ecobici CABA — Disponibilidad y ocupación de estaciones"
)

st.markdown(
    """
    Análisis histórico y territorial construido a partir de snapshots
    de **CityBikes**, procesados mediante la arquitectura
    **Bronze → Silver → Gold**.
    """
)

st.info(
    "Los datos representan estados observados de las estaciones "
    "y no viajes individuales."
)


# =========================================================
# CONSULTA GOLD
# =========================================================

SQL = """
SELECT
    f.hour_start_local,
    f.fecha_local,
    f.hora_local,
    f.snapshots_count,

    f.avg_capacity,

    f.avg_free_bikes,
    f.min_free_bikes,
    f.max_free_bikes,

    f.avg_empty_slots,
    f.min_empty_slots,
    f.max_empty_slots,

    f.avg_occupancy_pct,
    f.min_occupancy_pct,
    f.max_occupancy_pct,

    f.zero_bikes_pct,
    f.zero_empty_slots_pct,
    f.fully_operational_pct,

    f.last_snapshot_at_utc,

    e.station_id,
    e.station_name,
    e.address,
    e.latitude,
    e.longitude,
    e.capacity,

    z.barrio,
    z.comuna

FROM gold.fact_ocupacion_por_hora f

JOIN gold.dim_estacion e
    ON e.estacion_key = f.estacion_key

LEFT JOIN gold.dim_zona z
    ON z.zona_key = e.zona_key

ORDER BY
    f.hour_start_local,
    e.station_name;
"""


try:
    df = run_query(SQL)

except Exception as exc:
    st.error(
        "No fue posible consultar la capa Gold."
    )
    st.caption(str(exc))
    st.stop()


if df.empty:
    st.warning(
        "La capa Gold todavía no contiene datos."
    )
    st.stop()


# =========================================================
# PREPARACIÓN
# =========================================================

df["hour_start_local"] = pd.to_datetime(
    df["hour_start_local"]
)

df["fecha_local"] = pd.to_datetime(
    df["fecha_local"]
).dt.date

df["last_snapshot_local"] = (
    pd.to_datetime(
        df["last_snapshot_at_utc"],
        utc=True,
        errors="coerce",
    )
    .dt.tz_convert(
        "America/Argentina/Buenos_Aires"
    )
)


# =========================================================
# FILTROS
# =========================================================

st.sidebar.header(
    "Filtros"
)

fecha_min = df[
    "fecha_local"
].min()

fecha_max = df[
    "fecha_local"
].max()


periodo = st.sidebar.date_input(
    "Período",
    value=(
        fecha_min,
        fecha_max,
    ),
    min_value=fecha_min,
    max_value=fecha_max,
)


df_filtrado = df.copy()


if isinstance(
    periodo,
    (tuple, list),
):

    if len(periodo) == 2:
        desde, hasta = periodo

    elif len(periodo) == 1:
        desde = periodo[0]
        hasta = periodo[0]

    else:
        desde = fecha_min
        hasta = fecha_max

else:
    desde = periodo
    hasta = periodo


df_filtrado = df_filtrado[
    (
        df_filtrado["fecha_local"]
        >= desde
    )
    &
    (
        df_filtrado["fecha_local"]
        <= hasta
    )
]


# ---------------------------------------------------------
# Comuna
# ---------------------------------------------------------

comunas = sorted(
    df_filtrado[
        "comuna"
    ]
    .dropna()
    .astype(int)
    .unique()
)


comuna_sel = st.sidebar.multiselect(
    "Comuna",
    comunas,
)


if comuna_sel:
    df_filtrado = df_filtrado[
        df_filtrado[
            "comuna"
        ].isin(
            comuna_sel
        )
    ]


# ---------------------------------------------------------
# Barrio dependiente de comuna
# ---------------------------------------------------------

barrios = sorted(
    df_filtrado[
        "barrio"
    ]
    .dropna()
    .unique()
)


barrio_sel = st.sidebar.multiselect(
    "Barrio",
    barrios,
)


if barrio_sel:
    df_filtrado = df_filtrado[
        df_filtrado[
            "barrio"
        ].isin(
            barrio_sel
        )
    ]


# ---------------------------------------------------------
# Estación dependiente de barrio
# ---------------------------------------------------------

estaciones = sorted(
    df_filtrado[
        "station_name"
    ]
    .dropna()
    .unique()
)


estacion_sel = st.sidebar.multiselect(
    "Estación",
    estaciones,
)


if estacion_sel:
    df_filtrado = df_filtrado[
        df_filtrado[
            "station_name"
        ].isin(
            estacion_sel
        )
    ]


if df_filtrado.empty:
    st.warning(
        "No hay datos para los filtros seleccionados."
    )
    st.stop()


# =========================================================
# ESTADO GENERAL
# =========================================================

ultima_hora = df_filtrado[
    "hour_start_local"
].max()


ultimo = df_filtrado[
    df_filtrado[
        "hour_start_local"
    ]
    == ultima_hora
].copy()


ultima_observacion = (
    ultimo[
        "last_snapshot_local"
    ].max()
)


st.subheader(
    "Estado general"
)


c1, c2, c3, c4, c5 = st.columns(
    5
)


c1.metric(
    "Estaciones analizadas",
    ultimo[
        "station_id"
    ].nunique(),
)


c2.metric(
    "Bicicletas promedio",
    f"{ultimo['avg_free_bikes'].mean():.1f}",
)


c3.metric(
    "Espacios libres promedio",
    f"{ultimo['avg_empty_slots'].mean():.1f}",
)


c4.metric(
    "Ocupación promedio",
    f"{ultimo['avg_occupancy_pct'].mean():.1f} %",
)


if pd.notna(
    ultima_observacion
):
    ultima_texto = (
        ultima_observacion.strftime(
            "%d/%m %H:%M"
        )
    )

else:
    ultima_texto = (
        ultima_hora.strftime(
            "%d/%m %H:%M"
        )
    )


c5.metric(
    "Última observación",
    ultima_texto,
)


st.divider()


# =========================================================
# 1. DISPONIBILIDAD
# =========================================================

st.header(
    "1. Disponibilidad"
)

st.caption(
    "Situaciones observadas durante la última hora "
    "disponible para los filtros seleccionados."
)


col_retiro, col_devolucion = st.columns(
    2
)


# ---------------------------------------------------------
# RETIRO
# ---------------------------------------------------------

with col_retiro:

    st.subheader(
        "Baja disponibilidad para retiro"
    )

    st.caption(
        "Estaciones que durante la última hora presentaron "
        "una mayor proporción de observaciones sin bicicletas."
    )


    ranking_retiro = (
        ultimo[
            [
                "station_name",
                "barrio",
                "comuna",
                "avg_free_bikes",
                "zero_bikes_pct",
            ]
        ]
        .sort_values(
            [
                "zero_bikes_pct",
                "avg_free_bikes",
            ],
            ascending=[
                False,
                True,
            ],
        )
        .head(10)
    )


    fig_retiro = px.bar(
        ranking_retiro,
        x="zero_bikes_pct",
        y="station_name",
        orientation="h",
        hover_data={
            "barrio": True,
            "comuna": True,
            "avg_free_bikes": ":.1f",
        },
        labels={
            "station_name":
                "Estación",
            "zero_bikes_pct":
                "% de observaciones sin bicicletas",
            "avg_free_bikes":
                "Bicicletas promedio",
        },
    )


    fig_retiro.update_layout(
        yaxis={
            "categoryorder":
                "total ascending"
        },
        xaxis_range=[
            0,
            100,
        ],
        height=450,
    )


    st.plotly_chart(
        fig_retiro,
        use_container_width=True,
    )


# ---------------------------------------------------------
# DEVOLUCIÓN
# ---------------------------------------------------------

with col_devolucion:

    st.subheader(
        "Baja disponibilidad para devolución"
    )

    st.caption(
        "Estaciones que durante la última hora presentaron "
        "una mayor proporción de observaciones sin espacios "
        "disponibles para devolución."
    )


    ranking_devolucion = (
        ultimo[
            [
                "station_name",
                "barrio",
                "comuna",
                "avg_empty_slots",
                "zero_empty_slots_pct",
            ]
        ]
        .sort_values(
            [
                "zero_empty_slots_pct",
                "avg_empty_slots",
            ],
            ascending=[
                False,
                True,
            ],
        )
        .head(10)
    )


    fig_devolucion = px.bar(
        ranking_devolucion,
        x="zero_empty_slots_pct",
        y="station_name",
        orientation="h",
        hover_data={
            "barrio": True,
            "comuna": True,
            "avg_empty_slots": ":.1f",
        },
        labels={
            "station_name":
                "Estación",
            "zero_empty_slots_pct":
                "% de observaciones sin espacios",
            "avg_empty_slots":
                "Espacios libres promedio",
        },
    )


    fig_devolucion.update_layout(
        yaxis={
            "categoryorder":
                "total ascending"
        },
        xaxis_range=[
            0,
            100,
        ],
        height=450,
    )


    st.plotly_chart(
        fig_devolucion,
        use_container_width=True,
    )


st.divider()


# =========================================================
# 2. ANÁLISIS TERRITORIAL
# =========================================================

st.header(
    "2. Análisis territorial"
)

st.caption(
    "El enriquecimiento realizado en Silver permite "
    "analizar la disponibilidad por barrio y comuna."
)


col_territorio, col_mapa = st.columns(
    [
        1,
        1.4,
    ]
)


# ---------------------------------------------------------
# OCUPACIÓN POR COMUNA / BARRIO
# ---------------------------------------------------------

with col_territorio:

    st.subheader(
        "Ocupación por territorio"
    )


    nivel = st.selectbox(
        "Agrupar por",
        [
            "Comuna",
            "Barrio",
        ],
        label_visibility="collapsed",
    )


    if nivel == "Comuna":

        territorial = (
            df_filtrado
            .dropna(
                subset=[
                    "comuna"
                ]
            )
            .assign(
                territorio=lambda x:
                    "Comuna "
                    + x[
                        "comuna"
                    ]
                    .astype(int)
                    .astype(str)
            )
            .groupby(
                "territorio",
                as_index=False,
            )
            .agg(
                ocupacion_promedio=(
                    "avg_occupancy_pct",
                    "mean",
                )
            )
            .sort_values(
                "ocupacion_promedio",
                ascending=True,
            )
        )

    else:

        territorial = (
            df_filtrado
            .dropna(
                subset=[
                    "barrio"
                ]
            )
            .groupby(
                "barrio",
                as_index=False,
            )
            .agg(
                ocupacion_promedio=(
                    "avg_occupancy_pct",
                    "mean",
                )
            )
            .rename(
                columns={
                    "barrio":
                        "territorio"
                }
            )
            .sort_values(
                "ocupacion_promedio",
                ascending=True,
            )
        )


    fig_territorio = px.bar(
        territorial,
        x="ocupacion_promedio",
        y="territorio",
        orientation="h",
        labels={
            "territorio":
                nivel,
            "ocupacion_promedio":
                "Ocupación promedio (%)",
        },
    )


    fig_territorio.update_layout(
        height=600
    )


    st.plotly_chart(
        fig_territorio,
        use_container_width=True,
    )


# ---------------------------------------------------------
# MAPA
# ---------------------------------------------------------

with col_mapa:

    st.subheader(
        "Estado territorial de las estaciones"
    )


    mapa = ultimo[
        [
            "station_name",
            "barrio",
            "comuna",
            "latitude",
            "longitude",
            "avg_capacity",
            "avg_free_bikes",
            "avg_empty_slots",
            "avg_occupancy_pct",
        ]
    ].copy()


    mapa = mapa.dropna(
        subset=[
            "latitude",
            "longitude",
        ]
    )


    def clasificar_estado(
        ocupacion
    ):

        if pd.isna(
            ocupacion
        ):
            return "Sin dato"

        if ocupacion <= 20:
            return (
                "Baja disponibilidad para retiro"
            )

        if ocupacion >= 80:
            return (
                "Pocos espacios para devolución"
            )

        return "Equilibrada"


    mapa[
        "estado_disponibilidad"
    ] = (
        mapa[
            "avg_occupancy_pct"
        ]
        .apply(
            clasificar_estado
        )
    )


    fig_mapa = px.scatter_map(
        mapa,
        lat="latitude",
        lon="longitude",
        color="estado_disponibilidad",
        size="avg_capacity",
        hover_name="station_name",
        hover_data={
            "barrio": True,
            "comuna": True,
            "avg_free_bikes": ":.1f",
            "avg_empty_slots": ":.1f",
            "avg_occupancy_pct": ":.1f",
            "avg_capacity": False,
            "latitude": False,
            "longitude": False,
        },
        zoom=11,
        map_style="open-street-map",
        labels={
            "estado_disponibilidad":
                "Estado",
            "avg_free_bikes":
                "Bicicletas",
            "avg_empty_slots":
                "Espacios libres",
            "avg_occupancy_pct":
                "Ocupación (%)",
        },
    )


    fig_mapa.update_layout(
        height=600
    )


    st.plotly_chart(
        fig_mapa,
        use_container_width=True,
    )


st.caption(
    "Los umbrales del mapa (≤20 % y ≥80 %) se utilizan "
    "como criterio visual de clasificación y no representan "
    "una definición oficial de Ecobici."
)


st.divider()


# =========================================================
# 3. ANÁLISIS TEMPORAL
# =========================================================

st.header(
    "3. Análisis temporal"
)

st.caption(
    "Gold tiene granularidad estación × hora. "
    "Esto permite observar cómo cambia la ocupación "
    "a lo largo del tiempo."
)


# ---------------------------------------------------------
# EVOLUCIÓN CRONOLÓGICA
# ---------------------------------------------------------

st.subheader(
    "Evolución horaria de la ocupación"
)

st.caption(
    "Cada punto representa una hora con observaciones disponibles. "
    "La línea conecta únicamente los períodos registrados."
)


evolucion = (
    df_filtrado
    .groupby(
        "hour_start_local",
        as_index=False,
    )
    .agg(
        ocupacion_promedio=(
            "avg_occupancy_pct",
            "mean",
        ),
        bicicletas_promedio=(
            "avg_free_bikes",
            "mean",
        ),
        espacios_promedio=(
            "avg_empty_slots",
            "mean",
        ),
    )
    .sort_values(
        "hour_start_local"
    )
)


fig_evolucion = px.line(
    evolucion,
    x="hour_start_local",
    y="ocupacion_promedio",
    markers=True,
    hover_data={
        "bicicletas_promedio":
            ":.1f",
        "espacios_promedio":
            ":.1f",
    },
    labels={
        "hour_start_local":
            "Fecha y hora",
        "ocupacion_promedio":
            "Ocupación promedio (%)",
        "bicicletas_promedio":
            "Bicicletas promedio",
        "espacios_promedio":
            "Espacios promedio",
    },
)


fig_evolucion.update_layout(
    height=420
)


st.plotly_chart(
    fig_evolucion,
    use_container_width=True,
)


# =========================================================
# HEATMAP
# =========================================================

st.subheader(
    "Ocupación por hora y comuna"
)

st.caption(
    "Esta vista combina el enriquecimiento territorial "
    "de Silver con la agregación horaria de Gold."
)


heatmap_df = (
    df_filtrado
    .dropna(
        subset=[
            "comuna"
        ]
    )
    .assign(
        comuna_label=lambda x:
            "Comuna "
            + x[
                "comuna"
            ]
            .astype(int)
            .astype(str)
    )
    .groupby(
        [
            "comuna_label",
            "hora_local",
        ],
        as_index=False,
    )
    .agg(
        ocupacion_promedio=(
            "avg_occupancy_pct",
            "mean",
        )
    )
)


if (
    heatmap_df[
        "hora_local"
    ].nunique() > 1
    and
    heatmap_df[
        "comuna_label"
    ].nunique() > 1
):

    fig_heatmap = px.density_heatmap(
        heatmap_df,
        x="hora_local",
        y="comuna_label",
        z="ocupacion_promedio",
        histfunc="avg",
        labels={
            "hora_local":
                "Hora",
            "comuna_label":
                "Comuna",
            "ocupacion_promedio":
                "Ocupación promedio (%)",
        },
    )


    fig_heatmap.update_layout(
        height=500
    )


    st.plotly_chart(
        fig_heatmap,
        use_container_width=True,
    )

else:

    st.info(
        "Todavía no hay suficientes horas o comunas "
        "para construir una visualización comparativa."
    )


st.divider()


# =========================================================
# DATOS GOLD
# =========================================================

with st.expander(
    "Ver datos Gold utilizados"
):

    columnas_detalle = [
        "hour_start_local",
        "station_name",
        "barrio",
        "comuna",
        "avg_capacity",
        "avg_free_bikes",
        "avg_empty_slots",
        "avg_occupancy_pct",
        "zero_bikes_pct",
        "zero_empty_slots_pct",
        "snapshots_count",
    ]


    st.dataframe(
        df_filtrado[
            columnas_detalle
        ],
        use_container_width=True,
        hide_index=True,
    )