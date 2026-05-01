"""
Silver - Data Quality & Pipeline Health.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from db import (
    load_table, get_row_count, get_table_list,
    show_last_updated_badge, get_last_updated,
)

st.header("Silver Layer — Data Quality")
show_last_updated_badge("silver", "crypto_markets")

# --- Verificar que hay datos ---
tables = get_table_list("silver")
if not tables:
    st.warning("No hay tablas en silver todavia. Ejecuta el pipeline Silver desde Airflow.")
    st.stop()

# =============================================================
# PIPELINE FLOW: Bronze → Silver → Gold (conteo de filas)
# =============================================================
st.subheader("Pipeline Medallion")

bronze_count = get_row_count("bronze", "crypto_markets")
silver_count = get_row_count("silver", "crypto_markets")
quarantine_count = get_row_count("silver", "quarantine_crypto_markets")
gold_count = get_row_count("gold", "fact_crypto_markets")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Bronze (raw)", f"{bronze_count:,}")
col2.metric("Silver (clean)", f"{silver_count:,}")
col3.metric("Quarantine", f"{quarantine_count:,}")
col4.metric("Gold (facts)", f"{gold_count:,}")

# Barra de progreso visual
if bronze_count > 0:
    pass_rate = silver_count / bronze_count * 100
    reject_rate = quarantine_count / bronze_count * 100
    dedup_rate = 100 - pass_rate - reject_rate

    fig_funnel = go.Figure(go.Funnel(
        y=["Bronze (ingesta)", "Silver (validado)", "Gold (modelado)"],
        x=[bronze_count, silver_count, gold_count],
        textinfo="value+percent initial",
        marker=dict(color=["#636EFA", "#00CC96", "#FFA15A"]),
    ))
    fig_funnel.update_layout(height=250, margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(fig_funnel, use_container_width=True)

st.divider()

# =============================================================
# DATA QUALITY METRICS
# =============================================================
st.subheader("Calidad de datos")

col_a, col_b, col_c = st.columns(3)

with col_a:
    if bronze_count > 0:
        st.metric("Tasa de aprobacion", f"{silver_count / bronze_count * 100:.1f}%")
    else:
        st.metric("Tasa de aprobacion", "—")

with col_b:
    if bronze_count > 0:
        st.metric("Tasa de rechazo", f"{quarantine_count / bronze_count * 100:.1f}%")
    else:
        st.metric("Tasa de rechazo", "—")

with col_c:
    # Deduplicados = bronze - silver - quarantine
    if bronze_count > 0:
        dedup = bronze_count - silver_count - quarantine_count
        st.metric("Duplicados eliminados", f"{max(dedup, 0):,}")
    else:
        st.metric("Duplicados eliminados", "—")

# --- Global market ---
bronze_global = get_row_count("bronze", "global_market")
silver_global = get_row_count("silver", "global_market")

if bronze_global > 0 or silver_global > 0:
    st.caption(f"Global market: {bronze_global:,} bronze → {silver_global:,} silver")

st.divider()

# =============================================================
# COLUMNAS DERIVADAS EN SILVER
# =============================================================
st.subheader("Columnas derivadas")
st.caption("Silver agrega 6 columnas que no existen en Bronze")

df = load_table("silver", "crypto_markets")

if not df.empty:
    derived = {
        "spread_pct": "Spread entre max y min del dia (%)",
        "ath_distance_pct": "Distancia al All-Time High (%)",
        "atl_distance_pct": "Distancia al All-Time Low (%)",
        "supply_ratio": "Ratio circulante / total supply",
        "fdv_ratio": "Market cap / Fully diluted valuation",
        "spread_24h": "Diferencia absoluta high - low 24h",
    }

    available = {k: v for k, v in derived.items() if k in df.columns}

    if available:
        col_left, col_right = st.columns([1, 2])

        with col_left:
            for col_name, desc in available.items():
                non_null = df[col_name].notna().sum()
                total = len(df)
                st.markdown(f"**`{col_name}`**")
                st.caption(f"{desc} — {non_null}/{total} valores")

        with col_right:
            selected_col = st.selectbox("Visualizar columna", list(available.keys()))
            if "id" in df.columns:
                chart_df = (
                    df[["id", selected_col]]
                    .dropna()
                    .sort_values(selected_col, ascending=False)
                    .head(15)
                )
                fig = px.bar(
                    chart_df, x="id", y=selected_col,
                    color=selected_col, color_continuous_scale="Tealgrn",
                    labels={selected_col: available[selected_col], "id": ""},
                )
                fig.update_layout(height=350, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

st.divider()

# =============================================================
# QUARANTINE
# =============================================================
st.subheader("Quarantine")

qdf = load_table("silver", "quarantine_crypto_markets")

if qdf.empty or quarantine_count == 0:
    st.success("Sin registros en quarantine — todos los datos pasaron validacion.")
else:
    st.error(f"{quarantine_count} registros rechazados")
    st.dataframe(qdf.head(50), use_container_width=True, hide_index=True)
