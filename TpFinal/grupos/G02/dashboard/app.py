import os

import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(page_title="Demo Medallion", page_icon="📊", layout="wide")
st.title("Pipeline Medallion – Ventas ficticias")
st.caption("Dashboard de prueba: consulta exclusivamente las tablas del esquema Gold.")


def get_connection():
    return psycopg2.connect(
        host=os.getenv("WAREHOUSE_HOST", "warehouse"),
        port=os.getenv("WAREHOUSE_PORT", "5432"),
        dbname=os.getenv("WAREHOUSE_DB", "weather_dw"),
        user=os.getenv("WAREHOUSE_USER", "weather"),
        password=os.getenv("WAREHOUSE_PASSWORD", "weather_db_password"),
        connect_timeout=5,
    )


@st.cache_data(ttl=10)
def load_data():
    with get_connection() as conn:
        city = pd.read_sql_query(
            """
            SELECT city, SUM(total_revenue)::float AS revenue,
                   SUM(units_sold)::integer AS units,
                   SUM(transactions)::integer AS transactions
            FROM gold.fact_sales_daily
            GROUP BY city
            ORDER BY revenue DESC
            """,
            conn,
        )
        daily = pd.read_sql_query(
            """
            SELECT sale_date, SUM(total_revenue)::float AS revenue
            FROM gold.fact_sales_daily
            GROUP BY sale_date
            ORDER BY sale_date
            """,
            conn,
        )
        counts = pd.read_sql_query(
            """
            SELECT
              (SELECT COUNT(*) FROM bronze.sales_raw) AS bronze_rows,
              (SELECT COUNT(*) FROM silver.sales_clean) AS silver_rows,
              (SELECT COUNT(*) FROM gold.fact_sales_daily) AS gold_rows
            """,
            conn,
        )
    return city, daily, counts.iloc[0]


if st.button("Actualizar datos"):
    st.cache_data.clear()

try:
    city_data, daily_data, counts = load_data()
except Exception as exc:
    st.error("No se pudo consultar PostgreSQL. Verificá que el servicio warehouse esté iniciado.")
    st.code(str(exc))
    st.stop()

metric1, metric2, metric3 = st.columns(3)
metric1.metric("Bronze · registros crudos", int(counts["bronze_rows"]))
metric2.metric("Silver · registros válidos", int(counts["silver_rows"]))
metric3.metric("Gold · filas agregadas", int(counts["gold_rows"]))

if city_data.empty:
    st.info("Todavía no hay datos en Gold. Esperá a que finalicen los DAGs demo_bronze, demo_silver y demo_gold en Airflow.")
    st.stop()

left, right = st.columns(2)
with left:
    st.subheader("Facturación por ciudad")
    st.bar_chart(city_data.set_index("city")["revenue"], y_label="Facturación ($)")
with right:
    st.subheader("Facturación por día")
    st.line_chart(daily_data.set_index("sale_date")["revenue"], y_label="Facturación ($)")

st.subheader("Resumen Gold")
st.dataframe(city_data.rename(columns={
    "city": "Ciudad", "revenue": "Facturación ($)",
    "units": "Unidades vendidas", "transactions": "Transacciones",
}), use_container_width=True, hide_index=True)

st.caption("Los datos son inventados. Bronze conserva los 12 registros, Silver descarta 2 registros inválidos y Gold agrega las ventas limpias.")