import pandas as pd
import plotly.express as px
import streamlit as st
from babel.numbers import UnknownCurrencyError, get_currency_name

from db import run_query, table_exists

DEFAULT_CURRENCIES = ["USD", "EUR", "BRL", "CLP", "UYU", "GBP"]
VARIATION_ALERT_THRESHOLD = 5.0
DEFAULT_TOP_N = 15
TOP_EXPENSIVE_N = 5
MANUAL_CURRENCY_NAMES = {
    "USD": "Dólar estadounidense",
    "EUR": "Euro",
    "BRL": "Real brasileño",
    "CLP": "Peso chileno",
    "UYU": "Peso uruguayo",
    "GBP": "Libra esterlina",
    "ARS": "Peso argentino",
}


st.title("Monitor de tipo de cambio ARS")
st.caption("Cotizaciones Gold derivadas de Open Exchange Rates")

if not table_exists("gold", "fact_ars_exchange_rates"):
    st.warning(
        "Todavía no existe la tabla Gold `gold.fact_ars_exchange_rates`. "
        "Ejecutá el pipeline completo antes de abrir el dashboard."
    )
    st.stop()


def currency_name_from_code(code: str) -> str:
    if code in MANUAL_CURRENCY_NAMES:
        return MANUAL_CURRENCY_NAMES[code]

    try:
        name = get_currency_name(code, locale="es")
    except UnknownCurrencyError:
        return code

    return name[:1].upper() + name[1:] if name else code


def add_currency_names(df: pd.DataFrame) -> pd.DataFrame:
    named_df = df.copy()
    named_df["currency_name"] = named_df["currency_code"].map(currency_name_from_code)
    return named_df


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

st.sidebar.header("Filtros")

alert_threshold = st.sidebar.slider(
    "Umbral de alerta por variación (%)",
    min_value=1.0,
    max_value=20.0,
    value=VARIATION_ALERT_THRESHOLD,
    step=1.0,
)

if latest.empty:
    st.info("Gold existe, pero todavía no tiene filas cargadas.")
    st.stop()

latest["clear_ts"] = pd.to_datetime(latest["clear_ts"])
latest = add_currency_names(latest)
last_ts = latest["clear_ts"].max()
usd_row = latest.loc[latest["currency_code"] == "USD"]
eur_row = latest.loc[latest["currency_code"] == "EUR"]
currencies_count = latest["currency_code"].nunique()

metric_cols = st.columns(4)
metric_cols[0].metric("Último snapshot", last_ts.strftime("%Y-%m-%d %H:%M"))
metric_cols[1].metric("Monedas disponibles", f"{currencies_count:,}")

if not usd_row.empty:
    metric_cols[2].metric("1 USD en ARS", f"${usd_row.iloc[0]['ars_per_currency']:,.2f}")
else:
    metric_cols[2].metric("1 USD en ARS", "Sin dato")

if not eur_row.empty:
    metric_cols[3].metric("1 EUR en ARS", f"${eur_row.iloc[0]['ars_per_currency']:,.2f}")
else:
    metric_cols[3].metric("1 EUR en ARS", "Sin dato")

st.divider()

left, right = st.columns([1, 1])

with left:
    st.subheader("Top 5 de monedas más caras en ARS")
    top_expensive = (
        latest.sort_values("ars_per_currency", ascending=False)
        .head(TOP_EXPENSIVE_N)
        .sort_values("ars_per_currency", ascending=True)
    )
    fig_expensive = px.bar(
        top_expensive,
        x="ars_per_currency",
        y="currency_name",
        orientation="h",
        labels={
            "ars_per_currency": "Pesos argentinos por 1 unidad",
            "currency_name": "Moneda",
        },
    )
    fig_expensive.update_layout(height=460, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_expensive, use_container_width=True)

