import streamlit as st

from comun import formato_entero
from db import requiere_gold, run_query

st.set_page_config(page_title="CityBikes · G08", layout="wide")

st.title("CityBikes")
st.header("Saturación y disponibilidad de bicicletas públicas")
st.markdown(
    """
Pipeline medallion sobre [api.citybik.es](https://api.citybik.es/v2) para
**EcoBici (CABA)**, **Mi Bici Tu Bici (Rosario)** y **Bike Itaú Nordelta**:
Airflow toma un snapshot de cada estación cada 5 minutos (bronze), lo limpia y
valida contra el contrato (silver) y lo modela en tablas de hechos y
dimensiones (gold). Todas las páginas leen solo el schema `gold`.

| Página | Pregunta de negocio | Tabla gold |
|---|---|---|
| 1 · Sin bicis por estación | ¿Qué estaciones se quedan sin bicis y cuándo? | `fact_estacion_hora` |
| 2 · Sin bicis por zona | ¿Cómo varía el tiempo sin bicis por barrio, comuna o ciudad? | `fact_estacion_hora` |
| 3 · Duración de episodios | ¿Cuánto tarda en reponerse una estación vacía? | `fact_episodio_sin_bicis` |
| 4 · Vaciamiento y llenado | ¿Qué zonas se vacían y cuáles se llenan, y en qué horario? | `fact_estacion_hora` |
| 5 · Uso por estación | ¿Cuánto uso tiene cada estación y en qué horario? | `fact_estacion_hora` |
| 6 · Capacidad disponible | ¿Qué parte de la capacidad está realmente disponible? | `fact_capacidad_actual` |

Una estación **saturada** (o **sin bicis**) es una que no tiene bicis para
retirar (`free_bikes = 0`). La otra cara, estación llena sin anclajes libres
(`empty_slots = 0`), se ve en la página 4. Las estaciones que no alquilan o con dato del operador
viejo no cuentan como saturadas (página 6). Horarios en hora de Argentina.
"""
)

requiere_gold()

resumen = run_query("""
    SELECT
        (SELECT count(DISTINCT network_id) FROM gold.dim_estacion) AS redes,
        (SELECT count(*) FROM gold.dim_estacion) AS estaciones,
        (SELECT count(*) FROM gold.dim_fecha) AS dias,
        (SELECT coalesce(sum(snapshots_total), 0) FROM gold.fact_estacion_hora) AS observaciones,
        (SELECT max(ultima_obs) AT TIME ZONE 'America/Argentina/Buenos_Aires'
           FROM gold.dim_estacion) AS ultimo_snapshot
""").iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Redes", formato_entero(resumen["redes"]))
c2.metric("Estaciones", formato_entero(resumen["estaciones"]))
c3.metric("Días con datos", formato_entero(resumen["dias"]))
c4.metric("Observaciones estación × snapshot", formato_entero(resumen["observaciones"]))
st.caption(f"Último snapshot procesado: {resumen['ultimo_snapshot']:%d/%m/%Y %H:%M} (hora local).")
