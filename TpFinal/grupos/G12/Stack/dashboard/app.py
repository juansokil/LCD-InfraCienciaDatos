"""
Portada del dashboard del G12: sismos del mundo segun la API de USGS.

Lee solo la capa Gold (gold.fact_sismos_diarios + gold.dim_region, en
estrella, y gold.agg_ranking_zonas). Las paginas de la barra lateral
profundizan cada pregunta.
"""

import streamlit as st

from db import JOULES_POR_TON_TNT, boton_actualizar, exigir_gold, run_query

st.set_page_config(page_title="G12 · Sismos USGS", page_icon="🌎", layout="wide")
boton_actualizar()

st.title("🌎 Sismos en el mundo · Capa Gold")
st.markdown(
    "Pipeline del **Grupo 12** sobre la API de "
    "[USGS Earthquakes](https://earthquake.usgs.gov/fdsnws/event/1/). "
    "Cada hora, Airflow baja los sismos de magnitud 2.5 o más (**Bronze**), "
    "los limpia y deduplica (**Silver**) y los agrega por día y región (**Gold**). "
    "Este tablero lee únicamente Gold."
)

exigir_gold()

# --- KPIs generales -----------------------------------------------------------
kpis = run_query(
    """
    SELECT SUM(cantidad_sismos)                 AS sismos,
           MAX(magnitud_maxima)                 AS mag_max,
           SUM(energia_total_joules)            AS energia,
           SUM(alertas_tsunami)                 AS tsunamis,
           COUNT(DISTINCT region_id)            AS regiones,
           MIN(event_date)                      AS desde,
           MAX(event_date)                      AS hasta
    FROM gold.fact_sismos_diarios
    """
).iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Sismos registrados", f"{int(kpis['sismos']):,}".replace(",", "."))
c2.metric("Magnitud máxima", f"{kpis['mag_max']:.1f}")
c3.metric("Regiones con actividad", int(kpis["regiones"]))
c4.metric("Alertas de tsunami", int(kpis["tsunamis"] or 0))
c5.metric(
    "Energía liberada",
    f"{kpis['energia'] / JOULES_POR_TON_TNT:,.0f} t TNT".replace(",", "."),
    help="Energía estimada con log10(E) = 4.8 + 1.5·M (Gutenberg-Richter), "
    "expresada en toneladas de TNT equivalentes.",
)
st.caption(f"Período cubierto: {kpis['desde']:%d/%m/%Y} al {kpis['hasta']:%d/%m/%Y}.")

# --- Lo más fuerte ------------------------------------------------------------
st.subheader("Los días y lugares más fuertes")
top = run_query(
    """
    SELECT f.event_date AS fecha, r.region, f.cantidad_sismos, f.magnitud_maxima,
           f.alertas_tsunami
    FROM gold.fact_sismos_diarios f
    JOIN gold.dim_region r USING (region_id)
    ORDER BY f.magnitud_maxima DESC NULLS LAST, f.cantidad_sismos DESC
    LIMIT 10
    """
)
st.dataframe(
    top,
    hide_index=True,
    use_container_width=True,
    column_config={
        "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
        "region": "Región",
        "cantidad_sismos": "Sismos ese día",
        "magnitud_maxima": st.column_config.NumberColumn("Magnitud máx.", format="%.1f"),
        "alertas_tsunami": "Alertas de tsunami",
    },
)

# --- El modelo ----------------------------------------------------------------
with st.expander("¿De dónde salen estos números? (modelo Gold)"):
    st.markdown(
        """
- **`gold.fact_sismos_diarios`**: un registro por *día × región* con cantidad de
  sismos, magnitud promedio y máxima, energía total y alertas de tsunami.
- **`gold.dim_region`**: la dimensión de regiones (`region_id`, `region`).
  Con la fact forma un **modelo estrella**.
- **`gold.agg_ranking_zonas`**: agregado por región sobre todo el período
  (total de sismos, magnitudes, profundidad promedio).

Las tres tablas las arma `scripts/transform_gold.py` con SQL a partir de
`silver.earthquakes`.
        """
    )

st.markdown(
    "👈 En la barra lateral: **Evolución diaria** (cómo cambia la actividad día a día) "
    "y **Ranking de zonas** (dónde tiembla más y más fuerte)."
)
