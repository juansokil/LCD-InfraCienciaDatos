import plotly.express as px
import streamlit as st

from comun import formato_entero, selector_red, selector_tipo_dia, tasa
from db import requiere_gold, run_query

st.title("Uso estimado por estación")
st.caption(
    "Retiros y devoluciones estimados con la diferencia de bicicletas entre snapshots "
    "consecutivos (≤ 10 min). Son un **mínimo**: si en 5 minutos sale una bici y entra "
    "otra, no se ve. Los cambios de 5 o más bicis de golpe se toman como reposición "
    "del operador y se muestran aparte."
)
requiere_gold()

red, red_nombre, _ = selector_red("red_uso_estaciones")
tipos_dia = selector_tipo_dia("tipo_dia_uso_estaciones")
filtro = {"red": red, "tipos": tipos_dia}

# Normalizacion por TIEMPO observado, no por dias calendario: un par de
# snapshots validos cubre 5 minutos de una estacion, asi que 12 pares = una
# hora-estacion observada. Un dia con 1 hora de datos no cuenta como dia entero.
PARES_POR_HORA = 12

por_hora = run_query("""
    SELECT
        f.hora,
        sum(f.pares_comparados)       AS pares,
        sum(f.retiros_estimados)      AS retiros,
        sum(f.devoluciones_estimadas) AS devoluciones,
        sum(f.rebalanceo_bicis)       AS rebalanceo
    FROM gold.fact_estacion_hora f
    JOIN gold.dim_fecha df USING (fecha)
    WHERE f.network_id = :red
      AND df.tipo_dia = ANY(CAST(:tipos AS text[]))
    GROUP BY f.hora
""", filtro)
estaciones = run_query("""
    SELECT count(DISTINCT f.station_id) AS n
    FROM gold.fact_estacion_hora f
    JOIN gold.dim_fecha df USING (fecha)
    WHERE f.network_id = :red
      AND df.tipo_dia = ANY(CAST(:tipos AS text[]))
      AND f.pares_comparados > 0
""", filtro)["n"].iloc[0]
if por_hora.empty or por_hora["pares"].sum() == 0:
    st.info("Todavía no hay pares de snapshots consecutivos para esta red y selección de días.")
    st.stop()

# Tasa por hora-estacion observada x estaciones de la red = estimacion de la
# red entera, como si todas hubieran estado observadas todo el tiempo.
horas_estacion = por_hora["pares"] / PARES_POR_HORA
for col in ["retiros", "devoluciones", "rebalanceo"]:
    por_hora[f"{col}_red"] = tasa(por_hora[col], horas_estacion) / 100 * estaciones

# Dia = suma de las horas del reloj con datos. No se extrapola la tasa a 24 h:
# el uso de la madrugada no es el de la tarde.
horas_observadas = por_hora["pares"].sum() / PARES_POR_HORA
horas_reloj = int((por_hora["pares"] > 0).sum())
por_dia = {
    col: por_hora[f"{col}_red"].sum()
    for col in ["retiros", "devoluciones", "rebalanceo"]
}

c1, c2, c3, c4 = st.columns(4)
sufijo = "" if horas_reloj == 24 else f" ({horas_reloj} h)"
c1.metric(f"Retiros por día{sufijo}", formato_entero(round(por_dia["retiros"])))
c2.metric(f"Devoluciones por día{sufijo}", formato_entero(round(por_dia["devoluciones"])))
c3.metric(f"Movidas por el operador{sufijo}", formato_entero(round(por_dia["rebalanceo"])))
c4.metric("Horas-estación observadas", formato_entero(round(horas_observadas)))
st.caption(
    f"Estimación para las {estaciones} estaciones de la red: tasa por hora-estación "
    "observada de cada hora del día × estaciones, sumada sobre las horas con datos"
    + ("." if horas_reloj == 24 else
       f". Solo hay datos de {horas_reloj} de las 24 horas, así que el día está incompleto.")
)

# Perfil horario.
por_hora = (
    por_hora.set_index("hora").reindex(range(24)).rename_axis("hora").reset_index()
)
por_hora_largo = por_hora.melt(
    id_vars="hora", value_vars=["retiros_red", "devoluciones_red"],
    var_name="movimiento", value_name="bicicletas",
)
por_hora_largo["movimiento"] = por_hora_largo["movimiento"].map(
    {"retiros_red": "Retiros", "devoluciones_red": "Devoluciones"}
)
fig_horario = px.line(
    por_hora_largo,
    x="hora",
    y="bicicletas",
    color="movimiento",
    markers=True,
    color_discrete_map={"Retiros": "#d62828", "Devoluciones": "#277da1"},
    labels={
        "hora": "Hora local",
        "bicicletas": "Bicicletas en esa hora (estimación red)",
        "movimiento": "",
    },
)
fig_horario.update_xaxes(tickmode="linear", dtick=1)
st.subheader("¿En qué horario se usa la red?")
st.plotly_chart(fig_horario, use_container_width=True)

