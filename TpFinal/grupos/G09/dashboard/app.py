import streamlit as st

from db import load_table

st.set_page_config(
    page_title="G09 - USGS Earthquakes",
    layout="wide",
)

st.title("G09 - USGS Earthquakes")
st.caption("Pipeline Bronze → Silver → Gold sobre datos sismicos de la USGS")

summary = load_table("gold", "earthquake_risk_summary")

if summary.empty:
    st.info("Todavia no hay datos Gold. Ejecuta los DAGs Bronze, Silver y Gold desde Airflow.")
else:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Regiones con eventos", len(summary))
    k2.metric("Eventos totales", int(summary["events_count"].sum()))
    k3.metric("Magnitud maxima", f"{float(summary['max_mag'].max()):.1f}")
    k4.metric("Eventos fuertes / mayores", int(summary["severe_events"].sum()))

    st.divider()
    st.subheader("Ranking de riesgo por region")
    st.dataframe(summary, use_container_width=True)
