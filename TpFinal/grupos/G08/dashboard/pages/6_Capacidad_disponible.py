import pandas as pd
import plotly.express as px
import streamlit as st

from comun import columna_zona, formato_entero, selector_red, tasa
from db import requiere_gold, run_query

UMBRAL_SNAPSHOT_MINUTOS = 15  # Tres ciclos del pipeline, que corre cada 5 minutos.

st.title("Capacidad realmente disponible")
st.caption(
    "Anclajes fuera de servicio, estaciones que no alquilan y estaciones que no "
    "reportan hace rato, por red y zona."
)
requiere_gold()

# Estado actual: la ultima foto de cada estacion. La antiguedad se mide contra
# el reloj de ahora, por eso se calcula al consultar y no en gold.
actual = run_query("""
    SELECT
        c.network_id,
        d.red_nombre,
        c.station_id,
        COALESCE(d.station_name, c.station_id) AS station_name,
        d.ciudad, d.zona, d.zona_padre, d.zona_nivel,
        c.free_bikes, c.empty_slots, c.slots, c.docks_fuera_servicio,
        c.alquila, c.recibe, c.operador_viejo, c.sin_dato_operador,
        EXTRACT(EPOCH FROM (now() - c.snapshot_ts)) / 60.0 AS minutos_sin_snapshot
    FROM gold.fact_capacidad_actual c
    JOIN gold.dim_estacion d USING (network_id, station_id)
""")
actual["minutos_sin_snapshot"] = pd.to_numeric(actual["minutos_sin_snapshot"]).astype(float)
# Estaciones dadas de baja: no aparecen hace mas de un dia respecto del ultimo
# snapshot de SU red (no del reloj: si el stack estuvo apagado, no son bajas).
atraso_red = (
    actual["minutos_sin_snapshot"]
    - actual.groupby("network_id")["minutos_sin_snapshot"].transform("min")
)
bajas = actual[atraso_red > 24 * 60]
actual = actual[atraso_red <= 24 * 60].copy()
actual["reporta"] = actual["minutos_sin_snapshot"] <= UMBRAL_SNAPSHOT_MINUTOS
actual["no_alquila"] = actual["alquila"].eq(False)
actual["no_recibe"] = actual["recibe"].eq(False)
actual["alquiler_desconocido"] = actual["alquila"].isna()
# Capacidad confiable: la estacion reporto hace poco y el operador no esta
# atrasado. Si el operador no manda fecha (sin_dato_operador) no se puede
# saber si esta atrasado: se usa, pero se cuenta aparte.
actual["confiable"] = actual["reporta"] & ~actual["operador_viejo"] & actual["slots"].notna()
actual["slots_confiables"] = actual["slots"].where(actual["confiable"], 0).fillna(0)
actual["bicis_retirables"] = actual["free_bikes"].where(
    actual["confiable"] & actual["alquila"].eq(True), 0).fillna(0)
actual["anclajes_devolucion"] = actual["empty_slots"].where(
    actual["confiable"] & actual["recibe"].ne(False), 0).fillna(0)
actual["anclajes_fuera_servicio"] = actual["docks_fuera_servicio"].where(
    actual["confiable"], 0).fillna(0)

conteos = ["slots_confiables", "bicis_retirables", "anclajes_devolucion", "anclajes_fuera_servicio"]

def problemas_por(columna: str) -> pd.DataFrame:
    return actual.groupby(columna, as_index=False).agg(
        estaciones=("station_id", "size"),
        no_alquilan=("no_alquila", "sum"),
        no_reciben=("no_recibe", "sum"),
        alquiler_desconocido=("alquiler_desconocido", "sum"),
        sin_reportar=("reporta", lambda valores: int((~valores).sum())),
        operador_viejo=("operador_viejo", "sum"),
        sin_dato_operador=("sin_dato_operador", "sum"),
    )


