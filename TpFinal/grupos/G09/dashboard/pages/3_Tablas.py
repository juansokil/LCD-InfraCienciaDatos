import streamlit as st

from data import require_gold
from db import run_query, table_exists

st.set_page_config(page_title="Tablas - USGS Earthquakes", layout="wide")
st.title("Tablas operativas")
st.caption("Eventos a priorizar y evolucion diaria por region.")

summary, events = require_gold()

total_events = int(summary["events_count"].sum()) if not summary.empty else 0
avg_latency = float(summary["avg_ingestion_latency_minutes"].mean()) if not summary.empty else 0.0

k1, k2 = st.columns(2)
k1.metric("Eventos totales", total_events)
k2.metric("Latencia prom. ingesta", f"{avg_latency:.0f} min")

st.divider()
st.subheader("Que eventos priorizar?")
st.caption("Eventos fuertes/mayores, con tsunami, con alerta o significancia >= 500.")
if not events.empty:
    priority = events[
        events["severity_class"].isin(["fuerte", "mayor"])
        | (events["tsunami"] == 1)
        | events["alert"].notna()
        | (events["sig"].fillna(0) >= 500)
    ].sort_values("sig", ascending=False, na_position="last")

    cols_show = [c for c in [
        "event_time", "place", "mag", "depth_km",
        "severity_class", "alert", "tsunami", "sig", "cdi", "mmi",
    ] if c in priority.columns]
    st.dataframe(priority[cols_show], use_container_width=True, hide_index=True, height=420)

st.divider()

if table_exists("gold", "fact_region_daily"):
    daily_cols = set(run_query("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'gold'
          AND table_name = 'fact_region_daily'
    """)["column_name"])
    if "region" in daily_cols:
        daily = run_query("""
            SELECT
                region,
                event_date,
                events_count,
                max_mag,
                avg_depth_km,
                severe_events
            FROM gold.fact_region_daily
            ORDER BY event_date DESC, events_count DESC
        """)
    else:
        daily = run_query("""
            SELECT
                d.region,
                f.event_date,
                f.events_count,
                f.max_mag,
                f.avg_depth_km,
                f.severe_events
            FROM gold.fact_region_daily f
            LEFT JOIN gold.dim_region d ON f.region_id = d.region_id
            ORDER BY f.event_date DESC, f.events_count DESC
        """)
    if not daily.empty:
        st.subheader("Eventos diarios por region")
        st.dataframe(daily, use_container_width=True, hide_index=True, height=420)
