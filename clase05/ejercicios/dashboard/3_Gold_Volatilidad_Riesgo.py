"""
Volatilidad y Riesgo - Analisis de spread, categorias y dispersion.
Objetivo: responder "cuales son las criptos mas volatiles? donde esta el riesgo?"
"""

import streamlit as st
import plotly.express as px
from db import load_table, show_last_updated_badge

st.header("Gold - Volatilidad y Riesgo")
show_last_updated_badge("gold", "gold_abt_crypto", col="_processed_at")

# --- Cargar datos ---
abt = load_table("gold", "gold_abt_crypto")
fact = load_table("gold", "fact_crypto_markets")
dim = load_table("gold", "dim_crypto")

if abt.empty and fact.empty:
    st.warning("No hay datos en gold todavia. Ejecuta el pipeline desde Airflow.")
    st.stop()

# =============================================================
# DISTRIBUCION DE VOLATILIDAD
# =============================================================
if not abt.empty and "volatility_category" in abt.columns:
    st.subheader("Distribucion por volatilidad")

    col_a, col_b = st.columns(2)

    with col_a:
        vol_counts = abt["volatility_category"].value_counts().reset_index()
        vol_counts.columns = ["categoria", "cantidad"]
        fig_vol = px.pie(
            vol_counts, values="cantidad", names="categoria",
            hole=0.4, color="categoria",
            color_discrete_map={"baja": "#00CC96", "media": "#FFA15A", "alta": "#EF553B"},
        )
        fig_vol.update_layout(height=350, title="Volatilidad 24h")
        st.plotly_chart(fig_vol, use_container_width=True)

    with col_b:
        if "market_cap_tier" in abt.columns:
            tier_counts = abt["market_cap_tier"].value_counts().reset_index()
            tier_counts.columns = ["tier", "cantidad"]
            fig_tier = px.pie(
                tier_counts, values="cantidad", names="tier",
                hole=0.4, color="tier",
                color_discrete_map={"top_10": "#636EFA", "top_25": "#AB63FA", "rest": "#B6E880"},
            )
            fig_tier.update_layout(height=350, title="Tiers por Market Cap")
            st.plotly_chart(fig_tier, use_container_width=True)

    st.divider()

# =============================================================
# SPREAD 24H
# =============================================================
df = fact.copy()
if not dim.empty and "crypto_id" in dim.columns:
    df = df.merge(dim[["crypto_id", "name", "symbol"]], on="crypto_id", how="left")

if "spread_pct" in df.columns and "name" in df.columns:
    st.subheader("Spread 24h — Top 15")
    st.caption("Diferencia porcentual entre max y min del dia. Mayor spread = mayor volatilidad intradiaria.")

    spread_data = (
        df[["name", "spread_pct"]]
        .drop_duplicates(subset="name")
        .dropna()
        .sort_values("spread_pct", ascending=False)
        .head(15)
    )

    fig_spread = px.bar(
        spread_data, x="name", y="spread_pct",
        color="spread_pct", color_continuous_scale="YlOrRd",
        labels={"spread_pct": "Spread %", "name": ""},
    )
    fig_spread.update_layout(height=400, xaxis_tickangle=-45)
    st.plotly_chart(fig_spread, use_container_width=True)

    st.divider()

# =============================================================
# SCATTER: PRECIO VS VOLUMEN (bubble = market cap)
# =============================================================
if not abt.empty and "current_price" in abt.columns and "total_volume" in abt.columns:
    st.subheader("Mapa de riesgo: Precio vs Volumen")
    st.caption("Tamano = market cap, Color = volatilidad. Criptos en esquina inferior izq = bajo riesgo.")

    hover = "id" if "id" in abt.columns else None
    color = "volatility_category" if "volatility_category" in abt.columns else None

    fig_scatter = px.scatter(
        abt, x="total_volume", y="current_price",
        size="market_cap", color=color, hover_name=hover,
        log_x=True, log_y=True,
        color_discrete_map={"baja": "#00CC96", "media": "#FFA15A", "alta": "#EF553B"},
        labels={"total_volume": "Volumen 24h (log)", "current_price": "Precio (log)"},
    )
    fig_scatter.update_layout(height=500)
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.divider()

# =============================================================
# DISTANCIA A ATH / ATL
# =============================================================
if not abt.empty and "ath_distance_pct" in abt.columns and "id" in abt.columns:
    st.subheader("Distancia al All-Time High")
    st.caption("Que tan lejos esta cada crypto de su maximo historico. Valores negativos = por debajo del ATH.")

    ath_data = (
        abt[["id", "ath_distance_pct"]]
        .dropna()
        .sort_values("ath_distance_pct", ascending=True)
        .head(20)
    )

    fig_ath = px.bar(
        ath_data, x="id", y="ath_distance_pct",
        color="ath_distance_pct", color_continuous_scale="RdYlGn",
        labels={"ath_distance_pct": "Distancia al ATH (%)", "id": ""},
    )
    fig_ath.update_layout(height=400, xaxis_tickangle=-45)
    st.plotly_chart(fig_ath, use_container_width=True)
