import streamlit as st
import pandas as pd
import psycopg2

import plotly.express as px

# Zona horaria en la que se interpretan los indicadores horarios del dashboard.
# Los timestamps de la API vienen en UTC; para otras redes puede cambiarse este valor.
LOCAL_TIMEZONE = "America/Argentina/Buenos_Aires"

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

st.markdown("""
**El presente dashboard permite observar:** 
- Disponibilidad de bicis en tiempo real
- Slots disponibles para devolución en tiempo real 
- Variación horaria de la disponibilidad, según el tipo de día o según la zona
- Promedio de bicis disponibles según la zona
- Relación entre bicis disponibles y slots disponibles
- Estaciones que suelen tener más bicis disponibles o más slots disponibles
""")

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
# Utilidades de zona horaria
# ──────────────────────────────────────────────────────────────
def aplicar_horario_local(df, time_id_col="time_id", timezone=LOCAL_TIMEZONE):
    """Convierte un time_id generado en UTC (YYYYMMDDHH) a hora local para visualización."""
    if df.empty or time_id_col not in df.columns:
        return df

    df = df.copy()
    time_id_str = df[time_id_col].astype("Int64").astype(str)
    datetime_local = pd.to_datetime(
        time_id_str,
        format="%Y%m%d%H",
        errors="coerce",
        utc=True,
    ).dt.tz_convert(timezone)

    df["datetime_local"] = datetime_local
    df["hora"] = datetime_local.dt.hour
    df["dia_semana"] = datetime_local.dt.isocalendar().day.astype("Int64")

    nombres_dia = {
        1: "Lunes",
        2: "Martes",
        3: "Miércoles",
        4: "Jueves",
        5: "Viernes",
        6: "Sábado",
        7: "Domingo",
    }
    df["nombre_dia"] = df["dia_semana"].map(nombres_dia)

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
        f.free_bikes_pct_actual,
        f.tipo_estacion_actual,
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

# Disponibilidad por hora y zona + hora real desde dim_time
df_hora = run_query("""
    SELECT
        f.time_id,
        t.hora,
        t.dia_semana,
        t.nombre_dia,
        f.zona_id,
        e.comuna,
        e.barrio,
        f.station_id,
        f.free_bikes_promedio,
        f.empty_slots_promedio,
        f.free_bikes_pct_promedio,
        f.porcentaje_tiempo_devolucion,
        f.porcentaje_tiempo_equilibrada,
        f.porcentaje_tiempo_alquiler
    FROM gold.fact_ocupacion_por_hora f
    LEFT JOIN gold.dim_time t USING (time_id)
    LEFT JOIN gold.dim_estacion e USING (station_id)
    WHERE t.hora IS NOT NULL
""")

# Ajuste de zona horaria para visualización.
# Gold conserva time_id como hora UTC; el dashboard lo interpreta en horario local.
df_hora = aplicar_horario_local(df_hora)

# Perfil funcional histórico de estaciones
df_perfil_estaciones = run_query("""
    SELECT
        e.name AS station_name,
        e.barrio,
        e.comuna,
        ROUND((AVG(f.porcentaje_tiempo_devolucion) * 100)::numeric, 1)  AS pct_tiempo_devolucion,
        ROUND((AVG(f.porcentaje_tiempo_equilibrada) * 100)::numeric, 1) AS pct_tiempo_equilibrada,
        ROUND((AVG(f.porcentaje_tiempo_alquiler) * 100)::numeric, 1)    AS pct_tiempo_alquiler,
        ROUND(AVG(f.free_bikes_promedio)::numeric, 1)                  AS avg_free_bikes,
        ROUND(AVG(f.free_bikes_pct_promedio)::numeric, 1)              AS avg_free_bikes_pct
    FROM gold.fact_ocupacion_por_hora f
    LEFT JOIN gold.dim_estacion e USING (station_id)
    WHERE e.name IS NOT NULL
    GROUP BY e.name, e.barrio, e.comuna
""")

# ══════════════════════════════════════════════════════════════
# 1. ESTADO OPERATIVO ACTUAL
# ══════════════════════════════════════════════════════════════
st.divider()
st.header("📊 Estado operativo actual")

