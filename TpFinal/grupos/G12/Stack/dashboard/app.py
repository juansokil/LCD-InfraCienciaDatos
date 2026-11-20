import plotly.express as px
import streamlit as st

from db import NARANJA, boton_actualizar, chequear_datos, consulta

st.set_page_config(page_title="Sismos G12", page_icon="🌎", layout="wide")
boton_actualizar()

st.title("🌎 Sismos en el mundo")
st.write(
    "TP Final del Grupo 12. Cada 15 minutos Airflow baja los sismos de magnitud 2.5 o más "
    "de la API del USGS, los limpia en Silver y los guarda en Gold en un modelo estrella. "
    "Este tablero lee las tablas de Gold."
)

chequear_datos()

# ---- numeros generales ----
totales = consulta("""
    SELECT SUM(f.cantidad_terremoto)  AS terremotos,
           MAX(f.magnitud)            AS mag_max,
           AVG(f.magnitud)            AS mag_prom,
           AVG(f.profundidad)         AS prof_prom,
           COUNT(DISTINCT f.fecha_id) AS dias,
           MIN(d.fecha)               AS desde,
           MAX(d.fecha)               AS hasta
    FROM gold.fact_terremoto f
    JOIN gold.dim_fecha d ON d.fecha_id = f.fecha_id
""").iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Terremotos", f"{int(totales['terremotos']):,}".replace(",", "."))
c2.metric("Magnitud máxima", f"{totales['mag_max']:.1f}")
c3.metric("Magnitud promedio", f"{totales['mag_prom']:.2f}")
c4.metric("Profundidad promedio", f"{totales['prof_prom']:.0f} km")

st.caption(
    f"Datos del {totales['desde']:%d/%m/%Y} al {totales['hasta']:%d/%m/%Y} "
    f"({int(totales['dias'])} días). Fechas en UTC."
)

st.divider()

# ---- los mas fuertes ----
st.subheader("Los 10 terremotos más fuertes")
fuertes = consulta("""
    SELECT d.fecha, u.region, COALESCE(u.ubicacion, '-') AS ubicacion, f.magnitud, m.tipo_magnitud,
           f.profundidad, a.tipo_alerta
    FROM gold.fact_terremoto f
    JOIN gold.dim_fecha d     ON d.fecha_id = f.fecha_id
    JOIN gold.dim_ubicacion u ON u.id_ubicacion = f.id_ubicacion
    JOIN gold.dim_magnitud m  ON m.id_magnitud = f.id_magnitud
    JOIN gold.dim_alerta a    ON a.id_alerta = f.id_alerta
    ORDER BY f.magnitud DESC
    LIMIT 10
""")
st.dataframe(
    fuertes,
    hide_index=True,
    use_container_width=True,
    column_config={
        "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
        "region": "Región",
        "ubicacion": "Ubicación",
        "magnitud": st.column_config.ProgressColumn("Magnitud", format="%.1f", min_value=0, max_value=10),
        "tipo_magnitud": "Escala",
        "profundidad": st.column_config.NumberColumn("Profundidad (km)", format="%.0f"),
        "tipo_alerta": "Alerta",
    },
)

# ---- regiones ----
st.subheader("¿Dónde tiembla más?")
regiones = consulta("""
    SELECT u.region, SUM(f.cantidad_terremoto) AS terremotos
    FROM gold.fact_terremoto f
    JOIN gold.dim_ubicacion u ON u.id_ubicacion = f.id_ubicacion
    GROUP BY u.region
    ORDER BY terremotos DESC
    LIMIT 10
""")
fig = px.bar(
    regiones.sort_values("terremotos"),
    x="terremotos",
    y="region",
    orientation="h",
    color_discrete_sequence=[NARANJA],
    labels={"terremotos": "Terremotos", "region": ""},
)
st.plotly_chart(fig, use_container_width=True)

st.caption("En la barra de la izquierda hay más páginas: evolución en el tiempo y magnitudes y alertas.")