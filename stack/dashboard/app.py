"""
Home del dashboard del curso.

Cada página responde UNA pregunta y consume las vistas de la capa semántica
de Gold (gold.v_*). Las tablas físicas son del pipeline; las vistas son la
API pública hacia el consumo.

El home, además, responde la pregunta previa a todas: **¿anda el pipeline?**
Ese estado se lee de la metadata de Airflow, no se decora.
"""

import pandas as pd
import streamlit as st

from db import estado_pipeline, eventos_asset, frescura
from theme import aplicar_tema, aviso, frescura_pill, pill, seccion

aplicar_tema("Dashboard del curso", "📈")

st.markdown(
    "<h1 style='margin-bottom:4px'>Pipeline crypto · Capa Gold</h1>"
    "<div style='color:var(--ink-3);font-size:14px;max-width:62ch'>"
    "Dashboard del curso de Infraestructura para Ciencia de Datos. Los datos llegan "
    "solos: <b>bronze cada 15 min</b>, y de ahí en cadena — silver arranca cuando "
    "bronze termina, gold cuando termina silver. Nadie toca nada.</div>",
    unsafe_allow_html=True,
)

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

# =============================================================================
# ESTADO REAL DE LA CADENA
# =============================================================================
# Antes acá había tres pills verdes fijas que decían "todo arriba" pasara lo que
# pasara. Un tablero de salud que no puede ponerse en rojo no es un tablero de
# salud: es un adorno. Esto sale de `dag_run` en la metadata de Airflow.
seccion("¿Anda el pipeline?", "El nivel de infraestructura, leído de Airflow")

ESTADOS = {
    "success": ("--up", "OK"),
    "running": ("--accent", "corriendo"),
    "failed": ("--down", "FALLÓ"),
    "queued": ("--ink-3", "en cola"),
}
ETAPAS = {
    "crypto_bronze": ("🥉", "Bronze"),
    "crypto_silver": ("🥈", "Silver"),
    "crypto_gold": ("🥇", "Gold"),
    "crypto_ml": ("🤖", "ML"),
}

dags = estado_pipeline()

if dags.empty:
    aviso(
        "<b>No puedo leer la metadata de Airflow.</b> El dashboard sigue "
        "mostrando los datos que ya están en el warehouse — son dos "
        "preguntas distintas: <i>¿hay datos?</i> y <i>¿se están "
        "actualizando?</i>. Si Airflow está caído, lo que ves abajo puede "
        "estar viejo sin que nada se vea roto.",
        "🔌",
    )
else:
    cols = st.columns(len(dags))
    for col, (_, r) in zip(cols, dags.iterrows()):
        icono, nombre = ETAPAS.get(r["dag_id"], ("⚙️", r["dag_id"]))
        color, texto = ESTADOS.get(r["estado"], ("--ink-3", str(r["estado"])))
        if r["pausado"]:
            color, texto = "--ink-3", "PAUSADO"
        ultima = (pd.Timestamp(r["ultima"]).strftime("%H:%M")
                  if pd.notna(r["ultima"]) else "nunca")
        fallidas = int(r["fallidas"] or 0)
        nota = f"{int(r['corridas'] or 0)} corridas"
        if fallidas:
            nota += f" · {fallidas} fallidas"
        col.markdown(
            f"<div class='kpi'>"
            f"<div class='lab'>{icono} {nombre}</div>"
            f"<div class='val' style='font-size:17px;color:var({color})'>{texto}</div>"
            f"<div class='chg'>última {ultima}</div>"
            f"<div class='foot'>{nota}</div></div>",
            unsafe_allow_html=True,
        )

    # Frescura del dato + evidencia de que el encadenado por asset está vivo.
    fresco = frescura("bronze", "crypto_markets", "snapshot_ts")
    eventos = eventos_asset(24)
    c1, c2 = st.columns([1, 2])
    c1.markdown(frescura_pill(fresco), unsafe_allow_html=True)
    c2.markdown(
        pill(f"{eventos} assets publicados", "--up", "últimas 24 h")
        if eventos else
        pill("sin assets en 24 h", "--down", "la cadena no se está disparando"),
        unsafe_allow_html=True,
    )
    st.caption(
        "Los DAGs de Silver, Gold y ML **no tienen cron**: arrancan cuando el "
        "anterior publica su asset. Si ese contador está en cero, la cadena no "
        "se está encadenando — aunque los DAGs figuren en verde."
    )

st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)