# Por estacion: uso por dia observado + porcentaje de tiempo sin bicis.
por_estacion = run_query("""
    SELECT
        f.station_id,
        COALESCE(d.station_name, f.station_id) AS station_name,
        d.zona,
        sum(f.pares_comparados)       AS pares,
        sum(f.retiros_estimados)      AS retiros,
        sum(f.devoluciones_estimadas) AS devoluciones,
        sum(f.rebalanceo_bicis)       AS rebalanceo,
        sum(f.snapshots_validos)      AS snapshots_observados,
        sum(f.snapshots_sin_bicis)    AS snapshots_sin_bicis
    FROM gold.fact_estacion_hora f
    JOIN gold.dim_estacion d USING (network_id, station_id)
    JOIN gold.dim_fecha df USING (fecha)
    WHERE f.network_id = :red
      AND df.tipo_dia = ANY(CAST(:tipos AS text[]))
    GROUP BY f.station_id, d.station_name, d.zona
""", filtro)
# Tasa por hora observada (comparable entre estaciones aunque se hayan
# observado distinto tiempo). Minimo una hora, para que un par suelto no
# aparezca con un uso enorme.
por_estacion = por_estacion[por_estacion["pares"] >= PARES_POR_HORA].copy()
horas_obs = por_estacion["pares"] / PARES_POR_HORA
por_estacion["retiros_por_hora"] = por_estacion["retiros"] / horas_obs
por_estacion["devoluciones_por_hora"] = por_estacion["devoluciones"] / horas_obs
por_estacion["uso_por_hora"] = por_estacion["retiros_por_hora"] + por_estacion["devoluciones_por_hora"]
por_estacion["pct_sin_bicis"] = tasa(
    por_estacion["snapshots_sin_bicis"], por_estacion["snapshots_observados"]
)

top = por_estacion.nlargest(15, "uso_por_hora")
top_largo = top.melt(
    id_vars=["station_id", "station_name", "uso_por_hora"],
    value_vars=["retiros_por_hora", "devoluciones_por_hora"],
    var_name="movimiento",
    value_name="bicicletas",
)
top_largo["movimiento"] = top_largo["movimiento"].map(
    {"retiros_por_hora": "Retiros", "devoluciones_por_hora": "Devoluciones"}
)
fig_estaciones = px.bar(
    top_largo,
    x="bicicletas",
    y="station_name",
    color="movimiento",
    barmode="stack",
    orientation="h",
    hover_data=["station_id"],
    color_discrete_map={"Retiros": "#d62828", "Devoluciones": "#277da1"},
    labels={"bicicletas": "Bicicletas por hora observada", "station_name": "Estación", "movimiento": ""},
)
fig_estaciones.update_yaxes(
    categoryorder="array",
    categoryarray=top.sort_values("uso_por_hora")["station_name"].tolist(),
)
fig_estaciones.update_layout(height=max(450, 32 * len(top)))
st.subheader("Estaciones con más uso")
st.plotly_chart(fig_estaciones, use_container_width=True)

# Cruce uso x saturacion: separa "vacia porque se usa mucho" de "vacia porque
# nadie la repone".
uso_mediano = por_estacion["uso_por_hora"].median()
sat_mediana = por_estacion["pct_sin_bicis"].median()


def cuadrante(fila):
    if fila["pct_sin_bicis"] > sat_mediana:
        return ("Vacía por mucho uso" if fila["uso_por_hora"] > uso_mediano
                else "Vacía con poco uso (¿falta reposición?)")
    return "Mucho uso, bien abastecida" if fila["uso_por_hora"] > uso_mediano else "Poco uso"


por_estacion["perfil"] = por_estacion.apply(cuadrante, axis=1)
fig_cruce = px.scatter(
    por_estacion,
    x="uso_por_hora",
    y="pct_sin_bicis",
    color="perfil",
    hover_data=["station_name", "zona", "rebalanceo"],
    labels={
        "uso_por_hora": "Retiros + devoluciones por hora observada",
        "pct_sin_bicis": "Tiempo sin bicis (%)",
        "perfil": "",
        "station_name": "Estación",
        "zona": "Zona",
        "rebalanceo": "Bicis movidas por el operador",
    },
    color_discrete_map={
        "Vacía por mucho uso": "#f4a261",
        "Vacía con poco uso (¿falta reposición?)": "#d62828",
        "Mucho uso, bien abastecida": "#2a9d8f",
        "Poco uso": "#8d99ae",
    },
)
fig_cruce.add_vline(x=uso_mediano, line_dash="dot", line_color="#8d99ae")
fig_cruce.add_hline(y=sat_mediana, line_dash="dot", line_color="#8d99ae")
st.subheader("¿Vacía porque se usa mucho o porque nadie la repone?")
st.plotly_chart(fig_cruce, use_container_width=True)

st.dataframe(
    por_estacion[por_estacion["perfil"] == "Vacía con poco uso (¿falta reposición?)"]
    .sort_values("pct_sin_bicis", ascending=False)[
        ["station_name", "zona", "pct_sin_bicis", "uso_por_hora", "rebalanceo"]
    ].rename(columns={
        "station_name": "Estación",
        "zona": "Zona",
        "pct_sin_bicis": "Tiempo sin bicis (%)",
        "uso_por_hora": "Uso por hora observada",
        "rebalanceo": "Bicis movidas por el operador",
    }),
    use_container_width=True,
    hide_index=True,
)
st.caption(
    "Uso por hora observada = cambios / tiempo observado de la estación (pares de "
    "snapshots × 5 min). Las líneas punteadas son las medianas de la red. Cada cambio se asigna a la hora "
    "local del snapshot más reciente del par. El umbral de 5 bicis para separar "
    "reposiciones es una heurística: un pico real de 5 devoluciones en 5 minutos se "
    "contaría como operador."
)
