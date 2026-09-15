"""
🥈 Silver · Calidad — ¿sirve el dato?

Silver no agrega datos: agrega CONFIANZA. Toma el crudo de Bronze, lo
valida contra un contrato explícito y separa lo que no cumple (cuarentena).

La pregunta de esta capa no es "¿cuánto vale Bitcoin?" sino
"¿puedo creerle a este número?".
"""

import pandas as pd
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go
from db import run_query
from theme import (aplicar_tema, encabezado, pill, kpi, seccion, aviso,
                   de_donde_sale, layout, PLOTLY, SUBE, BAJA, GRIS, SERIES)

aplicar_tema("Silver · Calidad", "🥈")

CONTRATO = Path("/app/contracts/crypto_markets.yaml")

_TEXTO_REGLA = {
    "not_null": "no admite nulos",
    "unique": "sin duplicados",
    "positive": "tiene que ser positivo",
    "non_negative": "no puede ser negativo",
}


@st.cache_data(ttl=300)
def reglas_del_contrato():
    """Las reglas VIGENTES, leídas del YAML que aplica el DAG de Silver.

    Devuelve ``(html, version)``. Si el contrato no está montado, lo dice en
    vez de inventar: una página que no puede leer el contrato no debería
    fingir que lo conoce.
    """
    try:
        import yaml
        c = yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))
    except Exception:
        return ("<span style='color:var(--ink-3)'>No pude leer el contrato "
                "(<code>/app/contracts/</code> no está montado).</span>", "")
    filas = []
    for r in c.get("quality_rules", []) or []:
        que = _TEXTO_REGLA.get(r.get("rule"), r.get("rule", "?"))
        filas.append(
            f"<span style='color:var(--up)'>✓</span> "
            f"<code>{r.get('column')}</code> {que}<br>"
        )
    if not filas:
        filas.append("<span style='color:var(--ink-3)'>El contrato no declara "
                     "reglas de calidad.</span>")
    ver = c.get("version")
    return "".join(filas), (f" · v{ver}" if ver else "")




# run_query ya viene cacheado desde db.py (ttl=60). Este alias queda solo
# por comodidad de lectura: `q(...)` es mas corto dentro de las paginas.
q = run_query


try:
    conteos = q("""
        SELECT (SELECT count(*) FROM bronze.crypto_markets) AS bronze,
               (SELECT count(*) FROM silver.crypto_markets) AS silver,
               (SELECT to_regclass('silver.quarantine_crypto_markets') IS NOT NULL) AS hay_cuarentena
    """)
except Exception:
    encabezado("🥈 Silver · Calidad", "El dato validado contra un contrato")
    st.info("🕐 **`silver.crypto_markets` todavía no existe.** Lo escribe `crypto_silver`, "
            "que arranca solo apenas `crypto_bronze` termina de ingestar.")
    st.stop()

c = conteos.iloc[0]
if c["silver"] == 0:
    encabezado("🥈 Silver · Calidad", "El dato validado contra un contrato")
    st.info("🕐 **Silver está vacío.** Esperá la próxima corrida de `crypto_silver`.")
    st.stop()

rechazados = 0
if c["hay_cuarentena"]:
    rechazados = int(q("SELECT count(*) AS n FROM silver.quarantine_crypto_markets").iloc[0]["n"])

procesados = int(c["silver"]) + rechazados
tasa = rechazados / procesados * 100 if procesados else 0
estado = pill("SIN RECHAZOS", "--up", "la fuente viene limpia") if rechazados == 0 \
    else pill(f"{tasa:.1f}% RECHAZADO", "--down", f"{rechazados} registros")

encabezado("🥈 Silver · Calidad",
           "El dato validado contra un contrato · <code>silver.crypto_markets</code>", estado)

# --- El embudo -------------------------------------------------------------
seccion("El embudo de calidad", "De lo que llegó, ¿cuánto pasó la validación?")

cols = st.columns(4)
cols[0].markdown(kpi("Bronze (crudo)", f"{int(c['bronze']):,}".replace(",", "."),
                     foot="Todo lo que devolvió la API, sin filtrar."), unsafe_allow_html=True)
