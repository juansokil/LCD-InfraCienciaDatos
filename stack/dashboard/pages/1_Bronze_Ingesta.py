"""
🥉 Bronze · Ingesta — ¿llegó el dato?

Bronze es la capa que toca el mundo exterior: sale a buscar a una API que
no avisa cuando hay dato nuevo. Por eso acá no se miran precios, se mira
el ACTO de ingerir: ¿llegó?, ¿a tiempo?, ¿completo?, ¿cuánto ocupa?

Bronze es append-only: nunca se borra ni se corrige. Si algo salió mal,
se arregla aguas abajo — el crudo queda como fuente de verdad.
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from db import frescura, run_query
from theme import (aplicar_tema, encabezado, kpi, seccion, aviso,
                   de_donde_sale, filtro_periodo, where_periodo,
                   frescura_pill, miles, PLOTLY, SUBE, BAJA, GRIS)

aplicar_tema("Bronze · Ingesta", "🥉")

CADENCIA_MIN = 15          # el cron de crypto_bronze: 0,15,30,45
ESPERADOS_DIA = 24 * 60 // CADENCIA_MIN   # 96 snapshots/día


# run_query ya viene cacheado desde db.py (ttl=60). Este alias queda solo
# por comodidad de lectura: `q(...)` es mas corto dentro de las paginas.
q = run_query


try:
    g = q("""
        SELECT count(*)                              AS filas,
               count(DISTINCT snapshot_ts)           AS snapshots,
               count(DISTINCT id)                    AS activos,
               min(snapshot_ts::timestamp)           AS primera,
               max(snapshot_ts::timestamp)           AS ultima,
               pg_total_relation_size('bronze.crypto_markets') AS bytes,
               -- DOS latencias distintas, y conviene no confundirlas:
               --   latencia_nuestra = cuanto tardamos en guardar lo que pedimos
               --   staleness_fuente = que tan viejo venia el dato de CoinGecko
               -- Si el numero que sube es el segundo, el problema no es el
               -- pipeline: es la fuente. Culpar al pipeline por eso es el
               -- clasico de las guardias.
               -- Bronze guarda estos campos como TEXT (es crudo a proposito:
               -- no tipa, no limpia -- eso es trabajo de Silver). Por eso los
               -- casts explicitos; el resto de la query ya lo hacia.
               EXTRACT(EPOCH FROM (max(ingested_at::timestamp)
                                   - max(snapshot_ts::timestamp)))
                   AS latencia_seg,
               EXTRACT(EPOCH FROM (max(snapshot_ts::timestamp)
                                   - max(last_updated::timestamptz AT TIME ZONE 'UTC')))
                   AS staleness_seg
        FROM bronze.crypto_markets
    """)
except Exception:
    encabezado("🥉 Bronze · Ingesta", "El dato crudo, tal como llegó de la API")
    st.info("🕐 **`bronze.crypto_markets` todavía no existe.** La primera ingesta llega en el "
            "próximo :00 / :15 / :30 / :45.")
    st.stop()

if g.empty or g.iloc[0]["filas"] == 0:
    encabezado("🥉 Bronze · Ingesta", "El dato crudo, tal como llegó de la API")
    st.info("🕐 **Bronze está vacío.** Esperá la próxima corrida de `crypto_bronze`.")
    st.stop()

b = g.iloc[0]
ultima = pd.to_datetime(b["ultima"])
lag = (pd.Timestamp.utcnow().tz_localize(None) - ultima).total_seconds() / 60

# Una sola definicion de frescura para todo el dashboard: mismos umbrales y
# misma redaccion que el home y que la pagina de Mercado. Antes cada pantalla
# armaba la suya y el mismo estado se llamaba "INGESTA AL DIA" aca y "AL DIA"
# tres clicks mas alla.
estado = frescura_pill(frescura("bronze", "crypto_markets", "snapshot_ts"))

encabezado("🥉 Bronze · Ingesta",
           "El dato crudo, tal como llegó de la API · <code>bronze.crypto_markets</code>",
           estado)

# El filtro va en UNA fila, arriba de todo lo que gobierna. Los KPIs de arriba
# son acumulados de TODA la historia a proposito (peso en disco, total
# ingestado); el rango aplica a las series de abajo.
periodo = filtro_periodo("ingesta")
st.caption("Cadencia y crecimiento de la ingesta · mostrando **"
           + periodo["etiqueta"] + "**")

# --- KPIs de ingesta -------------------------------------------------------
ancho = q("""
    SELECT count(*) AS cols FROM information_schema.columns
    WHERE table_schema = 'bronze' AND table_name = 'crypto_markets'
