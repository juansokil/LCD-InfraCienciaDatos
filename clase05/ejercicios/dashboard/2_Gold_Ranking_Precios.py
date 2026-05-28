"""
Ranking y Precios - Tabla interactiva con filtros y comparacion.
Objetivo: responder "cual es el precio de X? como se compara con Y?"
"""

import streamlit as st
import plotly.express as px
from db import load_table, show_last_updated_badge

st.header("Gold - Ranking y Precios")
show_last_updated_badge("gold", "fact_crypto_markets", col="_processed_at")

# --- Cargar datos ---
fact = load_table("gold", "fact_crypto_markets")
dim = load_table("gold", "dim_crypto")

if fact.empty:
    st.warning("No hay datos en gold todavia. Ejecuta el pipeline desde Airflow.")
    st.stop()

df = fact.copy()
if not dim.empty and "crypto_id" in dim.columns:
    df = df.merge(dim[["crypto_id", "name", "symbol"]], on="crypto_id", how="left")

if "name" not in df.columns:
    st.error("Faltan columnas de nombre. Revisa el pipeline Gold.")
    st.stop()

unique_df = df.drop_duplicates(subset="crypto_id").sort_values("market_cap", ascending=False)

# =============================================================
# FILTROS
# =============================================================
with st.sidebar:
    st.subheader("Filtros")

    # Filtro por rango de precio
    if "current_price" in unique_df.columns:
        price_min = float(unique_df["current_price"].min())
        price_max = float(unique_df["current_price"].max())
        price_range = st.slider(
            "Rango de precio (USD)",
            min_value=price_min, max_value=price_max,
            value=(price_min, price_max), format="$%.2f",
        )
        unique_df = unique_df[
            unique_df["current_price"].between(price_range[0], price_range[1])
        ]

    # Filtro por rank
    if "market_cap_rank" in unique_df.columns:
        max_rank = int(unique_df["market_cap_rank"].max())
        rank_limit = st.slider("Top N por ranking", 5, max(max_rank, 50), 50)
        unique_df = unique_df[unique_df["market_cap_rank"] <= rank_limit]

# =============================================================
# TABLA DE PRECIOS
# =============================================================
st.subheader(f"Tabla de precios ({len(unique_df)} criptos)")

display_cols = ["market_cap_rank", "name", "symbol", "current_price", "market_cap",
                "total_volume", "price_change_percentage_24h", "high_24h", "low_24h"]
available_cols = [c for c in display_cols if c in unique_df.columns]

tabla = unique_df[available_cols].reset_index(drop=True)

col_config = {
    "current_price": st.column_config.NumberColumn("Precio", format="$%.2f"),
    "market_cap": st.column_config.NumberColumn("Market Cap", format="$%.0f"),
    "total_volume": st.column_config.NumberColumn("Volumen 24h", format="$%.0f"),
    "price_change_percentage_24h": st.column_config.NumberColumn("Cambio 24h %", format="%.2f%%"),
    "high_24h": st.column_config.NumberColumn("Max 24h", format="$%.2f"),
    "low_24h": st.column_config.NumberColumn("Min 24h", format="$%.2f"),
    "market_cap_rank": st.column_config.NumberColumn("Rank", format="%d"),
    "name": "Nombre",
    "symbol": "Simbolo",
}

st.dataframe(tabla, column_config=col_config, use_container_width=True, hide_index=True)

st.divider()

# =============================================================
# COMPARADOR
# =============================================================
st.subheader("Comparar criptomonedas")

all_names = sorted(unique_df["name"].dropna().unique())
selected = st.multiselect("Selecciona criptos para comparar", all_names, default=all_names[:3])

if selected:
    compare_df = unique_df[unique_df["name"].isin(selected)]

    metrics = ["current_price", "market_cap", "total_volume"]
    available_metrics = [m for m in metrics if m in compare_df.columns]

    for metric in available_metrics:
        labels = {
            "current_price": "Precio (USD)",
            "market_cap": "Market Cap (USD)",
            "total_volume": "Volumen 24h (USD)",
        }
        fig = px.bar(
            compare_df, x="name", y=metric, color="name",
            labels={metric: labels.get(metric, metric), "name": ""},
        )
        fig.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