cols[1].markdown(kpi("Silver (válido)", f"{int(c['silver']):,}".replace(",", "."),
                     foot="Pasó el contrato: tipos correctos y reglas de negocio cumplidas."),
                 unsafe_allow_html=True)
cols[2].markdown(kpi("Cuarentena", f"{rechazados:,}".replace(",", "."),
                     foot="Rechazados. NO se borran: se guardan aparte con el motivo, "
                          "para poder auditarlos y reprocesarlos."), unsafe_allow_html=True)
cols[3].markdown(kpi("Tasa de rechazo", f"{tasa:.2f} %",
                     foot="El número a vigilar. Un salto acá suele avisar que la fuente "
                          "cambió algo, antes de que se note en Gold."), unsafe_allow_html=True)

# Bronze y Silver casi nunca dan el mismo numero, y el hueco NO es rechazo.
# Silver deduplica: `read_bronze` hace DISTINCT ON (id, snapshot_ts) porque una
# reingesta del mismo minuto trae las mismas 50 criptas otra vez. Ese trabajo no
# se reportaba en ningun lado y dejaba un hueco sin explicar -- que es
# exactamente lo que hace desconfiar de un tablero: no el numero feo, el numero
# que no cierra.
dedup = int(c["bronze"]) - int(c["silver"]) - rechazados
if dedup > 0:
    aviso(
        f"<b>Bronze tiene {int(c['bronze']):,} filas y Silver {int(c['silver']):,}: "
        f"faltan {dedup:,}.</b> No son rechazos — son <b>duplicados</b> que Silver "
        "descartó. Bronze ingesta <i>todo lo que llega</i> (si un DAG se re-dispara, "
        "el mismo snapshot entra dos veces); Silver se queda con una fila por "
        "<code>(id, snapshot_ts)</code> usando <code>DISTINCT ON</code>.<br><br>"
        "Las dos cosas son correctas y a propósito: Bronze es <b>append-only e "
        "inmutable</b> (es la evidencia de qué devolvió la API), y la limpieza "
        "ocurre después. Por eso se deduplica en Silver y no borrando en Bronze."
        .replace(",", "."),
        "🧹",
    )

if not c["hay_cuarentena"]:
    aviso(
        "<b>La tabla de cuarentena todavía no existe — y eso es buena señal.</b> "
        "Se crea sola con el primer registro rechazado. Que no exista significa que, hasta ahora, "
        "todos los registros de la API cumplieron el contrato. "
        "<b>La cuarentena se lee al revés que el resto del dashboard</b>: acá el cero es la buena noticia, "
        "y lo que importa vigilar es un <b>salto</b> en el número.",
        "🚧",
    )

# --- El contrato -----------------------------------------------------------
seccion("El contrato de datos", "Las reglas que un registro debe cumplir para entrar a Silver")

meta = q("""
    SELECT DISTINCT _contract_version, _source_table
    FROM silver.crypto_markets LIMIT 1
""")
izq, der = st.columns([1, 1])

with izq:
    v = meta.iloc[0]["_contract_version"] if not meta.empty else "—"
    src = meta.iloc[0]["_source_table"] if not meta.empty else "—"
    st.markdown(
        f"<div class='kpi'><div class='lab'>Contrato aplicado</div>"
        f"<div class='val' style='font-size:19px'>crypto_markets v{v}</div>"
        f"<div class='foot'>Definido en <code>data/contracts/crypto_markets.yaml</code>. "
        f"El DAG lo lee y genera un validador Pydantic <b>desde el YAML</b>: cambiar una regla "
        f"no requiere tocar código.<br><br>Origen declarado: <code>{src}</code></div></div>",
        unsafe_allow_html=True,
    )

with der:
    # Las reglas se LEEN del contrato, no se copian. Antes estaban pegadas en
    # este HTML -- y ademas anunciaban reglas que el contrato nunca tuvo
    # (market_cap >= 0, market_cap_rank >= 1). Una pagina que dice "el contrato
    # se define en el YAML" y despues muestra otra cosa entrena a desconfiar.
    reglas_html, version = reglas_del_contrato()
    st.markdown(
        "<div class='kpi'><div class='lab'>Reglas de calidad</div>"
        "<div style='font-family:\"IBM Plex Mono\",monospace;font-size:12.5px;"
        f"color:var(--ink-2);margin-top:10px;line-height:2'>{reglas_html}</div>"
        "<div class='foot'>Leídas del contrato "
        f"<code>crypto_markets.yaml</code>{version}. Si una regla falla, el "
        "registro entero va a cuarentena con el motivo escrito.</div></div>",
        unsafe_allow_html=True,
    )

