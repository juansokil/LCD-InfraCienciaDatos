"""
Inicio del dashboard: la pregunta de negocio y los numeros clave.

Todo lo que se ve sale de las vistas gold.v_* (capa semantica de Gold).
"""

import plotly.express as px
import streamlit as st

from db import consultar, sin_datos_aun
from theme import AZUL, NARANJA, estilo

st.title("🌎 Actividad sísmica global")
st.markdown(
    "**¿Dónde se concentra la actividad sísmica, cómo evoluciona día a día y "
    "qué tan fuertes y profundos son los sismos?** Con foco en Sudamérica.  \n"
    "Datos del Servicio Geológico de EE.UU. (USGS), actualizados cada 30 minutos "
    "por un pipeline Bronze → Silver → Gold orquestado con Airflow."
)

kpis = consultar("SELECT * FROM gold.v_kpis")
if kpis.empty or not kpis.iloc[0]["sismos_total"]:
    sin_datos_aun()
    st.stop()
k = kpis.iloc[0]

st.caption(
    f"Período: **{k['desde']:%d/%m/%Y}** a **{k['hasta']:%d/%m/%Y}** (UTC) · "
    f"última actualización de USGS: **{k['ultima_actualizacion_usgs']:%d/%m/%Y %H:%M} UTC**"
)

c = st.columns(3) + st.columns(3)
c[0].metric("Sismos en el período", f"{int(k['sismos_total']):,}".replace(",", "."))
c[1].metric("Últimas 24 h", f"{int(k['sismos_24h']):,}".replace(",", "."))
c[2].metric("Magnitud ≥ 4,5", f"{int(k['sismos_m45']):,}".replace(",", "."))
c[3].metric("Magnitud ≥ 6", int(k["sismos_m6"]))
c[4].metric("Magnitud máxima", f"{float(k['magnitud_max']):.1f}")
c[5].metric("En Sudamérica", f"{int(k['sismos_sudamerica']):,}".replace(",", "."))

fuerte = consultar("SELECT * FROM gold.v_sismo_mas_fuerte")
if not fuerte.empty:
    f = fuerte.iloc[0]
    st.markdown(
        f"**El más fuerte del período:** magnitud **{float(f['magnitud']):.1f}** "
        f"({f['categoria_magnitud'].lower()}) — {f['lugar']} — "
        f"{f['ocurrido_at']:%d/%m/%Y %H:%M} UTC, a {float(f['profundidad_km']):.0f} km "
        f"de profundidad. [Ver en USGS]({f['url']})"
    )

st.divider()

diario = consultar("""
    SELECT fecha,
           sum(cantidad) AS sismos,
           sum(cantidad) FILTER (WHERE orden_magnitud >= 3) AS sismos_m4
    FROM gold.v_sismos_diarios
    -- el primer dia esta incompleto (la ventana de 30 dias de USGS arranca a
    -- mitad de un dia): mostrarlo dibujaria una caida que no existe
    WHERE fecha > (SELECT min(fecha) FROM gold.v_sismos_diarios)
    GROUP BY fecha ORDER BY fecha
""")
diario["sismos_m4"] = diario["sismos_m4"].fillna(0)

izq, der = st.columns(2)
with izq:
    fig = px.line(diario, x="fecha", y="sismos", markers=True,
                  title="Sismos por día (todas las magnitudes)",
                  labels={"fecha": "", "sismos": "sismos"})
    fig.update_traces(line=dict(color=AZUL, width=2), marker=dict(size=8))
    fig.update_traces(hovertemplate="%{x|%d/%m}<br><b>%{y}</b> sismos<extra></extra>")
    st.plotly_chart(estilo(fig), use_container_width=True)
with der:
    fig = px.bar(diario, x="fecha", y="sismos_m4",
                 title="Sismos por día de magnitud 4 o más",
                 labels={"fecha": "", "sismos_m4": "sismos M4+"})
    fig.update_traces(marker_color=NARANJA,
                      hovertemplate="%{x|%d/%m}<br><b>%{y}</b> sismos M4+<extra></extra>")
    st.plotly_chart(estilo(fig), use_container_width=True)

st.caption(
    "Los dos gráficos van separados a propósito: la mayoría de los registros son "
    "microsismos (casi todos en EE.UU., donde la red de sensores es muy densa) y "
    "taparían a los sismos que importan. El último día está en curso: todavía "
    "no está completo. Fuente: `gold.v_kpis`, `gold.v_sismos_diarios`."
)

with st.expander("¿Cómo está armado?"):
    st.markdown(
        """
        | Capa | Qué hace | Dónde queda |
        |---|---|---|
        | **Bronze** | Baja el feed GeoJSON de USGS cada 30 min (la primera vez, el último mes) y lo guarda tal cual | `data/raw/usgs/ds=AAAA-MM-DD/` + `bronze.usgs_sismos` |
        | **Silver** | Se queda con la última versión de cada sismo, tipa, valida y separa lo roto a cuarentena (SQL, upsert idempotente) | `silver.sismos`, `silver.sismos_cuarentena` |
        | **Gold** | Modelo estrella (`fact_sismo` + 5 dimensiones) y vistas `gold.v_*` | lo que lee este tablero |

        Las capas se encadenan por **Assets de Airflow 3**: Silver arranca cuando Bronze
        termina de escribir, y Gold cuando termina Silver.
        """
    )
