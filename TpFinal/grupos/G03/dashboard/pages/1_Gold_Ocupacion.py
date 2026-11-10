import pandas as pd
import plotly.express as px
import streamlit as st

from db import run_query


st.set_page_config(
    page_title="Gold · Ocupación",
    page_icon="\U0001F947",
    layout="wide",
)

st.title("Gold · Ocupación de estaciones")

st.caption(
    """
    Los datos de CityBikes representan snapshots de disponibilidad,
    no viajes individuales. Por eso el patrón horario se interpreta
    como **ocupación y disponibilidad observada por hora**.
    """
)


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
    st.warning("La capa Gold todavía no contiene datos.")
    st.stop()


# =========================================================
# FILTROS
# =========================================================

st.sidebar.header("Filtros")


comunas = sorted(
    df["comuna"]
    .dropna()
    .astype(int)
    .unique()
)

comuna_sel = st.sidebar.multiselect(
    "Comuna",
    comunas,
)


df_filtrado = df.copy()

if comuna_sel:
    df_filtrado = df_filtrado[
        df_filtrado["comuna"]
        .isin(comuna_sel)
    ]


barrios = sorted(
    df_filtrado["barrio"]
    .dropna()
    .unique()
)

barrio_sel = st.sidebar.multiselect(
    "Barrio",
    barrios,
)

if barrio_sel:
    df_filtrado = df_filtrado[
        df_filtrado["barrio"]
        .isin(barrio_sel)
    ]


estaciones = sorted(
    df_filtrado["station_name"]
    .dropna()
    .unique()
)

estacion_sel = st.sidebar.multiselect(
    "Estación",
    estaciones,
)

if estacion_sel:
    df_filtrado = df_filtrado[
        df_filtrado["station_name"]
        .isin(estacion_sel)
    ]


if df_filtrado.empty:
    st.warning(
        "No hay datos para los filtros seleccionados."
    )
    st.stop()


# =========================================================
# KPIs
# =========================================================

ultima_hora = df_filtrado[
    "hour_start_local"
].max()

ultimo = df_filtrado[
    df_filtrado["hour_start_local"]
    == ultima_hora
]


c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Estaciones",
    ultimo["station_id"].nunique(),
)

c2.metric(
    "Bicicletas promedio",
    f"{ultimo['avg_free_bikes'].mean():.1f}",
)

c3.metric(
    "Slots libres promedio",
    f"{ultimo['avg_empty_slots'].mean():.1f}",
)

c4.metric(
    "Ocupación promedio",
    f"{ultimo['avg_occupancy_pct'].mean():.1f} %",
)


st.caption(
    f"Última hora disponible: {ultima_hora}"
)


# =========================================================
# ESTACIONES MÁS SATURADAS
# =========================================================

st.subheader(
    "Estaciones más saturadas para devolución"
)

st.caption(
    """
    Una ocupación alta implica muchas bicicletas disponibles
    y pocos espacios libres para devolver una bicicleta.
    """
)


ranking_devolucion = (
    df_filtrado
    .groupby(
        [
            "station_id",
            "station_name",
            "barrio",
            "comuna",
        ],
        dropna=False,
    )
    .agg(
        ocupacion_promedio=(
            "avg_occupancy_pct",
            "mean",
        ),
        pct_sin_slots=(
            "zero_empty_slots_pct",
            "mean",
        ),
    )
    .reset_index()
    .sort_values(
        "ocupacion_promedio",
        ascending=False,
    )
    .head(15)
)


fig = px.bar(
    ranking_devolucion,
    x="ocupacion_promedio",
    y="station_name",
    orientation="h",
    labels={
        "ocupacion_promedio":
            "Ocupación promedio (%)",
        "station_name":
            "Estación",
    },
)

fig.update_layout(
    yaxis={
        "categoryorder": "total ascending"
    }
)

st.plotly_chart(
    fig,
    use_container_width=True,
)


# =========================================================
# ESTACIONES CRÍTICAS PARA RETIRO
# =========================================================

st.subheader(
    "Estaciones críticas para retiro"
)

st.caption(
    """
    Una ocupación baja implica pocas bicicletas disponibles.
    """
)


ranking_retiro = (
    df_filtrado
    .groupby(
        [
            "station_id",
            "station_name",
            "barrio",
            "comuna",
        ],
        dropna=False,
    )
    .agg(
        ocupacion_promedio=(
            "avg_occupancy_pct",
            "mean",
        ),
        pct_sin_bicicletas=(
            "zero_bikes_pct",
            "mean",
        ),
    )
    .reset_index()
    .sort_values(
        "ocupacion_promedio",
        ascending=True,
    )
    .head(15)
)


fig = px.bar(
    ranking_retiro,
    x="ocupacion_promedio",
    y="station_name",
    orientation="h",
    labels={
        "ocupacion_promedio":
            "Ocupación promedio (%)",
        "station_name":
            "Estación",
    },
)

fig.update_layout(
    yaxis={
        "categoryorder": "total descending"
    }
)

st.plotly_chart(
    fig,
    use_container_width=True,
)


# =========================================================
# PATRÓN POR HORA
# =========================================================

st.subheader(
    "Patrón de ocupación por hora"
)


patron = (
    df_filtrado
    .groupby(
        "hora_local",
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
        slots_promedio=(
            "avg_empty_slots",
            "mean",
        ),
    )
    .sort_values(
        "hora_local"
    )
)


fig = px.line(
    patron,
    x="hora_local",
    y="ocupacion_promedio",
    markers=True,
    labels={
        "hora_local":
            "Hora del día",
        "ocupacion_promedio":
            "Ocupación promedio (%)",
    },
)

st.plotly_chart(
    fig,
    use_container_width=True,
)


# =========================================================
# MAPA
# =========================================================

st.subheader(
    "Mapa de disponibilidad"
)

st.caption(
    """
    Estado correspondiente a la última hora disponible
    para los filtros seleccionados.
    """
)


mapa = (
    ultimo[
        [
            "station_name",
            "barrio",
            "comuna",
            "latitude",
            "longitude",
            "avg_free_bikes",
            "avg_empty_slots",
            "avg_occupancy_pct",
        ]
    ]
    .dropna(
        subset=[
            "latitude",
            "longitude",
        ]
    )
)


fig = px.scatter_map(
    mapa,
    lat="latitude",
    lon="longitude",
    color="avg_occupancy_pct",
    size="avg_free_bikes",
    hover_name="station_name",
    hover_data={
        "barrio": True,
        "comuna": True,
        "avg_free_bikes": ":.1f",
        "avg_empty_slots": ":.1f",
        "avg_occupancy_pct": ":.1f",
        "latitude": False,
        "longitude": False,
    },
    zoom=10,
    map_style="open-street-map",
    labels={
        "avg_occupancy_pct":
            "Ocupación (%)",
        "avg_free_bikes":
            "Bicicletas",
        "avg_empty_slots":
            "Slots libres",
    },
)

st.plotly_chart(
    fig,
    use_container_width=True,
)


# =========================================================
# DATOS
# =========================================================

with st.expander(
    "Ver datos Gold utilizados"
):
    st.dataframe(
        df_filtrado,
        use_container_width=True,
        hide_index=True,
    )
