import streamlit as st

from db import load_table, table_exists


def require_gold():
    if not table_exists("gold", "earthquake_risk_summary"):
        st.info("Todavia no existe la capa Gold. Ejecuta los DAGs Bronze, Silver y Gold.")
        st.stop()
    summary = load_table("gold", "earthquake_risk_summary")
    events = load_table("gold", "fact_earthquake_events")
    return summary, events