# Timestamp de la última actualización
if not df_estado.empty and "ts" in df_estado.columns:
    ts_ultimo = df_estado["ts"].max()
    st.caption(f"📅 Último snapshot registrado: **{ts_ultimo}** · Zona horaria visualizada: **{LOCAL_TIMEZONE}**")

col1, col2, col3, col4 = st.columns(4)
col1.metric("🚲 Bicis disponibles",
            f"{int(df_estado['free_bikes_actuales'].sum()):,}")
col2.metric("🅿️ Slots libres",
            f"{int(df_estado['empty_slots_actuales'].sum()):,}")
col3.metric("📍 Estaciones activas",
            df_estado["station_id"].nunique())
col4.metric("⚖️ Estaciones no equilibradas",
            int(df_estado["estado_critico_actual"].sum()))

# Mapa
df_mapa = df_estado.dropna(subset=["latitude", "longitude"])
if not df_mapa.empty:
    df_mapa["Tipo de estación"] = df_mapa["tipo_estacion_actual"]
    fig_map = px.scatter_mapbox(
        df_mapa,
        lat="latitude",
        lon="longitude",
        color="Tipo de estación",
        size="free_bikes_actuales",
        hover_name="station_name",
        hover_data=[
            "barrio",
            "comuna",
            "free_bikes_actuales",
            "empty_slots_actuales",
            "free_bikes_pct_actual",
            "Tipo de estación",
        ],
        color_discrete_map={
            "Estación de devolución": "#2196F3",   # azul
            "Estación equilibrada": "#FFC107",    # amarillo
            "Estación de alquiler": "#F44336",    # rojo
        },
        zoom=11,
        height=500,
        mapbox_style="open-street-map",

        title="Disponibilidad en tiempo real — Ecobici CABA",
    )
    fig_map.update_traces(
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "Barrio: %{customdata[0]}<br>"
            "Comuna: %{customdata[1]}<br>"
            "🚲 Bicis disponibles: %{customdata[2]:.0f}<br>"
            "🅿️ Slots libres: %{customdata[3]:.0f}<br>"
            "📊 % bicis disponibles: %{customdata[4]:.1f}%<br>"
            "⚖️ %{customdata[5]}"
            "<extra></extra>"
        )
    )
    st.plotly_chart(fig_map, use_container_width=True)
    st.caption("Clasificación: devolución (<40% bicis), equilibrada (40–60%), alquiler (>60%).")

# ══════════════════════════════════════════════════════════════
# 2. VARIACIÓN HORARIA, POR BARRIO O COMUNA
# ══════════════════════════════════════════════════════════════
st.divider()
st.header("⏰ Variación horaria de disponibilidad")

