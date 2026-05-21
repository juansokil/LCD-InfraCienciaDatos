"""
Dominancia - Participacion de mercado y concentracion.
Objetivo: responder "quien domina el mercado? esta concentrado o distribuido?"
"""

import streamlit as st
import plotly.express as px
from db import load_table, show_last_updated_badge

st.header("Gold - Dominancia de Mercado")
show_last_updated_badge("gold", "gold_abt_crypto", col="_processed_at")

# --- Cargar datos ---
abt = load_table("gold", "gold_abt_crypto")
fact_global = load_table("gold", "fact_global_market")

if abt.empty:
    st.warning("No hay datos ABT en gold todavia. Ejecuta el pipeline desde Airflow.")
    st.stop()

# =============================================================
# BTC / ETH DOMINANCIA
# =============================================================
if not fact_global.empty:
    st.subheader("Dominancia global")

    col1, col2, col3 = st.columns(3)

    btc_dom = fact_global.get("btc_dominance", [None]).iloc[-1] if "btc_dominance" in fact_global.columns else None
    eth_dom = fact_global.get("eth_dominance", [None]).iloc[-1] if "eth_dominance" in fact_global.columns else None

    if btc_dom is not None:
        col1.metric("Bitcoin", f"{btc_dom:.1f}%")
    if eth_dom is not None:
        col2.metric("Ethereum", f"{eth_dom:.1f}%")
    if btc_dom is not None and eth_dom is not None:
        col3.metric("Altcoins", f"{100 - btc_dom - eth_dom:.1f}%")

        # Donut de dominancia
        dom_data = [
            {"Segmento": "Bitcoin", "Dominancia": btc_dom},
            {"Segmento": "Ethereum", "Dominancia": eth_dom},
            {"Segmento": "Altcoins", "Dominancia": 100 - btc_dom - eth_dom},
        ]
        fig_dom = px.pie(
            dom_data, values="Dominancia", names="Segmento", hole=0.5,
            color="Segmento",
            color_discrete_map={"Bitcoin": "#F7931A", "Ethereum": "#627EEA", "Altcoins": "#00CC96"},
        )
        fig_dom.update_layout(height=350)
        st.plotly_chart(fig_dom, use_container_width=True)

    st.divider()

# =============================================================
# MARKET SHARE POR CRIPTO
# =============================================================
if "market_dominance" in abt.columns and "id" in abt.columns:
    st.subheader("Participacion de mercado individual")
    st.caption("Porcentaje del market cap total que representa cada cripto")

    share_df = (
        abt[["id", "market_dominance", "market_cap"]]
        .dropna()
        .sort_values("market_dominance", ascending=False)
    )

    # Top 10 + "Otros"
    top = share_df.head(10).copy()
    rest = share_df.iloc[10:]
    if not rest.empty:
        import pandas as pd
        otros = pd.DataFrame([{
            "id": f"Otros ({len(rest)})",
            "market_dominance": rest["market_dominance"].sum(),
            "market_cap": rest["market_cap"].sum(),
        }])
        top = pd.concat([top, otros], ignore_index=True)

    fig_share = px.bar(
        top, x="id", y="market_dominance",
        color="market_dominance", color_continuous_scale="Blues",
        labels={"market_dominance": "Dominancia %", "id": ""},
    )
    fig_share.update_layout(height=400, xaxis_tickangle=-45)
    st.plotly_chart(fig_share, use_container_width=True)

    st.divider()

# =============================================================
# CONCENTRACION: TOP 10 vs RESTO
# =============================================================
if "market_cap_tier" in abt.columns and "market_cap" in abt.columns:
    st.subheader("Concentracion del mercado")
    st.caption("Que porcentaje del valor total concentran las Top 10, Top 25 y el resto")

    tier_summary = (
        abt.groupby("market_cap_tier")["market_cap"]
        .sum()
        .reset_index()
    )
    tier_summary.columns = ["Tier", "Market Cap"]
    tier_summary["Porcentaje"] = (tier_summary["Market Cap"] / tier_summary["Market Cap"].sum() * 100).round(2)

    col_left, col_right = st.columns(2)

    with col_left:
        fig_conc = px.pie(
            tier_summary, values="Market Cap", names="Tier", hole=0.4,
            color="Tier",
            color_discrete_map={"top_10": "#636EFA", "top_25": "#AB63FA", "rest": "#B6E880"},
        )
        fig_conc.update_layout(height=350)
        st.plotly_chart(fig_conc, use_container_width=True)

    with col_right:
        for _, row in tier_summary.iterrows():
            st.metric(row["Tier"], f"{row['Porcentaje']:.1f}%", f"${row['Market Cap'] / 1e9:,.1f}B")

# =============================================================
# PRICE TIERS
# =============================================================
if "price_tier" in abt.columns:
    st.divider()
    st.subheader("Distribucion por rango de precio")
    st.caption("micro (<$1), small ($1-100), medium ($100-10K), large (>$10K)")

    tier_data = abt["price_tier"].value_counts().reset_index()
    tier_data.columns = ["Tier", "Cantidad"]

    fig_pt = px.bar(
        tier_data, x="Tier", y="Cantidad", color="Tier",
        color_discrete_map={"micro": "#B6E880", "small": "#FFA15A", "medium": "#636EFA", "large": "#EF553B"},
    )
    fig_pt.update_layout(height=300, showlegend=False)
    st.plotly_chart(fig_pt, use_container_width=True)
