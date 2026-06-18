"""
Aplicación Analítica - Dashboard EcoBici BA.
Capa de consumo (Serving Layer) que expone los KPIs y el mapa
interactivo consumiendo directamente el modelo estrella de la capa Gold.
"""
import streamlit as st
import pandas as pd
import sqlalchemy
import plotly.express as px

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Dashboard EcoBici BA - Capa Gold",
    page_icon="🚲",
    layout="wide"
)

# URI de conexión al contenedor Postgres mapeado en la red interna de Docker
DB_URI = "postgresql://admin:admin@data_warehouse:5432/InfraCienciaDatos"

@st.cache_data(ttl=60)
def get_gold_metrics():
    """Extrae las métricas unificadas haciendo un JOIN rápido del Star Schema."""
    engine = sqlalchemy.create_engine(DB_URI)
    query = """
        SELECT 
            f.fact_key,
            f.bikes_available,
            f.slots_available,
            f.occupancy_ratio,
            s.station_name,
            s.address,
            s.total_capacity,
            s.latitude,
            s.longitude,
            t.full_timestamp,
            t.hour,
            t.day_of_week,
            t.is_weekend
        FROM gold.fact_station_availability f
        JOIN gold.dim_station s ON f.station_id = s.station_id
        JOIN gold.dim_time t ON f.time_id = t.time_id
        ORDER BY t.full_timestamp DESC;
    """
    df = pd.read_sql(query, con=engine)
    if not df.empty:
        df["full_timestamp"] = pd.to_datetime(df["full_timestamp"])
    return df

# --- TÍTULO PRINCIPAL ---
st.title("🚲 Sistema Analítico EcoBici Buenos Aires")
st.markdown("### `Etapa Final: Consumo de la Capa Gold (Star Schema)`")
st.write("Visualización en tiempo real y tendencias del estado de disponibilidad de la red.")

# Carga de datos
with st.spinner("Conectando con el Data Warehouse (Esquema Gold)..."):
    df_gold = get_gold_metrics()

if df_gold.empty:
    st.warning("⚠️ No se encontraron snapshots de datos en la capa gold. Asegurate de que el DAG 'gold_ecobici' haya corrido en Airflow.")
else:
    # --- FILTROS EN BARRA LATERAL ---
    st.sidebar.header("Filtros de Análisis")
    filtro_dia = st.sidebar.multiselect(
        "Seleccionar Día de la Semana",
        options=["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        default=["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    )
    
    # Aplicar filtros
    df_filtrado = df_gold[df_gold["day_of_week"].isin(filtro_dia)]
    
    # Obtener el último snapshot para las métricas e indicadores actuales
    ultimo_timestamp = df_filtrado["full_timestamp"].max()
    df_actual = df_filtrado[df_filtrado["full_timestamp"] == ultimo_timestamp]

    # --- FILA 1: MÉTRICAS GENERALES EN SNAPSHOT ---
    st.markdown(f"#### 📊 Estado de la Red al: `{ultimo_timestamp}`")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(label="📍 Estaciones Activas", value=int(df_actual["station_name"].nunique()))
    with col2:
        st.metric(label="🚲 Bicicletas Disponibles", value=int(df_actual["bikes_available"].sum()))
    with col3:
        st.metric(label="🔒 Anclajes Libres", value=int(df_actual["slots_available"].sum()))
    with col4:
        ratio_promedio = df_actual["occupancy_ratio"].mean() * 100
        st.metric(label="📈 Ocupación Promedio", value=f"{ratio_promedio:.1f}%")

    st.markdown("---")

    # --- FILA 2: MAPA GEOGRÁFICO INTERACTIVO ---
    st.subheader("🗺️ Distribución Espacial y Saturación de Estaciones")
    st.write("El tamaño y color de los puntos representan la capacidad total y la tasa de ocupación actual.")
    
    # Renombrar temporalmente columnas para que Streamlit o Plotly las mapeen sin problemas
    df_mapa = df_actual.copy()
    
    fig_mapa = px.scatter_mapbox(
        df_mapa,
        lat="latitude",
        lon="longitude",
        color="occupancy_ratio",
        size="total_capacity",
        color_continuous_scale=px.colors.cyclical.IceFire,
        size_max=15,
        zoom=11.5,
        mapbox_style="carto-positron",
        hover_name="station_name",
        hover_data={"address": True, "bikes_available": True, "slots_available": True, "latitude": False, "longitude": False},
        labels={"occupancy_ratio": "Ratio de Ocupación"}
    )
    fig_mapa.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig_mapa, use_container_width=True)

    st.markdown("---")

    # --- FILA 3: ANÁLISIS TEMPORAL (HORAS PICO) ---
    st.subheader("⏳ Tendencia Temporal de Disponibilidad por Hora")
    st.write("Análisis agregado del comportamiento de la red por franja horaria.")
    
    # Agrupamos por hora para ver la fluctuación promedio del inventario
    df_hourly = df_filtrado.groupby("hour")[["bikes_available", "slots_available"]].mean().reset_index()
    
    fig_lineas = px.line(
        df_hourly,
        x="hour",
        y=["bikes_available", "slots_available"],
        labels={"hour": "Hora del Día", "value": "Cantidad Promedio (Unidades)", "variable": "Métrica"},
        title="Fluctuación de Bicicletas vs Anclajes Libres",
        markers=True
    )
    fig_lineas.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1))
    st.plotly_chart(fig_lineas, use_container_width=True)