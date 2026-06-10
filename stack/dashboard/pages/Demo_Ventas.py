
"""
Pagina demo pedagogica - Star Schema (BI) y ABT (ML) generados por los
DAGs didacticos de clase05 (gold_01_star_basico, gold_02_abt).

Conecta con las tablas (sufijo _demo, no colisionan con crypto_gold):
  - gold.dim_producto_demo, gold.dim_tiempo_demo, gold.fact_ventas_demo  (Star Schema / BI)
  - gold.abt_clientes_demo                                               (ABT / ML)
"""

import streamlit as st
import plotly.express as px
import pandas as pd
from db import load_table, get_row_count, table_exists, get_engine, run_query

st.header("Demo Pedagogico - Star Schema y ABT")
st.caption("Datos sinteticos de `gold_01_star_basico` y `gold_02_abt`. "
           "Las dos audiencias de Gold: **BI** (Star Schema) y **ML** (ABT).")

engine = get_engine()
needed = [("gold", "fact_ventas_demo"), ("gold", "dim_producto_demo"),
          ("gold", "dim_tiempo_demo"), ("gold", "abt_clientes_demo")]
missing = [f"{s}.{t}" for s, t in needed if not table_exists(engine, s, t)]
if missing:
    st.warning(
        "Faltan tablas: " + ", ".join(missing) +
        ". Ejecuta los DAGs `gold_01_star_basico` y `gold_02_abt` desde Airflow."
    )
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Productos", get_row_count("gold", "dim_producto_demo"))
col2.metric("Fechas", get_row_count("gold", "dim_tiempo_demo"))
col3.metric("Ventas", get_row_count("gold", "fact_ventas_demo"))
col4.metric("Clientes", get_row_count("gold", "abt_clientes_demo"))
st.divider()

tab_bi, tab_ml = st.tabs(["\U0001F4CA BI — Star Schema", "\U0001F916 ML — ABT"])

# =============================================================
# TAB BI: Star Schema = JOIN fact + dim + agregacion
# =============================================================
with tab_bi:
    st.caption("Consumo BI: se hace **JOIN** fact + dim y se **agrega**. "
               "Es lo que hace un dashboard / reporte.")

    top_n = st.slider("Top N productos por monto", 3, 12, 8)
    q_vp = """
        SELECT p.producto, SUM(f.monto_total) AS total
        FROM gold.fact_ventas_demo f
        JOIN gold.dim_producto_demo p ON f.producto_id = p.producto_id
        GROUP BY p.producto
        ORDER BY total DESC
    """
    df_vp = run_query(q_vp).head(top_n)
    if not df_vp.empty:
        fig = px.bar(df_vp, x="producto", y="total", color="total",
                     color_continuous_scale="Blues",
                     labels={"total": "Monto total ($)", "producto": ""},
                     title=f"Top {top_n} productos por monto")
        fig.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    q_vm = """
        SELECT t.anio, t.mes, SUM(f.monto_total) AS monto
        FROM gold.fact_ventas_demo f
        JOIN gold.dim_tiempo_demo t ON f.fecha_id = t.fecha_id
        GROUP BY t.anio, t.mes
        ORDER BY t.anio, t.mes
    """
    df_vm = run_query(q_vm)
    if not df_vm.empty:
        df_vm["periodo"] = (df_vm["anio"].astype(str) + "-"
                            + df_vm["mes"].astype(str).str.zfill(2))
        fig2 = px.line(df_vm, x="periodo", y="monto", markers=True,
                       labels={"monto": "Monto total ($)", "periodo": ""},
                       title="Ventas por mes (JOIN con dim_tiempo_demo)")
        fig2.update_layout(height=300)
        st.plotly_chart(fig2, use_container_width=True)

# =============================================================
# TAB ML: ABT = 1 fila por cliente, features ya derivadas, SIN JOINs
# =============================================================
with tab_ml:
    st.caption("Consumo ML: **1 fila = 1 cliente**, features ya derivadas, "
               "**sin JOINs** (lista para entrenar un modelo).")

    abt = load_table("gold", "abt_clientes_demo")
    if not abt.empty:
        colors = {"Bronze": "#cd7f32", "Silver": "#c0c0c0", "Gold": "#ffd700"}
        c1, c2 = st.columns(2)
        with c1:
            seg = abt["segmento_valor"].value_counts().reset_index()
            seg.columns = ["segmento", "clientes"]
            fig_seg = px.pie(seg, names="segmento", values="clientes", hole=0.4,
                             color="segmento", color_discrete_map=colors,
                             title="Clientes por segmento")
            fig_seg.update_layout(height=300, margin=dict(t=40, b=10))
            st.plotly_chart(fig_seg, use_container_width=True)
        with c2:
            ins = (abt.groupby("segmento_valor", as_index=False)["ticket_promedio"]
                      .mean().sort_values("ticket_promedio", ascending=False))
            fig_ins = px.bar(ins, x="segmento_valor", y="ticket_promedio",
                             color="segmento_valor", color_discrete_map=colors,
                             labels={"ticket_promedio": "Ticket promedio ($)",
                                     "segmento_valor": ""},
                             title="Ticket promedio por segmento")
            fig_ins.update_layout(height=300, showlegend=False,
                                  margin=dict(t=40, b=10))
            st.plotly_chart(fig_ins, use_container_width=True)

        segs = ["Todos"] + sorted(abt["segmento_valor"].dropna().unique().tolist())
        sel = st.selectbox("Filtrar tabla por segmento", segs)
        view = abt if sel == "Todos" else abt[abt["segmento_valor"] == sel]
        st.dataframe(view.sort_values("monto_total", ascending=False),
                     use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "**Patron didactico:** estos DAGs generan tablas sinteticas hardcoded. "
    "El DAG productivo `crypto_gold` aplica el MISMO patron (Star Schema + ABT) "
    "sobre datos reales de criptomonedas, y las paginas Gold reales del "
    "dashboard lo consumen igual que esta demo."
)