""").iloc[0]["cols"]

cols = st.columns(4)
cols[0].markdown(kpi("Snapshots ingestados", f"{int(b['snapshots']):,}".replace(",", "."),
                     foot=f"Cada uno trae {int(b['activos'])} activos. Bronze es append-only: "
                          "los snapshots se acumulan, nunca se pisan."),
                 unsafe_allow_html=True)
cols[1].markdown(kpi("Filas acumuladas", f"{int(b['filas']):,}".replace(",", "."),
                     foot="snapshots × activos. Crece linealmente: es el costo de tener historia."),
                 unsafe_allow_html=True)
cols[2].markdown(kpi("Ancho del payload", f"{int(ancho)} columnas",
                     foot="Todo lo que devuelve la API se guarda, aunque hoy no se use. "
                          "Mañana puede hacer falta y el crudo ya está."),
                 unsafe_allow_html=True)
cols[3].markdown(kpi("Tamaño en disco", f"{b['bytes'] / 1024 / 1024:.1f} MB",
                     foot=f"~{b['bytes'] / max(int(b['snapshots']), 1) / 1024:.0f} kB por snapshot."),
                 unsafe_allow_html=True)

# --- Cadencia: ¿el cron se está cumpliendo? --------------------------------
seccion("Cadencia real vs esperada",
        f"El cron de <code>crypto_bronze</code> es <code>0,15,30,45 * * * *</code> → "
        f"{ESPERADOS_DIA} snapshots por día completo")

por_dia = q("""
    SELECT snapshot_ts::timestamp::date AS fecha,
           count(DISTINCT snapshot_ts)  AS snapshots,
           count(*)                     AS filas
    FROM bronze.crypto_markets
    WHERE true""" + where_periodo("snapshot_ts::timestamp::date", periodo) + """
    GROUP BY 1 ORDER BY 1
""")

# El color lee la cadencia en los DOS sentidos. Antes todas las barras eran
# azules y solo el texto de abajo avisaba si faltaban: un dia con 99 de 96
# esperados se veia igual de sano que uno con 96 clavados, cuando en realidad
# es IMPOSIBLE con un cron cada 15 minutos y significa que hubo re-disparos.
AMBAR = "#c98500"


def _color_cadencia(n, es_borde):
    if es_borde:
        return GRIS          # primer y ultimo dia: arrancan/terminan a mitad
    if n > ESPERADOS_DIA:
        return AMBAR         # DE MAS: corridas repetidas
    if n >= ESPERADOS_DIA * .95:
        return SUBE          # en regla
    return BAJA              # faltaron corridas


_bordes = {0, len(por_dia) - 1}
fig = go.Figure()
fig.add_trace(go.Bar(
    x=por_dia["fecha"], y=por_dia["snapshots"], name="Ingestados",
    marker_color=[_color_cadencia(n, i in _bordes)
                  for i, n in enumerate(por_dia["snapshots"])],
    customdata=[[int(n) - ESPERADOS_DIA] for n in por_dia["snapshots"]],
    hovertemplate="%{x|%d-%b}: %{y} snapshots "
                  "(%{customdata[0]:+d} vs esperado)<extra></extra>",
))
fig.add_hline(y=ESPERADOS_DIA, line_color=GRIS, line_dash="dot", line_width=1.5,
              annotation_text=f"esperados: {ESPERADOS_DIA}/día", annotation_position="top left",
              annotation_font=dict(size=11, color=GRIS))
fig.update_layout(height=250, bargap=0.5, **PLOTLY)
st.plotly_chart(fig, use_container_width=True)

# El primer y el último día casi nunca están completos (arranca/termina a mitad).
completos = por_dia.iloc[1:-1] if len(por_dia) > 2 else pd.DataFrame()
if not completos.empty:
    cumpl = completos["snapshots"].mean() / ESPERADOS_DIA * 100
    _faltan = completos[completos["snapshots"] < ESPERADOS_DIA * .95]
    _sobran = completos[completos["snapshots"] > ESPERADOS_DIA]
    leyenda = ("🔵 en regla · 🔴 faltaron corridas · 🟠 corrió de más · "
               "⚪ día incompleto (arranca/termina a mitad)")
    if _faltan.empty and _sobran.empty:
        st.caption(f"✅ Cumplimiento del cron en días completos: **{cumpl:.0f}%**. "
                   f"El pipeline no se saltea corridas.  \n{leyenda}")
    else:
        partes = []
        if not _faltan.empty:
            partes.append(f"**{len(_faltan)} día(s) por debajo** — hubo corridas "
                          "que no ejecutaron")
        if not _sobran.empty:
            # Esto NO es un problema de Bronze: es append-only y guardar dos
            # veces el mismo snapshot es su comportamiento correcto. Pero es
            # la evidencia que le sirve a Silver, que es quien deduplica.
            partes.append(f"**{len(_sobran)} día(s) por encima de "
                          f"{ESPERADOS_DIA}** — imposible con este cron: hubo "
                          "re-disparos del DAG")
        st.caption(f"⚠️ Cumplimiento en días completos: **{cumpl:.0f}%** · "
                   + " · ".join(partes) + f".  \n{leyenda}")
else:
    st.caption(f"📅 Con **{len(por_dia)} {'día' if len(por_dia) == 1 else 'días'}** todavía no hay un día "
               "completo para medir cumplimiento (el primero y el último arrancan/terminan a mitad).")

# --- Re-ingestas: el mismo snapshot, guardado dos veces --------------------
# Bronze NO deduplica, y esta bien que no lo haga: es append-only y el crudo
# es la evidencia de lo que devolvio la API. Pero el que consume aguas abajo
# tiene que SABER que estan, porque es su trabajo resolverlas.
reing = q("""
    SELECT count(*) - count(DISTINCT (id, snapshot_ts)) AS repetidas,
           count(*)                                     AS filas
    FROM bronze.crypto_markets