if not df_hora.empty:

    # Filtro semana / finde
    fines_de_semana = [6, 7]
    df_hora["tipo_dia"] = df_hora["dia_semana"].apply(
        lambda d: "Fin de semana" if d in fines_de_semana else "Semana"
    )

    col_filtro_dia, col_filtro_comuna, col_filtro_barrio = st.columns(3)

    with col_filtro_dia:
        tipo_sel = st.radio(
            "Filtrar por tipo de día:",
            ["Todos los días", "Semana", "Fin de semana"],
            horizontal=True,
        )

    comunas_disponibles = sorted(
        df_hora["comuna"].dropna().astype(int).unique().tolist()
    ) if "comuna" in df_hora.columns and not df_hora["comuna"].dropna().empty else []

    with col_filtro_comuna:
        comuna_sel = st.selectbox(
            "Filtrar por comuna:",
            ["Todas las comunas"] + [f"Comuna {c}" for c in comunas_disponibles],
        )

    df_barrios_posibles = df_hora.copy()
    if comuna_sel != "Todas las comunas":
        comuna_num = int(comuna_sel.replace("Comuna ", ""))
        df_barrios_posibles = df_barrios_posibles[df_barrios_posibles["comuna"] == comuna_num]

    barrios_disponibles = sorted(
        df_barrios_posibles["barrio"].dropna().astype(str).unique().tolist()
    ) if "barrio" in df_barrios_posibles.columns and not df_barrios_posibles["barrio"].dropna().empty else []

    with col_filtro_barrio:
        barrio_sel = st.selectbox(
            "Filtrar por barrio:",
            ["Todos los barrios"] + barrios_disponibles,
        )

    df_filtrado = df_hora.copy()

    if tipo_sel != "Todos los días":
        df_filtrado = df_filtrado[df_filtrado["tipo_dia"] == tipo_sel]

    if comuna_sel != "Todas las comunas":
        comuna_num = int(comuna_sel.replace("Comuna ", ""))
        df_filtrado = df_filtrado[df_filtrado["comuna"] == comuna_num]

    if barrio_sel != "Todos los barrios":
        df_filtrado = df_filtrado[df_filtrado["barrio"] == barrio_sel]

    if df_filtrado.empty:
        st.info(f"Todavía no hay datos disponibles para los filtros seleccionados: {tipo_sel} — {comuna_sel} — {barrio_sel}.")
    else:
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
            title=f"Disponibilidad promedio por franja horaria — {tipo_sel} — {comuna_sel} — {barrio_sel}",
            labels={"franja": "Franja horaria", "Promedio": "Cantidad promedio"},
            color_discrete_map={
                "🚲 Bicis disponibles": "#2196F3",
                "🅿️ Slots libres":      "#FF9800",
            },
            custom_data=["Métrica", "franja", "Promedio"],
        )
        fig_franja.update_traces(
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Franja horaria: %{customdata[1]}<br>"
                "Cantidad promedio: %{customdata[2]:.1f}"
                "<extra></extra>"
            )
        )
        st.plotly_chart(fig_franja, use_container_width=True)

        # KPIs de hora pico (hora real desde dim_time)
        df_por_hora = df_filtrado.groupby("hora")[
            ["free_bikes_promedio", "empty_slots_promedio"]
        ].mean().dropna(how="all")

        if df_por_hora.empty:
            st.info(f"Todavía no hay datos horarios suficientes para los filtros seleccionados: {tipo_sel} — {comuna_sel} — {barrio_sel}.")
        else:
            hora_critica_bicis = int(df_por_hora["free_bikes_promedio"].idxmin())
            hora_critica_slots = int(df_por_hora["empty_slots_promedio"].idxmin())

            col5, col6 = st.columns(2)
            col5.metric("🚲 Hora más crítica de bicis",
                        f"{hora_critica_bicis:02d}:00 hs",
                        help=f"Hora del día con menor disponibilidad de bicis — {tipo_sel} — {comuna_sel} — {barrio_sel}")
            col6.metric("🅿️ Hora más crítica de slots",
                        f"{hora_critica_slots:02d}:00 hs",
                        help=f"Hora del día con menor cantidad de slots libres — {tipo_sel} — {comuna_sel} — {barrio_sel}")

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

agrupacion_zona = st.radio(
    "Agrupar por:",
    ["Barrio", "Comuna"],
    horizontal=True,
)

if agrupacion_zona == "Barrio":
    columna_agrupacion = "barrio"
    etiqueta_eje = "Barrio"
    titulo_grafico = "Promedio de bicis disponibles por barrio (de mayor a menor)"
else:
    columna_agrupacion = "comuna"
    etiqueta_eje = "Comuna"
    titulo_grafico = "Promedio de bicis disponibles por comuna (de mayor a menor)"

df_zona = (
    df_estado.dropna(subset=[columna_agrupacion])
    .groupby(columna_agrupacion)[["free_bikes_actuales", "empty_slots_actuales"]]
    .mean()
    .reset_index()
    .sort_values("free_bikes_actuales", ascending=True)
)