# =============================================================================
# LAS PÁGINAS
# =============================================================================
# Esta lista tiene que coincidir con lo que hay en `pages/`. No es decorativo:
# es lo primero que ve quien abre el tablero, y una tarjeta que promete algo
# que no existe (o que describe una pagina que ya cambio) hace perder tiempo
# antes de mostrar un solo dato.
PAGINAS = [
    ("🥉", "Bronze · Ingesta", "¿Llegó el dato?",
     "Cadencia real contra la esperada — y también cuando corre de MÁS —, "
     "re-ingestas, frescura y peso del crudo. Acá no se miran precios: se "
     "mira el acto de ingerir."),
    ("🥈", "Silver · Calidad", "¿Sirve el dato?",
     "Los invariantes del modelo verificados contra la base, el embudo "
     "Bronze→Silver→cuarentena, el contrato que se aplica y la trazabilidad "
     "que agrega la capa."),
    ("🥇", "Gold · Mercado", "¿Qué dice el negocio?",
     "El mismo 24 h calculado por la API y por vos, uno al lado del otro. "
     "Más KPIs del momento, mapa de capitalización y ranking."),
    ("🥇", "Gold · Velas", "¿Cómo se movió el mercado?",
     "La vela del mercado entero, y la de cada activo: apertura, máximo, "
     "mínimo y cierre por día, armados desde los snapshots."),
    ("🥇", "Gold · Análisis", "¿Qué estructura hay detrás?",
     "Riesgo contra retorno, correlación intradía, concentración — y el star "
     "schema funcionando: la misma pregunta cortada por dos dimensiones."),
    ("🤖", "Gold · ML", "¿El modelo sirve?",
     "El veredicto primero: el modelo contra las dos varas, la fácil y la "
     "difícil. Debajo, la maquinaria (ABT, MLflow, champion, predicciones)."),
]

st.markdown(
    "<div style='color:var(--ink-3);font-size:12.5px;font-family:\"IBM Plex Mono\",monospace;"
    "letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px'>"
    "Recorré el pipeline capa por capa</div>", unsafe_allow_html=True,
)

cols = st.columns(3)
for i, (icono, nombre, pregunta, detalle) in enumerate(PAGINAS):
    with cols[i % 3]:
        st.markdown(
            f"<div class='kpi' style='margin-bottom:14px'>"
            f"<div style='font-size:20px;line-height:1'>{icono}</div>"
            f"<div class='val' style='font-size:16px;font-family:Archivo,sans-serif;margin-top:8px'>{nombre}</div>"
            f"<div style='color:var(--ink-2);font-size:12.5px;margin-top:3px'>{pregunta}</div>"
            f"<div class='foot'>{detalle}</div></div>",
            unsafe_allow_html=True,
        )

# =============================================================================
# CÓMO ESTÁ ARMADO
# =============================================================================
seccion("Cómo está armado", "De la API a la pantalla, sin intervención manual")

# Streamlit no renderiza mermaid y no hay componente instalado en la imagen:
# antes esto era un bloque ```mermaid que se veía como código plano. Una cadena
# de 4 eslabones no necesita un motor de diagramas.
st.markdown(
    "<div class='tbl-wrap' style='padding:18px 16px;background:var(--surface);"
    "border:1px solid var(--line);border-radius:10px'>"
    "<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;"
    "font-family:\"IBM Plex Mono\",monospace;font-size:12.5px;color:var(--ink-2)'>"
    "<span style='color:var(--ink)'>📡 CoinGecko</span>"
    "<span style='color:var(--ink-3)'>— ⏰ cron 15′ →</span>"
    "<span style='color:var(--ink)'>🥉 bronze</span>"
    "<span style='color:var(--ink-3)'>— 📦 asset →</span>"
    "<span style='color:var(--ink)'>🥈 silver</span>"
    "<span style='color:var(--ink-3)'>— 📦 asset →</span>"
    "<span style='color:var(--ink)'>🥇 gold</span>"
    "<span style='color:var(--ink-3)'>— 📦 asset →</span>"
    "<span style='color:var(--ink)'>🤖 ml</span>"
    "</div>"
    "<div style='margin-top:12px;color:var(--ink-3);font-size:12px'>"
    "Un solo reloj, y está en el borde: CoinGecko no avisa cuándo hay dato nuevo. "
    "De ahí en adelante cada capa arranca porque la anterior <b>terminó de "
    "escribir</b>, no porque sean y cinco."
    "</div></div>",
    unsafe_allow_html=True,
)

aviso(
    "<b>Los KPIs se definen una sola vez, en SQL.</b> Viven en las vistas "
    "<code>gold.v_*</code> dentro del warehouse, y cada página los lee. Si un "
    "número está mal, se corrige ahí y queda corregido para todos los "
    "consumidores a la vez — ese es el sentido de una <b>capa semántica</b>. "
    "En cada pantalla vas a encontrar un <code>🔍 ¿De dónde sale esto?</code> "
    "con el SELECT real de la vista que la alimenta.",
    "🔭",
)
