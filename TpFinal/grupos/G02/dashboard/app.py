import pandas as pd
import plotly.express as px
import streamlit as st

from db import run_query, table_exists


st.set_page_config(
    page_title="ARS Exchange Monitor",
    page_icon="ARS",
    layout="wide",
)

st.title("Monitor de tipo de cambio ARS")
st.caption("Cotizaciones Gold derivadas de Open Exchange Rates")

if not table_exists("gold", "fact_ars_exchange_rates"):
    st.warning("Todavia no existe `gold.fact_ars_exchange_rates`.")
    st.stop()


@st.cache_data(ttl=60)
def load_latest_snapshot() -> pd.DataFrame:
    return run_query(
        """
        SELECT
            currency_code,
            clear_ts,
            rate_per_usd,
            ars_per_usd,
            ars_per_currency,
            currency_per_ars,
            variation_pct_vs_previous
        FROM gold.fact_ars_exchange_rates
        WHERE api_timestamp = (
            SELECT MAX(api_timestamp)
            FROM gold.fact_ars_exchange_rates
        )
        ORDER BY ars_per_currency DESC
        """
    )


@st.cache_data(ttl=60)
def load_history(currency_codes: list[str]) -> pd.DataFrame:
    return run_query(
        """
        SELECT
            currency_code,
            clear_ts,
            ars_per_currency,
            variation_pct_vs_previous
        FROM gold.fact_ars_exchange_rates
        WHERE currency_code = ANY(:currency_codes)
        ORDER BY clear_ts
        """,
        {"currency_codes": currency_codes},
    )


latest = load_latest_snapshot()

if latest.empty:
    st.info("Gold existe, pero todavia no tiene filas cargadas.")
    st.stop()

latest["clear_ts"] = pd.to_datetime(latest["clear_ts"])
last_ts = latest["clear_ts"].max()
ars_row = latest.loc[latest["currency_code"] == "ARS"]
usd_row = latest.loc[latest["currency_code"] == "USD"]
currencies_count = latest["currency_code"].nunique()

metric_cols = st.columns(4)
metric_cols[0].metric("Ultimo snapshot", last_ts.strftime("%Y-%m-%d %H:%M"))
metric_cols[1].metric("Monedas disponibles", f"{currencies_count:,}")

if not usd_row.empty:
    metric_cols[2].metric("1 USD en ARS", f"${usd_row.iloc[0]['ars_per_currency']:,.2f}")
else:
    metric_cols[2].metric("1 USD en ARS", "Sin dato")

if not ars_row.empty:
    metric_cols[3].metric("1 ARS en ARS", f"{ars_row.iloc[0]['ars_per_currency']:,.2f}")
else:
    metric_cols[3].metric("1 ARS en ARS", "Sin dato")

st.divider()

left, right = st.columns([1, 1])

with left:
    st.subheader("Monedas mas caras en ARS")
    top_expensive = latest.head(15).sort_values("ars_per_currency")
    fig_expensive = px.bar(
        top_expensive,
        x="ars_per_currency",
        y="currency_code",
        orientation="h",
        labels={
            "ars_per_currency": "Pesos argentinos por 1 unidad",
            "currency_code": "Moneda",
        },
    )
    fig_expensive.update_layout(height=460, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_expensive, use_container_width=True)

with right:
    st.subheader("Mayor variacion vs snapshot anterior")
    variation = latest.dropna(subset=["variation_pct_vs_previous"]).copy()
    if variation.empty:
        st.info("La variacion aparece cuando hay al menos dos snapshots por moneda.")
    else:
        movers = variation.reindex(
            variation["variation_pct_vs_previous"].abs().sort_values(ascending=False).index
        ).head(15)
        movers = movers.sort_values("variation_pct_vs_previous")
        fig_movers = px.bar(
            movers,
            x="variation_pct_vs_previous",
            y="currency_code",
            orientation="h",
            labels={
                "variation_pct_vs_previous": "Variacion %",
                "currency_code": "Moneda",
            },
            color="variation_pct_vs_previous",
            color_continuous_scale=["#0f8b8d", "#f4f1de", "#c44536"],
        )
        fig_movers.update_layout(height=460, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_movers, use_container_width=True)

st.divider()

st.subheader("Explorar cotizaciones")

currency_options = latest["currency_code"].tolist()
default_selection = [
    code for code in ["USD", "EUR", "BRL", "CLP", "UYU", "GBP"] if code in currency_options
]
selected_codes = st.multiselect(
    "Monedas para comparar historicamente",
    options=currency_options,
    default=default_selection or currency_options[:5],
)

filter_text = st.text_input("Filtrar tabla por codigo de moneda", "")
table_df = latest.copy()
if filter_text:
    table_df = table_df[
        table_df["currency_code"].str.contains(filter_text.upper().strip(), na=False)
    ]

st.dataframe(
    table_df[
        [
            "currency_code",
            "ars_per_currency",
            "currency_per_ars",
            "variation_pct_vs_previous",
            "rate_per_usd",
        ]
    ].rename(
        columns={
            "currency_code": "Moneda",
            "ars_per_currency": "ARS por 1 moneda",
            "currency_per_ars": "Moneda por 1 ARS",
            "variation_pct_vs_previous": "Variacion %",
            "rate_per_usd": "Moneda por 1 USD",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

if selected_codes:
    history = load_history(selected_codes)
    if not history.empty:
        history["clear_ts"] = pd.to_datetime(history["clear_ts"])
        fig_history = px.line(
            history,
            x="clear_ts",
            y="ars_per_currency",
            color="currency_code",
            markers=True,
            labels={
                "clear_ts": "Fecha y hora",
                "ars_per_currency": "ARS por 1 unidad",
                "currency_code": "Moneda",
            },
        )
        fig_history.update_layout(height=440, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_history, use_container_width=True)
