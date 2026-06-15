import streamlit as st
import pandas as pd
import psycopg2
import plotly.express as px

# ──────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EcoBici - Gold",
    page_icon="🥇",
    layout="wide"
)

st.title("🥇 EcoBici Analytics — Dashboard Operativo")
st.subheader("Indicadores analíticos para la gestión del sistema EcoBici CABA")

# ──────────────────────────────────────────────────────────────
# Conexión
# ──────────────────────────────────────────────────────────────
def get_connection():
    return psycopg2.connect(
        host="data_warehouse",   # nombre del servicio en docker-compose
        port=5432,
        dbname="InfraCienciaDatos",
        user="admin",
        password="admin"
    )

@st.cache_data(ttl=300)
def run_query(sql):
    conn = get_connection()
    df = pd.read_sql(sql, conn)
    conn.close()
    return df

# ──────────────────────────────────────────────────────────────
# Carga de datos
# ──────────────────────────────────────────────────────────────

# Estado actual + coordenadas + barrio (JOIN con dim_estacion)
df_estado = run_query("""
    SELECT
        f.station_id,
        f.network_id,
        f.ts,
        f.timestamp_api,
        f.free_bikes_actuales,
        f.empty_slots_actuales,
        f.occupancy_pct_actual,
        f.estado_critico_actual,
        d.name      AS station_name,
        d.latitude,
        d.longitude,
        d.barrio,
        d.comuna,
        d.zona_id
    FROM gold.fact_estado_actual_estacion f
    LEFT JOIN gold.dim_estacion d USING (station_id)
""")

# Ocupación por hora + hora real desde dim_time
df_hora = run_query("""
    SELECT
        f.time_id,
        t.hora,
        t.dia_semana,
        t.nombre_dia,
        f.zona_id,
        f.station_id,
        f.free_bikes_promedio,
        f.empty_slots_promedio,
        f.occupancy_pct_promedio,
        f.porcentaje_tiempo_critico
    FROM gold.fact_ocupacion_por_hora f
    LEFT JOIN gold.dim_time t USING (time_id)
    WHERE t.hora IS NOT NULL
""")

# Top 10 estaciones más críticas (históricamente)
df_top10 = run_query("""
    SELECT
        e.name      AS station_name,
        e.barrio,
        e.zona_id,
        ROUND(AVG(f.porcentaje_tiempo_critico)::numeric, 1)  AS pct_critico_prom,
        ROUND(AVG(f.free_bikes_promedio)::numeric, 1)        AS avg_free_bikes,
        ROUND(AVG(f.occupancy_pct_promedio)::numeric, 1)     AS avg_ocupacion_pct
    FROM gold.fact_ocupacion_por_hora f
    LEFT JOIN gold.dim_estacion e USING (station_id)
    WHERE e.name IS NOT NULL
    GROUP BY e.name, e.barrio, e.zona_id
    ORDER BY pct_critico_prom DESC
    LIMIT 10
""")

# ══════════════════════════════════════════════════════════════
# 1. ESTADO OPERATIVO ACTUAL
# ══════════════════════════════════════════════════════════════
st.divider()
st.header("📊 Estado operativo actual")

# Timestamp de la última actualización
if not df_estado.empty and "ts" in df_estado.columns:
    ts_ultimo = df_estado["ts"].max()
    st.caption(f"📅 Último snapshot registrado: **{ts_ultimo}**")

col1, col2, col3, col4 = st.columns(4)
col1.metric("🚲 Bicis disponibles",
            f"{int(df_estado['free_bikes_actuales'].sum()):,}")
col2.metric("🅿️ Slots libres",
            f"{int(df_estado['empty_slots_actuales'].sum()):,}")
col3.metric("📍 Estaciones activas",
            df_estado["station_id"].nunique())
col4.metric("🚨 Estaciones críticas",
            int(df_estado["estado_critico_actual"].sum()))