# 1. Comparacion entre redes, ahora.
st.subheader("Estado actual por red")
redes = problemas_por("red_nombre")
redes_largo = redes.melt(
    id_vars=["red_nombre", "estaciones"],
    value_vars=["no_alquilan", "no_reciben", "sin_reportar", "operador_viejo"],
    var_name="problema",
    value_name="cantidad",
)
redes_largo["porcentaje"] = tasa(redes_largo["cantidad"], redes_largo["estaciones"])
redes_largo["problema"] = redes_largo["problema"].map({
    "no_alquilan": "No alquilan",
    "no_reciben": "No reciben devoluciones",
    "sin_reportar": f"Sin snapshot hace > {UMBRAL_SNAPSHOT_MINUTOS} min",
    "operador_viejo": "Dato del operador viejo (> 60 min)",
})
# Un panel por problema: cada uno compara las redes en un solo problema, y un
# cero se lee como "0%" escrito en vez de como un hueco entre barras agrupadas.
redes_largo["etiqueta"] = (
    redes_largo["porcentaje"].round(0).astype("Int64").astype(str) + "% · "
    + redes_largo["cantidad"].astype(int).astype(str) + " de "
    + redes_largo["estaciones"].astype(int).astype(str)
)
tope_x = max(10.0, float(redes_largo["porcentaje"].max() or 0) * 1.6)
fig_redes = px.bar(
    redes_largo,
    x="porcentaje",
    y="red_nombre",
    facet_col="problema",
    facet_col_wrap=2,
    facet_row_spacing=0.16,
    facet_col_spacing=0.06,
    orientation="h",
    text="etiqueta",
    hover_data=["cantidad", "estaciones"],
    labels={"porcentaje": "Estaciones (%)", "red_nombre": "", "problema": "",
            "cantidad": "Estaciones con el problema", "estaciones": "Estaciones"},
)
# Titulo de cada panel en negrita, pegado al recuadro.
fig_redes.for_each_annotation(
    lambda a: a.update(text=f"<b>{a.text.split('=')[-1]}</b>", yshift=-6, font_size=14)
)
# Un solo color: el titulo del panel ya dice que problema es.
fig_redes.update_traces(marker_color="#e76f51", textposition="outside", cliponaxis=False)
# Recuadro y grilla vertical en cada panel, para que se lean como tarjetas.
BORDE = "rgba(128, 128, 128, 0.45)"
fig_redes.update_xaxes(
    range=[0, tope_x], ticksuffix="%",
    showline=True, mirror=True, linecolor=BORDE,
    showgrid=True, gridcolor="rgba(128, 128, 128, 0.15)",
)
fig_redes.update_yaxes(showline=True, mirror=True, linecolor=BORDE, ticksuffix="  ")
fig_redes.update_layout(height=460, margin=dict(t=40, b=20, l=10, r=10), bargap=0.35)
st.plotly_chart(fig_redes, use_container_width=True)
if not bajas.empty:
    st.caption(
        f"No se cuentan {len(bajas)} estación(es) que la API dejó de informar hace más "
        "de un día (probablemente dadas de baja): "
        + ", ".join(sorted(bajas["station_name"].astype(str))[:10])
        + ("…" if len(bajas) > 10 else "")
    )

capacidad_red = actual.groupby("red_nombre", as_index=False)[conteos].sum()
capacidad_red["% anclajes fuera de servicio"] = tasa(
    capacidad_red["anclajes_fuera_servicio"], capacidad_red["slots_confiables"]
)
st.dataframe(
    capacidad_red.rename(columns={
        "red_nombre": "Red",
        "slots_confiables": "Anclajes instalados (datos confiables)",
        "bicis_retirables": "Bicis para retirar",
        "anclajes_devolucion": "Anclajes para devolver",
        "anclajes_fuera_servicio": "Anclajes fuera de servicio",
    }),
    use_container_width=True,
    hide_index=True,
)

# 2. Evolucion diaria por red (historico de fact_estacion_hora).
historia = run_query("""
    SELECT
        d.red_nombre,
        f.fecha,
        sum(f.snapshots_total)          AS total,
        sum(f.snapshots_no_alquila)     AS no_alquila,
        sum(f.snapshots_no_recibe)      AS no_recibe,
        sum(f.snapshots_operador_viejo) AS operador_viejo
    FROM gold.fact_estacion_hora f
    JOIN gold.dim_estacion d USING (network_id, station_id)
    GROUP BY d.red_nombre, f.fecha
    ORDER BY f.fecha
""")
if historia["fecha"].nunique() > 1:
    for col in ["no_alquila", "no_recibe", "operador_viejo"]:
        historia[col] = tasa(historia[col], historia["total"])
    historia_larga = historia.melt(
        id_vars=["red_nombre", "fecha"],
        value_vars=["no_alquila", "no_recibe", "operador_viejo"],
        var_name="problema",
        value_name="porcentaje",
    )
    historia_larga["problema"] = historia_larga["problema"].map({
        "no_alquila": "No alquila",
        "no_recibe": "No recibe devoluciones",
        "operador_viejo": "Dato del operador viejo",
    })
    fig_historia = px.line(
        historia_larga,
        x="fecha",
        y="porcentaje",
        color="red_nombre",
        facet_row="problema",
        markers=True,
        labels={"porcentaje": "% de snapshots", "fecha": "Fecha", "red_nombre": "Red"},
    )
    fig_historia.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig_historia.update_layout(height=650)
    st.subheader("Evolución diaria por red")
    st.plotly_chart(fig_historia, use_container_width=True)

# 3. Por zona dentro de una red.
st.subheader("Detalle por zona")
red, red_nombre, tiene_barrios = selector_red("red_capacidad_disponible")
df_red, nivel = columna_zona(actual[actual["network_id"] == red], tiene_barrios,
                             "nivel_zona_capacidad")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Estaciones", formato_entero(len(df_red)))