# --- Completitud por columna ----------------------------------------------
seccion("Completitud", "Qué porcentaje de cada columna llega con dato (la API manda nulos sin avisar)")

comp = q("""
    SELECT
      round(100.0 * count(current_price)      / count(*), 1) AS "precio",
      round(100.0 * count(market_cap)         / count(*), 1) AS "market cap",
      round(100.0 * count(total_volume)       / count(*), 1) AS "volumen",
      round(100.0 * count(high_24h)           / count(*), 1) AS "máximo 24h",
      round(100.0 * count(low_24h)            / count(*), 1) AS "mínimo 24h",
      round(100.0 * count(max_supply)         / count(*), 1) AS "supply máximo",
      round(100.0 * count(ath)                / count(*), 1) AS "máximo histórico",
      round(100.0 * count(fully_diluted_valuation) / count(*), 1) AS "FDV"
    FROM silver.crypto_markets
""")
serie = comp.iloc[0].sort_values()
figc = go.Figure(go.Bar(
    x=serie.values, y=serie.index, orientation="h",
    marker=dict(color=[SUBE if v >= 95 else (GRIS if v >= 60 else BAJA) for v in serie.values]),
    text=[f"{v:.0f}%" for v in serie.values], textposition="outside",
    hovertemplate="%{y}: %{x:.1f}% con dato<extra></extra>",
))
figc.update_layout(height=280, bargap=0.35, xaxis=dict(range=[0, 112], showgrid=False, title=None),
                   **{k: v for k, v in PLOTLY.items() if k != "xaxis"})
st.plotly_chart(figc, use_container_width=True)
st.caption("Columnas por debajo del 100% **no son un error**: hay criptos sin supply máximo o sin FDV. "
           "Lo importante es **saberlo** antes de construir una métrica encima.")

# --- Lo que Silver agrega --------------------------------------------------
seccion("Lo que Silver agrega al dato", "Trazabilidad: de dónde vino y cuándo se procesó")