# Mapa
df_mapa = df_estado.dropna(subset=["latitude", "longitude"])
if not df_mapa.empty:
    df_mapa["Estado"] = df_mapa["estado_critico_actual"].map(
        {True: "🔴 Crítica", False: "🟢 Normal"}
    )
    fig_map = px.scatter_mapbox(
        df_mapa,
        lat="latitude",
        lon="longitude",
        color="Estado",
        color_discrete_map={"🔴 Crítica": "red", "🟢 Normal": "green"},
        size="free_bikes_actuales",
        hover_name="station_name",
        hover_data={
            "barrio":               True,
            "comuna":               True,
            "free_bikes_actuales":  True,
            "empty_slots_actuales": True,
            "occupancy_pct_actual": True,
            "latitude":  False,
            "longitude": False,
            "Estado":    False,
        },
        zoom=11,
        height=500,
        mapbox_style="open-street-map",
        title="Disponibilidad en tiempo real — Ecobici CABA",
    )
    st.plotly_chart(fig_map, use_container_width=True)
    st.caption("🟢 Normal  |  🔴 Crítica (menos del 10% de bicis o slots disponibles)")

# ══════════════════════════════════════════════════════════════
# 2. VARIACIÓN HORARIA
# ══════════════════════════════════════════════════════════════
st.divider()
st.header("⏰ Variación horaria de disponibilidad")

if not df_hora.empty:

    # Filtro semana / finde
    fines_de_semana = ["Sábado", "Domingo"]
    df_hora["tipo_dia"] = df_hora["nombre_dia"].apply(
        lambda d: "Fin de semana" if d in fines_de_semana else "Semana"
    )

    tipo_sel = st.radio(
        "Filtrar por tipo de día:",
        ["Todos", "Semana", "Fin de semana"],
        horizontal=True,
    )
    df_filtrado = (
        df_hora if tipo_sel == "Todos"
        else df_hora[df_hora["tipo_dia"] == tipo_sel]
    )

    # Franja horaria
    def franja(hora):
        if   6 <= hora < 12: return "Mañana (6-12)"
        elif 12 <= hora < 18: return "Tarde (12-18)"
        else:                  return "Noche (18-6)"

    df_filtrado = df_filtrado.copy()
    df_filtrado["franja"] = df_filtrado["hora"].apply(franja)

    orden_franjas = ["Mañana (6-12)", "Tarde (12-18)", "Noche (18-6)"]

    df_franja = (
        df_filtrado.groupby("franja")[
            ["free_bikes_promedio", "empty_slots_promedio"]
        ]
        .mean()
        .reset_index()
        .melt(id_vars="franja", var_name="Métrica", value_name="Promedio")
    )
    df_franja["Métrica"] = df_franja["Métrica"].map({
        "free_bikes_promedio":  "🚲 Bicis disponibles",
        "empty_slots_promedio": "🅿️ Slots libres",
    })

    fig_franja = px.bar(
        df_franja,
        x="franja",
        y="Promedio",
        color="Métrica",
        barmode="group",
        category_orders={"franja": orden_franjas},
        title=f"Disponibilidad promedio por franja horaria — {tipo_sel}",
        labels={"franja": "Franja horaria", "Promedio": "Cantidad promedio"},
        color_discrete_map={
            "🚲 Bicis disponibles": "#2196F3",
            "🅿️ Slots libres":      "#FF9800",
        },
    )
    st.plotly_chart(fig_franja, use_container_width=True)

    # KPIs de hora pico (hora real desde dim_time)
    df_por_hora = df_filtrado.groupby("hora")[
        ["free_bikes_promedio", "empty_slots_promedio"]
    ].mean()

    hora_critica_bicis = int(df_por_hora["free_bikes_promedio"].idxmin())
    hora_critica_slots = int(df_por_hora["empty_slots_promedio"].idxmin())

    col5, col6 = st.columns(2)
    col5.metric("🚲 Hora más crítica de bicis",
                f"{hora_critica_bicis:02d}:00 hs",
                help=f"Hora del día con menor disponibilidad de bicis — {tipo_sel}")
    col6.metric("🅿️ Hora más crítica de slots",
                f"{hora_critica_slots:02d}:00 hs",
                help=f"Hora del día con menor cantidad de slots libres — {tipo_sel}")

    # Top 3 horas críticas
    top3_bicis = (
        df_por_hora["free_bikes_promedio"]
        .nsmallest(3).reset_index()
        .rename(columns={"hora": "Hora", "free_bikes_promedio": "Bicis promedio"})
    )
    top3_slots = (
        df_por_hora["empty_slots_promedio"]
        .nsmallest(3).reset_index()
        .rename(columns={"hora": "Hora", "empty_slots_promedio": "Slots promedio"})
    )
    top3_bicis["Hora"] = top3_bicis["Hora"].apply(lambda h: f"{int(h):02d}:00 hs")
    top3_slots["Hora"] = top3_slots["Hora"].apply(lambda h: f"{int(h):02d}:00 hs")

    col7, col8 = st.columns(2)
    col7.markdown("**🚲 Top 3 horas con menos bicis**")
    col7.dataframe(top3_bicis.round(1), hide_index=True, use_container_width=True)
    col8.markdown("**🅿️ Top 3 horas con menos slots**")
    col8.dataframe(top3_slots.round(1), hide_index=True, use_container_width=True)