k2.metric("No alquilan", formato_entero(df_red["no_alquila"].sum()))
k3.metric(f"Sin snapshot > {UMBRAL_SNAPSHOT_MINUTOS} min", formato_entero((~df_red["reporta"]).sum()))
k4.metric("Operador viejo", formato_entero(df_red["operador_viejo"].sum()))
k5.metric("Anclajes fuera de servicio¹", formato_entero(df_red["anclajes_fuera_servicio"].sum()))
st.caption(
    f"{formato_entero(df_red['sin_dato_operador'].sum())} estación(es) sin fecha del "
    f"operador y {formato_entero(df_red['alquiler_desconocido'].sum())} con estado de "
    "alquiler desconocido. ¹Solo estaciones con datos confiables (snapshot reciente y "
    "operador al día)."
)

por_zona = df_red.groupby("zona_grafico", as_index=False)[conteos].sum()
por_zona["pct_bicis_retirables"] = tasa(por_zona["bicis_retirables"], por_zona["slots_confiables"])
por_zona["pct_anclajes_devolucion"] = tasa(por_zona["anclajes_devolucion"], por_zona["slots_confiables"])
por_zona["pct_anclajes_fuera"] = tasa(por_zona["anclajes_fuera_servicio"], por_zona["slots_confiables"])

capacidad_larga = por_zona.melt(
    id_vars=["zona_grafico", *conteos],
    value_vars=["pct_bicis_retirables", "pct_anclajes_devolucion", "pct_anclajes_fuera"],
    var_name="tipo_capacidad",
    value_name="porcentaje",
).dropna(subset=["porcentaje"])
capacidad_larga["tipo_capacidad"] = capacidad_larga["tipo_capacidad"].map({
    "pct_bicis_retirables": "Bicis disponibles para retirar",
    "pct_anclajes_devolucion": "Anclajes disponibles para devolver",
    "pct_anclajes_fuera": "Anclajes fuera de servicio",
})

if capacidad_larga.empty:
    st.info("No hay capacidad instalada conocida con datos suficientemente recientes.")
else:
    orden_zonas = por_zona.sort_values("slots_confiables")["zona_grafico"].tolist()
    fig_capacidad = px.bar(
        capacidad_larga,
        x="porcentaje",
        y="zona_grafico",
        color="tipo_capacidad",
        barmode="group",
        orientation="h",
        hover_data=conteos,
        color_discrete_map={
            "Bicis disponibles para retirar": "#2a9d8f",
            "Anclajes disponibles para devolver": "#277da1",
            "Anclajes fuera de servicio": "#d62828",
        },
        labels={
            "porcentaje": "Parte de los anclajes instalados (%)",
            "zona_grafico": nivel,
            "tipo_capacidad": "",
            "slots_confiables": "Anclajes instalados (datos confiables)",
            "bicis_retirables": "Bicis para retirar",
            "anclajes_devolucion": "Anclajes para devolver",
            "anclajes_fuera_servicio": "Anclajes fuera de servicio",
        },
    )
    fig_capacidad.update_xaxes(range=[0, 100], ticksuffix="%")
    fig_capacidad.update_yaxes(categoryorder="array", categoryarray=orden_zonas)
    fig_capacidad.update_layout(height=max(300, min(950, 32 * len(orden_zonas))))
    st.plotly_chart(fig_capacidad, use_container_width=True)

tabla = por_zona[["zona_grafico", *conteos, "pct_anclajes_fuera"]].merge(
    df_red.groupby("zona_grafico", as_index=False).agg(
        estaciones=("station_id", "size"),
        no_alquilan=("no_alquila", "sum"),
        sin_reportar=("reporta", lambda valores: int((~valores).sum())),
        operador_viejo=("operador_viejo", "sum"),
    ),
    on="zona_grafico",
    how="left",
).rename(columns={
    "zona_grafico": nivel,
    "slots_confiables": "Anclajes instalados (datos confiables)",
    "bicis_retirables": "Bicis para retirar",
    "anclajes_devolucion": "Anclajes para devolver",
    "anclajes_fuera_servicio": "Anclajes fuera de servicio",
    "pct_anclajes_fuera": "% fuera de servicio",
    "estaciones": "Estaciones",
    "no_alquilan": "No alquilan",
    "sin_reportar": "Sin snapshot reciente",
    "operador_viejo": "Operador viejo",
})
st.dataframe(tabla, use_container_width=True, hide_index=True)

st.caption(
    f"La capacidad usa estaciones que reportaron en los últimos {UMBRAL_SNAPSHOT_MINUTOS} "
    "minutos y cuyo dato del operador no tiene más de 60 minutos. Bicis para retirar y "
    "anclajes para devolver son medidas independientes: no se suman."
)
