"""
Resumen del Mercado - Vista ejecutiva con KPIs y Top 10.
Objetivo: responder "como esta el mercado crypto hoy?"
"""

import streamlit as st
import plotly.express as px
from db import load_table, show_last_updated_badge

st.header("Gold - Resumen del Mercado")
show_last_updated_badge("gold", "fact_crypto_markets", col="_processed_at")

# --- Cargar datos ---
fact = load_table("gold", "fact_crypto_markets")
dim = load_table("gold", "dim_crypto")
fact_global = load_table("gold", "fact_global_market")

if fact.empty:
    st.warning("No hay datos en gold todavia. Ejecuta el pipeline desde Airflow.")
    st.stop()

df = fact.copy()
if not dim.empty and "crypto_id" in dim.columns:
    df = df.merge(dim[["crypto_id", "name", "symbol"]], on="crypto_id", how="left")

# =============================================================
# KPIs GLOBALES
# =============================================================
col1, col2, col3, col4 = st.columns(4)

total_market_cap = df["market_cap"].sum() if "market_cap" in df.columns else 0
total_volume = df["total_volume"].sum() if "total_volume" in df.columns else 0
n_cryptos = df["crypto_id"].nunique() if "crypto_id" in df.columns else 0

col1.metric("Market Cap Total", f"${total_market_cap / 1e9:,.1f}B")
col2.metric("Volumen 24h", f"${total_volume / 1e9:,.1f}B")
col3.metric("Criptomonedas", n_cryptos)

if not fact_global.empty and "btc_dominance" in fact_global.columns:
    col4.metric("BTC Dominancia", f"{fact_global['btc_dominance'].iloc[-1]:.1f}%")
else:
    avg_change = df["price_change_percentage_24h"].mean() if "price_change_percentage_24h" in df.columns else 0
    col4.metric("Cambio Prom. 24h", f"{avg_change:+.2f}%")

# --- Global extra ---
if not fact_global.empty:
    gcol1, gcol2, gcol3 = st.columns(3)
    if "total_market_cap_usd" in fact_global.columns:
        gcol1.metric("Market Cap Global", f"${fact_global['total_market_cap_usd'].iloc[-1] / 1e12:,.2f}T")
    if "total_volume_usd" in fact_global.columns:
        gcol2.metric("Volumen Global", f"${fact_global['total_volume_usd'].iloc[-1] / 1e9:,.1f}B")
    if "active_cryptocurrencies" in fact_global.columns:
        gcol3.metric("Cryptos Activas", f"{fact_global['active_cryptocurrencies'].iloc[-1]:,.0f}")

st.divider()

# =============================================================
# TOP 10 POR MARKET CAP
# =============================================================
st.subheader("Top 10 por Market Cap")

if "name" in df.columns:
    top10 = (
        df.sort_values("market_cap", ascending=False)
        .drop_duplicates(subset="crypto_id")
        .head(10)
    )

    col_left, col_right = st.columns(2)

    with col_left:
        fig_bar = px.bar(
            top10, x="name", y="market_cap",
            color="current_price", color_continuous_scale="Viridis",
            labels={"market_cap": "Market Cap (USD)", "name": "", "current_price": "Precio"},
        )
        fig_bar.update_layout(height=400, xaxis_tickangle=-45)
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_right:
        fig_pie = px.pie(top10, values="market_cap", names="name", hole=0.4)
        fig_pie.update_layout(height=400)
        st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# =============================================================
# GANADORES Y PERDEDORES 24H
# =============================================================
if "price_change_percentage_24h" in df.columns and "name" in df.columns:
    st.subheader("Movimiento 24h")

    unique_df = df.drop_duplicates(subset="crypto_id").dropna(subset=["price_change_percentage_24h"])

    col_win, col_lose = st.columns(2)

    with col_win:
        winners = unique_df.nlargest(5, "price_change_percentage_24h")
        fig_w = px.bar(
            winners, x="name", y="price_change_percentage_24h",
            color_discrete_sequence=["#00CC96"],
            labels={"price_change_percentage_24h": "Cambio %", "name": ""},
        )
        fig_w.update_layout(height=300, title="Top 5 Ganadores")
        st.plotly_chart(fig_w, use_container_width=True)

    with col_lose:
        losers = unique_df.nsmallest(5, "price_change_percentage_24h")
        fig_l = px.bar(
            losers, x="name", y="price_change_percentage_24h",
            color_discrete_sequence=["#EF553B"],
            labels={"price_change_percentage_24h": "Cambio %", "name": ""},
        )
        fig_l.update_layout(height=300, title="Top 5 Perdedores")
        st.plotly_chart(fig_l, use_container_width=True)