if not df_zona.empty:
    if agrupacion_zona == "Comuna":
        df_zona["zona_label"] = df_zona[columna_agrupacion].astype(int).apply(lambda c: f"Comuna {c}")
    else:
        df_zona["zona_label"] = df_zona[columna_agrupacion].astype(str).str.title()

    fig_zona = px.bar(
        df_zona,
        x="free_bikes_actuales",
        y="zona_label",
        orientation="h",
        title=titulo_grafico,
        labels={
            "free_bikes_actuales": "Bicis disponibles (promedio)",
            "zona_label": etiqueta_eje,
        },
        color="free_bikes_actuales",
        color_continuous_scale="RdYlGn",
        custom_data=["zona_label", "free_bikes_actuales", "empty_slots_actuales"],
    )
    fig_zona.update_layout(yaxis={"categoryorder": "total ascending"})
    fig_zona.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "🚲 Bicis disponibles promedio: %{customdata[1]:.1f}<br>"
            "🅿️ Slots libres promedio: %{customdata[2]:.1f}"
            "<extra></extra>"
        )
    )
    st.plotly_chart(fig_zona, use_container_width=True)
else:
    st.info("Datos de zona no disponibles todavía.")

# ══════════════════════════════════════════════════════════════
# 4. PERFIL FUNCIONAL DE ESTACIONES (HISTÓRICO)
# ══════════════════════════════════════════════════════════════
st.divider()
st.header("🧭 Perfil funcional de estaciones")
st.markdown("Basado en el historial completo: proporción de tiempo en que cada estación funcionó principalmente como devolución, equilibrada o alquiler.")

if not df_perfil_estaciones.empty:
    tab_devolucion, tab_alquiler, tab_equilibrada = st.tabs([
        "⬇️ Devolución",
        "⬆️ Alquiler",
        "⚖️ Equilibradas",
    ])

    with tab_devolucion:
        st.subheader("Top 10 estaciones más aptas para devolución")
        st.markdown("Estaciones que estuvieron mayor proporción del tiempo con menos del 40% de bicicletas disponibles. Suelen tener más espacios libres para devolver que bicicletas para alquilar.")
        df_devolucion = df_perfil_estaciones.nlargest(10, "pct_tiempo_devolucion").drop(
            columns=["pct_tiempo_devolucion", "pct_tiempo_equilibrada", "pct_tiempo_alquiler", "avg_free_bikes"],
            errors="ignore",
        )
        st.dataframe(
            df_devolucion.rename(columns={
                "station_name": "Estación",
                "barrio": "Barrio",
                "comuna": "Comuna",
                "avg_free_bikes_pct": "Bicis disponibles promedio %",         
            }),
            use_container_width=True,
            hide_index=True,
        )

    with tab_alquiler:
        st.subheader("Top 10 estaciones más aptas para alquiler")
        st.markdown("Estaciones que estuvieron mayor proporción del tiempo con más del 60% de bicicletas disponibles. Suelen tener más bicicletas para alquilar que espacios libres para devolución.")
        df_alquiler = df_perfil_estaciones.nlargest(10, "pct_tiempo_alquiler").drop(
            columns=["pct_tiempo_devolucion", "pct_tiempo_equilibrada", "pct_tiempo_alquiler", "avg_free_bikes"],
            errors="ignore",
        )
        st.dataframe(
            df_alquiler.rename(columns={
                "station_name": "Estación",
                "barrio": "Barrio",
                "comuna": "Comuna",
                "avg_free_bikes_pct": "Bicis disponibles promedio %",         
            }),
            use_container_width=True,
            hide_index=True,
        )

    with tab_equilibrada:
        st.subheader("Top 10 estaciones más equilibradas")
        st.markdown("Estaciones que estuvieron mayor proporción del tiempo entre 40% y 60% de bicicletas disponibles.")
        df_equilibrada = df_perfil_estaciones.nlargest(10, "pct_tiempo_equilibrada").drop(
            columns=["pct_tiempo_devolucion", "pct_tiempo_equilibrada", "pct_tiempo_alquiler", "avg_free_bikes"],
            errors="ignore",
        )
        st.dataframe(
            df_equilibrada.rename(columns={
                "station_name": "Estación",
                "barrio": "Barrio",
                "comuna": "Comuna",
                "avg_free_bikes_pct": "Bicis disponibles promedio %",         
            }),
            use_container_width=True,
            hide_index=True,
        )
else:
    st.info("Todavía no hay suficientes datos históricos para construir el perfil funcional de estaciones.")
