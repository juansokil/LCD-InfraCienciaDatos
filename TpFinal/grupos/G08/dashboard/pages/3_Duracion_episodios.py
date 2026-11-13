import plotly.express as px
import streamlit as st

from comun import columna_zona, formato_entero, selector_red
from db import requiere_gold, run_query

st.title("Duración de episodios sin bicicletas")
st.caption(
    "Un episodio empieza en el primer snapshot con cero bicicletas y termina en el "
    "primer snapshot posterior con bicicletas: ¿se repone en 5 minutos o en 2 horas?"
)
requiere_gold()

red, red_nombre, tiene_barrios = selector_red("red_duracion_episodios")
df = run_query("""
    SELECT
        e.station_id,
        COALESCE(d.station_name, e.station_id) AS station_name,
        d.ciudad, d.zona, d.zona_padre, d.zona_nivel,
        e.inicio_local,
        e.hora_inicio,
        e.snapshots_vacios,
        e.duracion_minutos
    FROM gold.fact_episodio_sin_bicis e
    JOIN gold.dim_estacion d USING (network_id, station_id)
    WHERE e.network_id = :red
""", {"red": red})
if df.empty:
    st.info(
        "Todavía no hay episodios completos para esta red: hace falta ver la estación "
        "con bicis, después vacía y después repuesta, sin huecos de más de 10 minutos."
    )
    st.stop()

df["duracion_minutos"] = df["duracion_minutos"].astype(float)
df, nivel = columna_zona(df, tiene_barrios, "nivel_zona_duracion")

c1, c2, c3 = st.columns(3)
c1.metric("Episodios completos", formato_entero(len(df)))
c2.metric("Duración mediana", f"{df['duracion_minutos'].median():.0f} min")
c3.metric("Percentil 90", f"{df['duracion_minutos'].quantile(0.9):.0f} min")

# Mediana por zona: menos sensible que el promedio a episodios muy largos.
por_zona = (
    df.groupby("zona_grafico", as_index=False)
    .agg(
        episodios=("duracion_minutos", "size"),
        mediana_minutos=("duracion_minutos", "median"),
        p90_minutos=("duracion_minutos", lambda valores: valores.quantile(0.90)),
    )
    .nlargest(15, "mediana_minutos")
    .sort_values("mediana_minutos")
)
fig_zonas = px.bar(
    por_zona,
    x="mediana_minutos",
    y="zona_grafico",
    orientation="h",
    hover_data=["episodios", "p90_minutos"],
    labels={
        "mediana_minutos": "Duración mediana (minutos)",
        "zona_grafico": nivel,
        "episodios": "Episodios completos",
        "p90_minutos": "Percentil 90 (minutos)",
    },
)
st.subheader(f"Duración mediana por {nivel.lower()}")
st.plotly_chart(fig_zonas, use_container_width=True)

# Por estacion: las que mas tardan en reponerse (con al menos 3 episodios).
por_estacion = (
    df.groupby(["station_id", "station_name"], as_index=False)
    .agg(
        episodios=("duracion_minutos", "size"),
        mediana_minutos=("duracion_minutos", "median"),
        horas_vacia=("duracion_minutos", lambda valores: valores.sum() / 60),
    )
)
top = por_estacion[por_estacion["episodios"] >= 3].nlargest(15, "mediana_minutos")
if not top.empty:
    fig_estaciones = px.bar(
        top.sort_values("mediana_minutos"),
        x="mediana_minutos",
        y="station_name",
        orientation="h",
        hover_data=["episodios", "horas_vacia"],
        labels={
            "mediana_minutos": "Duración mediana (minutos)",
            "station_name": "Estación",
            "episodios": "Episodios",
            "horas_vacia": "Horas vacía en total",
        },
    )
    st.subheader("Estaciones que más tardan en reponerse (≥ 3 episodios)")
    st.plotly_chart(fig_estaciones, use_container_width=True)

# Por hora local de inicio: mediana y dispersion.
df["hora_etiqueta"] = df["hora_inicio"].map(lambda hora: f"{int(hora):02d}:00")
fig_horas = px.box(
    df,
    x="hora_etiqueta",
    y="duracion_minutos",
    points="outliers",
    category_orders={"hora_etiqueta": [f"{h:02d}:00" for h in range(24)]},
    labels={
        "hora_etiqueta": "Hora local de inicio",
        "duracion_minutos": "Duración (minutos)",
    },
)
st.subheader("Duración según la hora en que empieza el episodio")
st.plotly_chart(fig_horas, use_container_width=True)

st.subheader("Episodios más largos")
st.dataframe(
    df.nlargest(200, "duracion_minutos")[
        ["station_name", "zona_grafico", "inicio_local", "duracion_minutos", "snapshots_vacios"]
    ].rename(columns={
        "station_name": "Estación",
        "zona_grafico": nivel,
        "inicio_local": "Inicio (hora local)",
        "duracion_minutos": "Duración (min)",
        "snapshots_vacios": "Snapshots vacíos",
    }),
    use_container_width=True,
    hide_index=True,
)
st.caption(
    "Solo episodios cerrados: con un snapshot con bicis antes y otro después, sin huecos "
    "de más de 10 minutos. La resolución es de 5 minutos (un snapshot). Los episodios "
    "abiertos aparecen cuando la estación se repone."
)