""").iloc[0]
_rep = int(reing["repetidas"])
if _rep:
    aviso(
        f"<b>{miles(_rep)} filas son re-ingestas</b>: el mismo "
        "<code>(activo, snapshot_ts)</code> guardado más de una vez, porque "
        "el DAG se disparó dos veces para ese minuto.<br><br>"
        "<b>Bronze las guarda a propósito y no es un error.</b> Es "
        "append-only: el crudo es la evidencia de qué devolvió la API, y "
        "borrar acá sería destruir esa evidencia. Quien deduplica es "
        "<b>Silver</b>, con <code>DISTINCT ON (id, snapshot_ts)</code>.<br><br>"
        "Pero conviene mirarlas: una re-ingesta aguas arriba es lo que "
        "revienta la idempotencia aguas abajo si la capa siguiente no la "
        "maneja bien.",
        "♻️",
    )

# --- Pulso por hora --------------------------------------------------------
seccion("Pulso de las últimas 24 horas", "Cada barra es una hora: ¿entraron los 4 snapshots?")
por_hora = q("""
    SELECT date_trunc('hour', snapshot_ts::timestamp) AS hora,
           count(DISTINCT snapshot_ts)               AS snapshots
    FROM bronze.crypto_markets
    WHERE snapshot_ts::timestamp > now() - interval '24 hours'
    GROUP BY 1 ORDER BY 1