extra = q("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'silver' AND table_name = 'crypto_markets'
      AND column_name LIKE '\\_%'
    ORDER BY ordinal_position
""")
a, b2 = st.columns([1, 1.3])
with a:
    st.dataframe(extra, hide_index=True, use_container_width=True,
                 column_config={"column_name": "Columna", "data_type": "Tipo"})
with b2:
    st.markdown(
        "<div style='color:var(--ink-2);font-size:13px;line-height:1.6;padding-top:6px'>"
        "Estas columnas no vienen de la API: las <b>agrega la capa</b>. Son la diferencia entre "
        "un dato y un dato <i>confiable</i> — permiten responder <i>¿de dónde salió esta fila "
        "y cuándo se procesó?</i> meses después, cuando alguien discuta un número.<br><br>"
        "El <code>_contract_version</code> es clave: si mañana el contrato cambia, se puede "
        "distinguir qué filas se validaron con qué reglas.</div>",
        unsafe_allow_html=True,
    )

# --- El activo que entró/salió --------------------------------------------
rot = q("""
    WITH por_snap AS (
        SELECT snapshot_ts, count(DISTINCT id) AS n FROM silver.crypto_markets GROUP BY 1
    ), universo AS (
        SELECT count(DISTINCT id) AS total FROM silver.crypto_markets
    )
    SELECT (SELECT total FROM universo) AS universo,
           max(n) AS por_snapshot
    FROM por_snap
""")
u, ps = int(rot.iloc[0]["universo"]), int(rot.iloc[0]["por_snapshot"])
if u > ps:
    intermitentes = q(f"""
        SELECT name, symbol, count(DISTINCT snapshot_ts) AS apariciones
        FROM silver.crypto_markets
        GROUP BY 1, 2
        HAVING count(DISTINCT snapshot_ts) < (SELECT count(DISTINCT snapshot_ts) FROM silver.crypto_markets)
        ORDER BY apariciones
    """)
    seccion("Rotación del universo", "Una dimensión que cambia, capturada en vivo")
    st.markdown(
        f"<div class='aviso'><span>🔄</span><div>"
        f"Cada snapshot trae <b>{ps} activos</b> (el top-{ps} por capitalización), pero en total "
        f"se vieron <b>{u} activos distintos</b>: alguno <b>entró o salió</b> del ranking mientras "
        f"el pipeline corría.<br><br>Esto es exactamente el problema que resuelven las "
        f"<b>Slowly Changing Dimensions</b>: el universo no es fijo. Si Gold guardara solo la foto "
        f"de hoy, la historia de quien salió del top-{ps} desaparecería.</div></div>",
        unsafe_allow_html=True,
    )
    st.dataframe(intermitentes, hide_index=True, use_container_width=True,
                 column_config={"name": "Activo", "symbol": "Símbolo",
                                "apariciones": st.column_config.NumberColumn(
                                    "Snapshots en los que apareció")})

# =============================================================
# LAS REGLAS, Y SU RESULTADO REAL
# =============================================================
seccion("El contrato, ejecutandose",
        "Cada regla con lo que encontro en la ultima corrida")

hay_runs = q("SELECT to_regclass('silver.quality_runs') IS NOT NULL AS e").iloc[0]["e"]

if not hay_runs:
    aviso(
        "<b>Todavia no hay mediciones de calidad.</b> Las escribe "
        "<code>crypto_silver</code> en <code>silver.quality_runs</code>, una fila "
        "por regla y por corrida. Espera la proxima corrida.",
        "📋",
    )
else:
    ult = q("""
        WITH u AS (SELECT max(run_ts) AS run_ts FROM silver.quality_runs)
        SELECT r.regla, r.tipo, r.severidad, r.filas_evaluadas, r.violaciones,
               round(r.violaciones::numeric / NULLIF(r.filas_evaluadas,0) * 100, 2) AS pct
        FROM silver.quality_runs r, u
        WHERE r.run_ts = u.run_ts
        ORDER BY r.severidad, r.violaciones DESC
    """)

    if ult.empty:
        st.caption("La tabla existe pero todavia no tiene mediciones.")
    else:
        errores = ult[ult["severidad"] == "error"]
        avisos = ult[ult["severidad"] == "warning"]
        c = st.columns(3)
        c[0].markdown(kpi("Reglas evaluadas", f"{len(ult)}",
                          foot="Declaradas en <code>crypto_markets.yaml</code> y "
                               "aplicadas por <code>evaluar_reglas()</code>."),
                      unsafe_allow_html=True)
        c[1].markdown(kpi("Rechazos (error)", f"{int(errores['violaciones'].sum())}",
                          foot="Registros que no pasan: van a cuarentena."),
                      unsafe_allow_html=True)
        c[2].markdown(kpi("Marcados (warning)", f"{int(avisos['violaciones'].sum())}",
                          foot="Pasan a Silver, pero quedan senalados en "
                               "<code>_quality_flags</code>."),
                      unsafe_allow_html=True)

        figr = go.Figure(go.Bar(
            x=ult["violaciones"], y=ult["regla"], orientation="h",
            marker_color=[BAJA if s == "error" else SUBE for s in ult["severidad"]],
            hovertemplate="<b>%{y}</b><br>%{x} de " +
                          ult["filas_evaluadas"].astype(str) + " filas<extra></extra>",
        ))
        figr.update_layout(**layout(
            height=30 * len(ult) + 70,
            xaxis=dict(title="Filas que violan la regla", showgrid=True,
                       gridcolor="rgba(128,128,128,.15)"),
            yaxis=dict(autorange="reversed"),
        ))
        st.plotly_chart(figr, use_container_width=True)
        st.caption("Rojo = **error** (cuarentena) · azul = **warning** (pasa, marcado). "
                   "Las reglas en cero tambien son informacion: dicen que se "
                   "evaluaron y no encontraron nada — que no es lo mismo que no "
                   "haberlas mirado.")

        st.dataframe(
            ult, hide_index=True, use_container_width=True,
            column_config={
                "regla": "Regla", "tipo": "Tipo", "severidad": "Severidad",
                "filas_evaluadas": st.column_config.NumberColumn("Evaluadas"),
                "violaciones": st.column_config.NumberColumn("Violan"),
                "pct": st.column_config.NumberColumn("%", format="%.2f%%"),
            },
        )

    # --- la tendencia: donde se ve que algo cambio -------------------
    serie = q("""
        SELECT run_ts, regla, violaciones
        FROM silver.quality_runs
        WHERE severidad = 'warning'
        ORDER BY run_ts
    """)
    if serie["run_ts"].nunique() >= 2:
        seccion("La tendencia", "Un numero aislado no dice nada; el cambio si")
        figt = go.Figure()
        for i, (nombre, g) in enumerate(serie.groupby("regla")):
            figt.add_trace(go.Scatter(
                x=g["run_ts"], y=g["violaciones"], mode="lines+markers", name=nombre,
                line=dict(color=SERIES[i % len(SERIES)], width=2), marker=dict(size=5),
            ))
        figt.update_layout(**layout(
            height=280,
            yaxis=dict(title="Violaciones", showgrid=True,
                       gridcolor="rgba(128,128,128,.15)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        ))
        st.plotly_chart(figt, use_container_width=True)
        st.caption("**12 rechazos** puede ser lo de siempre o una catastrofe: la "
                   "diferencia solo se ve con la historia al lado. Un salto aca "
                   "suele avisar que la fuente cambio algo, antes de que el "
                   "numero raro llegue a Gold.")
    else:
        st.caption("⏳ Con una sola corrida no hay tendencia que mirar. "
                   "`silver.quality_runs` acumula: a la segunda aparece.")

# =============================================================
# LOS REGISTROS MARCADOS
# =============================================================
tiene_flags = q("""
    SELECT count(*) AS n FROM information_schema.columns
    WHERE table_schema='silver' AND table_name='crypto_markets'
      AND column_name='_quality_flags'
""").iloc[0]["n"]

if tiene_flags:
    seccion("Lo que pasó, pero con reparos",
            "Registros marcados: usables, y vale mirarlos")
    marcados = q("""
        SELECT COALESCE(NULLIF(_quality_flags,''),'(sin marcas)') AS marcas,
               count(*) AS filas
        FROM silver.crypto_markets
        WHERE _quality_flags IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC
    """)
    if not marcados.empty:
        st.dataframe(marcados, hide_index=True, use_container_width=True,
                     column_config={"marcas": "Reglas que viola",
                                    "filas": st.column_config.NumberColumn("Filas")})
        muestra = q("""
            SELECT id, name, current_price, low_24h, high_24h,
                   circulating_supply, total_supply, total_volume, _quality_flags
            FROM silver.crypto_markets
            WHERE _quality_flags IS NOT NULL AND _quality_flags <> ''
            ORDER BY snapshot_ts DESC LIMIT 20
        """)
        with st.expander("Ver registros marcados (ultimos 20)"):
            st.dataframe(muestra, hide_index=True, use_container_width=True)
        aviso(
            "<b>Por que pasan y no se rechazan.</b> Un precio por debajo de su "
            "propio minimo de 24 h no es un dato corrupto: es que las tres "
            "columnas <b>no se refrescan en el mismo instante</b>, asi que un "
            "precio que acaba de romper el piso aparece fuera de rango hasta que "
            "<code>low_24h</code> se pone al dia. Y volumen cero son fondos "
            "institucionales que no cotizan en mercado abierto — el dato esta "
            "bien, lo que avisa es que ese activo no deberia entrar en un "
            "analisis de volumen.<br><br>"
            "Rechazarlos seria tirar datos buenos. No mirarlos seria peor. Por eso "
            "hay <b>dos severidades</b>: con una sola, o las reglas son tan laxas "
            "que no atrapan nada, o tan estrictas que rompen el pipeline.",
            "🔖",
        )

de_donde_sale("gold.v_series_diaria",
              "Lo que Silver habilita: una vez que el dato está validado y con "
              "tipos, Gold puede armar series temporales sobre él.")
