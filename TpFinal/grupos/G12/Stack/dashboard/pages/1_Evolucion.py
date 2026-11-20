import plotly.express as px
import streamlit as st

from db import CELESTE, NARANJA, boton_actualizar, chequear_datos, consulta

st.set_page_config(page_title="Evolución", page_icon="📈", layout="wide")
boton_actualizar()
st.title("📈 Evolución en el tiempo")

chequear_datos()

por_dia = consulta("""
    SELECT d.fecha, d.dia_semana,
           SUM(f.cantidad_terremoto) AS terremotos,
           AVG(f.magnitud)           AS mag_prom,
           MAX(f.magnitud)           AS mag_max
    FROM gold.fact_terremoto f
    JOIN gold.dim_fecha d ON d.fecha_id = f.fecha_id
    GROUP BY d.fecha, d.dia_semana
    ORDER BY d.fecha
""")

# filtro de fechas
desde, hasta = por_dia["fecha"].min(), por_dia["fecha"].max()
rango = st.sidebar.date_input("Período", value=(desde, hasta), min_value=desde, max_value=hasta)
if len(rango) == 2:
    por_dia = por_dia[(por_dia["fecha"] >= rango[0]) & (por_dia["fecha"] <= rango[1])]

c1, c2, c3 = st.columns(3)
c1.metric("Terremotos en el período", int(por_dia["terremotos"].sum()))
c2.metric("Promedio por día", f"{por_dia['terremotos'].mean():.1f}")
c3.metric("Día con más terremotos", f"{por_dia.loc[por_dia['terremotos'].idxmax(), 'fecha']:%d/%m}")

st.subheader("Terremotos por día")
fig = px.bar(
    por_dia, x="fecha", y="terremotos",
    color_discrete_sequence=[NARANJA],
    labels={"fecha": "", "terremotos": "Terremotos"},
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Magnitud por día")
fig = px.line(
    por_dia, x="fecha", y=["mag_max", "mag_prom"], markers=True,
    labels={"fecha": "", "value": "Magnitud", "variable": ""},
    color_discrete_sequence=[NARANJA, CELESTE],
)
fig.for_each_trace(lambda t: t.update(name={"mag_max": "Máxima", "mag_prom": "Promedio"}[t.name]))
st.plotly_chart(fig, use_container_width=True)

# dia de la semana (1 = lunes ... 7 = domingo)
st.subheader("¿Hay días de la semana con más actividad?")
dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
semana = por_dia.groupby("dia_semana", as_index=False)["terremotos"].mean()
semana["dia"] = semana["dia_semana"].map(lambda d: dias[int(d) - 1])
fig = px.bar(
    semana, x="dia", y="terremotos",
    color_discrete_sequence=[CELESTE],
    labels={"dia": "", "terremotos": "Promedio de terremotos"},
)
st.plotly_chart(fig, use_container_width=True)
st.caption("Spoiler: no debería haber diferencia, los terremotos no saben qué día es.")