""")
if por_hora.empty:
    st.caption("Sin ingestas en las últimas 24 horas.")
else:
    esperado_hora = 60 // CADENCIA_MIN
    figh = go.Figure(go.Bar(
        x=por_hora["hora"], y=por_hora["snapshots"],
        marker=dict(color=[SUBE if s >= esperado_hora else BAJA for s in por_hora["snapshots"]]),
        hovertemplate="%{x|%d-%b %H:%M}: %{y} de " + str(esperado_hora) + "<extra></extra>",
    ))
    figh.add_hline(y=esperado_hora, line_color=GRIS, line_dash="dot", line_width=1)
    figh.update_layout(height=190, bargap=0.35, **PLOTLY)
    st.plotly_chart(figh, use_container_width=True)
    faltantes = int((por_hora["snapshots"] < esperado_hora).sum())
    if faltantes:
        st.caption(f"🔴 **{faltantes} hora(s)** con menos de {esperado_hora} snapshots. "
                   "Puede ser rate-limit de la API o una corrida fallida.")

# --- Crecimiento y proyección ---------------------------------------------
seccion("Crecimiento", "Bronze nunca borra: ¿cuánto va a pesar en el cuatrimestre?")
c1, c2 = st.columns([1.4, 1])

with c1:
    acum = por_dia.copy()
    acum["acumulado"] = acum["filas"].cumsum()
    figc = go.Figure(go.Scatter(
        x=acum["fecha"], y=acum["acumulado"], mode="lines+markers",
        line=dict(color=SUBE, width=2), fill="tozeroy",
        fillcolor="rgba(57,135,229,.15)",
        hovertemplate="%{x|%d-%b}: %{y:,.0f} filas acumuladas<extra></extra>",
    ))
    figc.update_layout(height=230, **PLOTLY)
    st.plotly_chart(figc, use_container_width=True)

with c2:
    dias = max(len(por_dia), 1)
    filas_dia = b["filas"] / dias
    mb_dia = b["bytes"] / 1024 / 1024 / dias
    st.markdown(kpi("Proyección a 4 meses",
                    f"{mb_dia * 120:.0f} MB",
                    foot=f"A razón de ~{filas_dia:,.0f} filas/día. ".replace(",", ".") +
                         "Guardar el crudo es barato; perderlo, caro: sin Bronze no se puede "
                         "reprocesar Silver ni Gold si mañana cambia la lógica."),
                unsafe_allow_html=True)

# --- Últimos snapshots -----------------------------------------------------
seccion("Últimas ingestas", "Las 10 corridas más recientes, tal como quedaron en la tabla")
ultimos = q("""
    SELECT snapshot_ts::timestamp AS snapshot,
           count(*)               AS activos,
           min(ingested_at::timestamp) AS ingestado
    FROM bronze.crypto_markets
    GROUP BY 1 ORDER BY 1 DESC LIMIT 10
""")
ultimos["demora_seg"] = (pd.to_datetime(ultimos["ingestado"]) -
                         pd.to_datetime(ultimos["snapshot"])).dt.total_seconds()
st.dataframe(
    ultimos, hide_index=True, use_container_width=True,
    column_config={
        "snapshot": st.column_config.DatetimeColumn("Snapshot", format="YYYY-MM-DD HH:mm"),
        "activos": st.column_config.NumberColumn("Activos", help="Cuántas criptos trajo esa corrida"),
        "ingestado": st.column_config.DatetimeColumn("Escrito en Bronze", format="HH:mm:ss"),
        "demora_seg": st.column_config.NumberColumn("Demora (s)", format="%.0f",
                                                    help="Entre la marca del snapshot y la escritura"),
    },
)

aviso(
    "<b>Por qué Bronze guarda todo y no corrige nada.</b> Si la API devuelve un precio raro, "
    "Bronze lo guarda igual: es el <b>crudo</b>. Limpiar acá significaría perder para siempre "
    "la evidencia de qué mandó la fuente. La validación ocurre en <b>Silver</b>, donde los "
    "registros que no cumplen el contrato van a cuarentena — separados, no borrados.",
    "🥉",
)

# --- Las dos latencias -----------------------------------------------------
seccion("¿Quién tarda?", "Separar nuestra demora de la demora de la fuente")

lat = b.get("latencia_seg")
stale = b.get("staleness_seg")
la, lb = st.columns(2)
la.markdown(
    kpi("Nuestra latencia",
        f"{lat:.0f} s" if lat is not None and lat == lat else "—",
        foot="De <code>snapshot_ts</code> (cuándo pedimos) a <code>ingested_at</code> "
             "(cuándo quedó escrito). Es lo único que está en nuestras manos."),
    unsafe_allow_html=True,
)
lb.markdown(
    kpi("Antigüedad en origen",
        f"{stale / 60:.1f} min" if stale is not None and stale == stale else "—",
        foot="Cuánto hacía que CoinGecko había actualizado ese dato cuando se lo "
             "pedimos (<code>last_updated</code>). Esto NO lo controlamos."),
    unsafe_allow_html=True,
)
aviso(
    "<b>Un dato puede estar recién ingestado y ser viejo igual.</b> Si nuestra "
    "latencia es de segundos pero la fuente venía con minutos de atraso, el "
    "número que llega a Gold ya nació desactualizado — y ninguna métrica de "
    "pipeline lo muestra. Por eso se miden las dos por separado: cuando alguien "
    "dice «el dashboard está atrasado», estas dos tarjetas dicen de quién es.",
    "⏱️",
)

de_donde_sale("gold.v_ultimo_snapshot",
              "Bronze no tiene vistas — es crudo a propósito. Esta es la primera "
              "vista de la cadena, para ver a dónde va a parar lo que entra acá.")
