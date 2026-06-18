import streamlit as st
import pandas as pd
import psycopg2
import plotly.express as px

# Configuración de la página secundaria
st.set_page_config(page_title="Análisis de Turismo", page_icon="📊", layout="wide")

st.title("📊 Reporte de Insights Climáticos para Turismo")
st.markdown("Análisis de patrones sobre los últimos 3 meses de datos acumulados.")

# --- CONEXIÓN A LA BASE DE DATOS ---
# Usamos las credenciales exactas del contenedor 'warehouse' definido en tu docker-compose
DB_CONFIG = "dbname=weather_data user=admin password=admin123 host=warehouse port=5432"

@st.cache_data(ttl=600)  # Caché de 10 minutos para no saturar Postgres
def ejecutar_query(query):
    """Función auxiliar para conectar a la DB y devolver un DataFrame"""
    conn = psycopg2.connect(DB_CONFIG)
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# --- CONTROL DE EXCEPCIONES POR SI AIRFLOW TODAVÍA NO CARGÓ DATOS ---
try:
    # --- 1. DATOS PREVIOS: Extracción de meses y nombres para visualizaciones ---
    # Traemos todo el histórico consolidado en Gold mapeado con su respectiva ciudad
    query_base = """
        SELECT 
            f.fecha,
            EXTRACT(MONTH FROM f.fecha) as mes_num,
            TO_CHAR(f.fecha, 'TMMonth') as mes_nombre,
            c.ciudad,
            f.temp_promedio,
            f.temp_max,
            f.temp_min,
            f.lluvia_acumulada,
            f.viento_promedio
        FROM gold.fact_clima_real f
        JOIN gold.dim_ciudad c ON f.ciudad_id = c.id;
    """
    df_clima = ejecutar_query(query_base)
    
    # Convertimos el número de mes a entero y ordenamos cronológicamente para los gráficos
    df_clima['mes_num'] = df_clima['mes_num'].astype(int)
    df_clima = df_clima.sort_values(by=['mes_num'])

    # =========================================================================
    # METRICA 1: Patrón mensual en las lluvias acumuladas por ciudad
    # =========================================================================
    st.subheader("1. 🌧️ Hay algún Patron en base a las Precipitaciones?")
    st.write("Suma de lluvia acumulada por mes y por ciudad para identificar épocas de lluvias intensas.\n\n-> Uso práctico: Hacer énfasis en actividades internas, como museos, shoppings, edificios historicos y demás, durante estos períodos")
    
    # Agrupamos por ciudad y mes_nombre manteniendo el número de mes para ordenar la gráfica
    df_lluvias = df_clima.groupby(['ciudad', 'mes_num', 'mes_nombre'])['lluvia_acumulada'].sum().reset_index()
    
    # Gráfico de líneas solicitado: x=meses, y=lluvia acumulada, color=ciudad
    fig_lluvias = px.line(
        df_lluvias, 
        x="mes_nombre", 
        y="lluvia_acumulada", 
        color="ciudad",
        title="Evolución Mensual de Lluvias Acumuladas (mm)",
        labels={"mes_nombre": "Mes", "lluvia_acumulada": "Lluvia Total (mm)", "ciudad": "Ciudad"},
        markers=True
    )
    st.plotly_chart(fig_lluvias, use_container_width=True)
    
    st.markdown("---")

    # =========================================================================
    # METRICA 2: Ciudades con mayor variabilidad térmica diaria
    # =========================================================================
    st.subheader("2. 🌡️ Ciudades con Mayor Variabilidad Térmica Diaria")
    st.write("Promedio de la diferencia diaria entre temperatura máxima y mínima.\n\n-> Ayuda a saber en qué ciudades prestar atención a la hora de recomendar vestimenta apropiada, como en capas, y así evitar resfrios que perjudiquen la experiencia e itinerario.")
    
    # 1. Calculamos la variabilidad de cada día individual
    df_clima['variabilidad_diaria'] = df_clima['temp_max'] - df_clima['temp_min']
    
    # 2. Creamos un orden de ciudades basado en su variabilidad promedio total (los 3 meses juntos)
    # Agrupamos solo por ciudad, sacamos el promedio, y ordenamos de mayor a menor
    orden_ciudades = (
        df_clima.groupby('ciudad')['variabilidad_diaria']
        .mean()
        .sort_values(ascending=False)
        .index
    )
    
    # 3. Calculamos el promedio mensual de esa variabilidad por ciudad y por mes para la tabla
    df_var = df_clima.groupby(['ciudad', 'mes_nombre'])['variabilidad_diaria'].mean().reset_index()
    
    # 4. Pivotamos el DataFrame: filas=ciudad, columnas=meses
    df_var_pivot = df_var.pivot(index='ciudad', columns='mes_nombre', values='variabilidad_diaria')
    
    # 5. Aplicamos el orden jerárquico que calculamos en el paso 2 usando .reindex()
    df_var_pivot = df_var_pivot.reindex(orden_ciudades)
    
    # Mostramos la tabla ordenada y formateada con un decimal
    st.dataframe(df_var_pivot.style.format("{:.1f} °C"), use_container_width=True)
    
    st.markdown("---")

    # =========================================================================
    # METRICA 3: Días ideales para recorrer sin lluvia (Días Lindos)
    # =========================================================================
    st.subheader("3. ☀️ Días Ideales para Recorrer (Sin Lluvia)")
    st.write("Cantidad de días por mes en los que la lluvia acumulada fue de 0 mm.\n\n-> Ayuda a considerar con cuanto tiempo óptimo contamos para recorrer al aire libre")
    
    # Creamos una bandera: 1 si no llovió, 0 si llovió
    df_clima['dia_lindo'] = df_clima['lluvia_acumulada'].apply(lambda x: 1 if x == 0 else 0)
    
    # Sumamos los días lindos agrupando por ciudad y mes
    df_dias_lindos = df_clima.groupby(['ciudad', 'mes_num', 'mes_nombre'])['dia_lindo'].sum().reset_index()
    
    # Gráfico de barras: x=ciudad, y=días lindos, color (barras agrupadas/separadas) = mes
    fig_lindos = px.bar(
        df_dias_lindos,
        x="ciudad",
        y="dia_lindo",
        color="mes_nombre",
        barmode="group",
        title="Cantidad de Días sin Lluvia por Mes",
        labels={"ciudad": "Ciudad", "dia_lindo": "Días Sin Lluvia", "mes_nombre": "Mes"}
    )
    st.plotly_chart(fig_lindos, use_container_width=True)
    
    st.markdown("---")

    # =========================================================================
    # METRICA 4: Top ciudades con peores condiciones en esta temporada
    # =========================================================================
    st.subheader("4. ⚠️ Top Ciudades con Peores Condiciones Climáticas")
    st.write("Ranking de ciudades basado en la cantidad de **Días Feos** acumulados\n\n-> Días Feos = (Lluvia > 2mm Y Viento promedio > 12 km/h).\n\n-> Nos brinda un detalle clave a considerar a la hora de ofrecer viajes")
    
    # Determinamos si el día cumple los criterios de "Día Feo" de negocio
    def es_dia_feo(row):
        # Lluvia mayor a 2mm Y viento promedio mayor a 12 km/h
        return 1 if (row['lluvia_acumulada'] > 2.0 and row['viento_promedio'] > 12.0) else 0
        
    df_clima['dia_feo'] = df_clima.apply(es_dia_feo, axis=1)
    
    # Totalizamos la cantidad de días feos en toda la temporada (los 3 meses analizados)
    df_peores = df_clima.groupby('ciudad')['dia_feo'].sum().reset_index()
    df_peores = df_peores.sort_values(by='dia_feo', ascending=False)
    
    # Presentación en formato de Lista/Métricas visuales
    st.write("Ciudades ordenadas de peor a mejor condición climática actual:")
    
    for idx, row in df_peores.iterrows():
        # Usamos st.metric o un formato de alerta para destacar el podio de días feos
        cant_dias = int(row['dia_feo'])
        if cant_dias > 0:
            st.error(f"🚨 **{row['ciudad']}**: {cant_dias} días registrados con tormenta y vientos fuertes.")
        else:
            st.success(f"✅ **{row['ciudad']}**: 0 días con condiciones extremas en este período.")

except Exception as error_db:
    # Control de entorno por si las tablas están vacías al levantar por primera vez el stack
    st.warning("⚡ Esperando la sincronización de datos...")
    st.info("Asegurate de que los DAGs de Airflow (`weather_bronze_pipeline` -> `silver` -> `gold`) hayan completado al menos una corrida exitosa.")
    st.error(f"Detalle del error técnico: {error_db}")