with right:
    st.subheader("Mayor variación vs snapshot anterior")
    variation = latest.dropna(subset=["variation_pct_vs_previous"]).copy()
    if variation.empty:
        st.info("La variación aparece cuando hay al menos dos snapshots por moneda.")
    else:
        movers = variation.reindex(
            variation["variation_pct_vs_previous"].abs().sort_values(ascending=False).index
        ).head(DEFAULT_TOP_N)
        movers["variation_pct_vs_previous"] = movers["variation_pct_vs_previous"].round(2)
        movers = movers.sort_values("variation_pct_vs_previous")
        fig_movers = px.bar(
            movers,
            x="variation_pct_vs_previous",
            y="currency_name",
            orientation="h",
            labels={
                "variation_pct_vs_previous": "Variación %",
                "currency_name": "Moneda",
            },
            color="variation_pct_vs_previous",
            color_continuous_scale=["#0f8b8d", "#f4f1de", "#c44536"],
            text="variation_pct_vs_previous",
        )
        fig_movers.update_traces(texttemplate="%{text:.2f}", textposition="outside")
        fig_movers.update_layout(height=460, margin=dict(l=10, r=10, t=20, b=10))
        fig_movers.update_xaxes(tickformat=".2f")
        st.plotly_chart(fig_movers, use_container_width=True)

st.divider()

st.subheader("Alertas de variación")

variation_alerts = (
    latest.dropna(subset=["variation_pct_vs_previous"])
    .loc[lambda df: df["variation_pct_vs_previous"].abs() >= alert_threshold]
    .sort_values("variation_pct_vs_previous", ascending=False)
)

if variation_alerts.empty:
    st.success(
        f"No hay monedas con variación mayor a ±{alert_threshold:.0f}% respecto del snapshot anterior."
    )
else:
    variation_alerts_display = variation_alerts.assign(
        variation_pct_vs_previous=lambda df: df["variation_pct_vs_previous"].round(2)
    )
    st.warning(
        f"Se detectaron {len(variation_alerts)} monedas con variación mayor a ±{alert_threshold:.0f}%."
    )

    st.dataframe(
        variation_alerts_display[
            [
                "currency_name",
                "ars_per_currency",
                "variation_pct_vs_previous",
                "rate_per_usd",
            ]
        ].rename(
            columns={
                "currency_name": "Moneda",
                "ars_per_currency": "ARS por 1 moneda",
                "variation_pct_vs_previous": "Variación %",
                "rate_per_usd": "Moneda por 1 USD",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Explorar cotizaciones")

filter_text = st.text_input("Filtrar tabla por nombre de moneda", "")
table_df = latest.copy()
if filter_text:
    table_df = table_df[
        table_df["currency_name"].str.contains(filter_text.strip(), case=False, na=False)
    ]

table_df = table_df.assign(
    variation_pct_vs_previous=lambda df: df["variation_pct_vs_previous"].round(2)
)

st.dataframe(
    table_df[
        [
            "currency_name",
            "ars_per_currency",
            "currency_per_ars",
            "variation_pct_vs_previous",
            "rate_per_usd",
        ]
    ].rename(
        columns={
            "currency_name": "Moneda",
            "ars_per_currency": "ARS por 1 moneda",
            "currency_per_ars": "Moneda por 1 ARS",
            "variation_pct_vs_previous": "Variación %",
            "rate_per_usd": "Moneda por 1 USD",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

st.subheader("Comparación histórica")

currency_options = latest["currency_code"].tolist()
default_selection = [code for code in DEFAULT_CURRENCIES if code in currency_options]
selected_codes = st.multiselect(
    "Monedas para comparar históricamente",
    options=currency_options,
    default=default_selection or currency_options[:5],
    format_func=currency_name_from_code,
)

if selected_codes:
    history = load_history(selected_codes)
    if not history.empty:
        history["clear_ts"] = pd.to_datetime(history["clear_ts"])
        history = add_currency_names(history)
        fig_history = px.line(
            history,
            x="clear_ts",
            y="ars_per_currency",
            color="currency_name",
            markers=True,
            labels={
                "clear_ts": "Fecha y hora",
                "ars_per_currency": "ARS por 1 unidad",
                "currency_name": "Moneda",
            },
        )
        fig_history.update_layout(height=440, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig_history, use_container_width=True)