else:
    st.info("Todavía no hay suficientes datos históricos.")

# ══════════════════════════════════════════════════════════════
# 3. DISPONIBILIDAD POR ZONA
# ══════════════════════════════════════════════════════════════
st.divider()
st.header("🏙️ Disponibilidad por zona")

df_zona = (
    df_estado.dropna(subset=["zona_id"])
    .groupby("zona_id")[["free_bikes_actuales", "empty_slots_actuales"]]
    .mean()
    .reset_index()
    .sort_values("free_bikes_actuales", ascending=True)  # más críticas primero
)

if not df_zona.empty:
    df_zona["zona_id"] = df_zona["zona_id"].astype(str)

    fig_zona = px.bar(
        df_zona,
        x="free_bikes_actuales",
        y="zona_id",
        orientation="h",
        title="Promedio de bicis disponibles por zona (de más crítica a menos)",
        labels={
            "free_bikes_actuales": "Bicis disponibles (promedio)",
            "zona_id":             "Zona / Comuna",
        },
        color="free_bikes_actuales",
        color_continuous_scale="RdYlGn",
    )
    fig_zona.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_zona, use_container_width=True)
    st.caption("Las zonas más a la izquierda tienen menos bicis disponibles → mayor criticidad.")
else:
    st.info("Datos de zona no disponibles todavía.")

# ══════════════════════════════════════════════════════════════
# 4. TOP 10 ESTACIONES PROBLEMÁTICAS (HISTÓRICO)
# ══════════════════════════════════════════════════════════════
st.divider()
st.header("🚨 Top 10 estaciones con mayor tiempo en estado crítico")
st.caption("Basado en el historial completo de observaciones registradas — promedio de todas las horas")

if not df_top10.empty:
    fig_top10 = px.bar(
        df_top10.sort_values("pct_critico_prom", ascending=True),
        x="pct_critico_prom",
        y="station_name",
        orientation="h",
        color="pct_critico_prom",
        color_continuous_scale="RdYlGn_r",
        title="% de tiempo en estado crítico por estación",
        labels={
            "pct_critico_prom": "% tiempo crítico",
            "station_name":     "Estación",
        },
        hover_data={"barrio": True, "avg_free_bikes": True, "avg_ocupacion_pct": True},
    )
    st.plotly_chart(fig_top10, use_container_width=True)

    st.dataframe(
        df_top10.rename(columns={
            "station_name":     "Estación",
            "barrio":           "Barrio",
            "zona_id":          "Zona",
            "pct_critico_prom": "% tiempo crítico",
            "avg_free_bikes":   "Bicis promedio",
            "avg_ocupacion_pct":"Ocupación promedio %",
        }),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Todavía no hay suficientes datos históricos para el ranking.")

# ══════════════════════════════════════════════════════════════
# 5. CONCLUSIONES
# ══════════════════════════════════════════════════════════════
st.divider()
st.markdown("""
### 📑 Conclusiones

- 🚲 **Zonas con estaciones vacías** → requieren redistribución de bicicletas
  o incorporación de nuevas unidades al sistema.
- 🅿️ **Zonas con estaciones saturadas** → requieren más estaciones de
  anclaje o ampliación de la red de bicisendas.
- ⏰ **Franjas críticas identificadas** → permiten planificar operaciones
  de rebalanceo en los horarios de mayor demanda,
  diferenciando días de semana de fines de semana.
- 📍 **Estaciones problemáticas recurrentes** → son candidatas prioritarias
  para intervención de infraestructura.
""")
