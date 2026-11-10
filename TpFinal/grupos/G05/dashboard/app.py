import streamlit as st

from db import run_query

st.set_page_config(
    page_title="Sismos USGS · G05",
    page_icon="🌎",
    layout="wide",
)

st.title("🌎 Sismos USGS · Grupo 5")
st.markdown(
    "Exploración de los eventos sísmicos informados por USGS en los últimos "
    "30 días. El flag de tsunami refleja el dato publicado por USGS; no es "
    "una alerta ni una predicción."
)

try:
    resumen = run_query("""
        SELECT
            (SELECT COUNT(*) FROM gold.fact_sismo) AS eventos,
            (SELECT COUNT(DISTINCT fecha) FROM gold.fact_sismo) AS dias,
            (SELECT COUNT(DISTINCT zona_id) FROM gold.fact_sismo) AS zonas,
            (SELECT COUNT(*) FROM gold.v_sismos_tsunami) AS tsunami_usgs,
            (SELECT MAX(fecha_evento) FROM gold.fact_sismo) AS ultimo_evento
    """)
except Exception as exc:
    st.error(f"No se pudieron consultar las vistas Gold: {exc}")
    st.stop()

if resumen.empty or int(resumen.iloc[0]["eventos"]) == 0:
    st.info("Gold todavía no tiene datos. Esperá a que termine el DAG 03_gold_sismos.")
    st.stop()

r = resumen.iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Sismos analizados", f"{int(r['eventos']):,}")
c2.metric("Días con actividad", int(r["dias"]))
c3.metric("Zonas reportadas", int(r["zonas"]))
c4.metric("Marcados por USGS con tsunami", int(r["tsunami_usgs"]))

st.caption(f"Último evento: {r['ultimo_evento']} · Elegí una página en el menú lateral.")
st.info(
    "La zona se deriva del texto `place` publicado por USGS y es aproximada; "
    "no representa una división geográfica normalizada."
)
