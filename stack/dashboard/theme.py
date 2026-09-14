"""
Tema visual compartido del dashboard.

Streamlit no permite tocar el DOM, pero sí inyectar CSS: con eso se
redefinen tipografías, colores, tarjetas y tablas. Este módulo centraliza
TODO lo visual para que las páginas se ocupen solo de los datos.

Uso en una página:

    from theme import aplicar_tema, encabezado, hero, kpi, seccion, PLOTLY

    aplicar_tema("Mercado ahora", "📊")          # SIEMPRE primero
    encabezado("Mercado ahora", "¿Cómo está el mercado?")
    hero("Capitalización total", "US$ 2,642 B", -1.84, serie)

Lo que exporta este módulo, y nada más:

    aplicar_tema · encabezado · seccion · aviso · pill · kpi · hero ·
    tabla · ticker · frescura_pill · de_donde_sale · layout ·
    filtro_periodo · where_periodo
    SUBE · BAJA · GRIS · SERIES · PLOTLY
"""

import streamlit as st

# ---------------------------------------------------------------- paleta
# Par divergente validado (contraste + daltonismo) del sistema de diseño.
# Pasos DARK del sistema de diseño: son los que pasan el validador de
# contraste y daltonismo sobre el fondo oscuro (#0e1219), no los de light.
SUBE = "#3987e5"
BAJA = "#e66767"
GRIS = "#8a8987"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"]

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500&display=swap');

/* Tema oscuro fijo (config.toml lo acompaña): estetica de terminal.
   Un solo set de tokens evita que el CSS propio pelee con el de Streamlit. */
:root{
  --ground:#0e1219; --surface:#151b24; --surface-2:#1b2330; --line:#27303d;
  --ink:#e9eef5; --ink-2:#a4b0c0; --ink-3:#6f7d8f;
  --up:#3987e5; --down:#e66767; --accent:#3987e5;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -14px rgba(0,0,0,.7);
}

/* ---- superficie de la app ---- */
.stApp{ background:var(--ground); }
header[data-testid="stHeader"]{ background:transparent; height:0; }
#MainMenu, footer{ visibility:hidden; }
[data-testid="stToolbar"]{ right:12px; }
[data-testid="stDecoration"]{ display:none; }

/* ---- base ---- */
html, body, [class*="st-"]{ font-family:"IBM Plex Sans",system-ui,sans-serif; }
.block-container{ padding-top:2.2rem; max-width:1280px; }
h1,h2,h3{ font-family:Archivo,system-ui,sans-serif !important; letter-spacing:-.02em; }
h1{ font-weight:700 !important; }
h2,h3{ font-weight:600 !important; }

/* números de st.metric en mono + tabular */
[data-testid="stMetricValue"]{
  font-family:"IBM Plex Mono",monospace !important; font-weight:600 !important;
  font-variant-numeric:tabular-nums; letter-spacing:-.02em;
}
[data-testid="stMetricLabel"] p{
  font-family:"IBM Plex Mono",monospace !important; font-size:10.5px !important;
  letter-spacing:.12em; text-transform:uppercase; color:var(--ink-3) !important;
}
[data-testid="stMetricDelta"]{ font-family:"IBM Plex Mono",monospace !important; }

/* métricas como tarjeta */
[data-testid="stMetric"]{
  background:var(--surface); border:1px solid var(--line); border-radius:12px;
  padding:14px 16px 12px; box-shadow:var(--shadow);
}

/* sidebar como panel de terminal */
section[data-testid="stSidebar"]{
  background:var(--surface); border-right:1px solid var(--line);
}
[data-testid="stSidebarNav"] a span{
  font-family:"IBM Plex Mono",monospace !important; font-size:13px !important;
}
[data-testid="stSidebarNav"] a{ border-radius:8px; }

/* widgets: bordes y radios consistentes con las tarjetas */
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div{
  background:var(--surface) !important; border-color:var(--line) !important;
  border-radius:9px !important; font-family:"IBM Plex Mono",monospace;
}
.stButton button{
  border:1px solid var(--line); border-radius:9px; background:var(--surface);
  color:var(--ink-2); font-family:"IBM Plex Mono",monospace; font-size:12.5px;
  transition:.12s;
}
.stButton button:hover{ border-color:var(--accent); color:var(--ink); }

/* dataframes nativos: fondo y tipografia del tema */
[data-testid="stDataFrame"]{ border:1px solid var(--line); border-radius:12px; overflow:hidden; }
[data-testid="stDataFrame"] *{ font-family:"IBM Plex Mono",monospace !important; }

/* alertas (st.info / st.caption) mas sobrias */
[data-testid="stAlert"]{
  background:var(--surface); border:1px solid var(--line); border-radius:10px;
  color:var(--ink-2);
}
hr{ border-color:var(--line) !important; }

/* tabs / expanders / inputs con la misma familia */
.stSelectbox label, .stMultiSelect label{
  font-family:"IBM Plex Mono",monospace; font-size:11px;
  letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3);
}

/* ---- componentes propios ---- */
.ticker{
  background:var(--surface); border:1px solid var(--line); border-radius:10px;
  overflow:hidden; white-space:nowrap; margin-bottom:18px;
}
.ticker-track{
  display:inline-block; padding:8px 0;
  font-family:"IBM Plex Mono",monospace; font-size:12.5px;
  animation:tk 52s linear infinite;
}
@keyframes tk{ from{transform:translateX(0)} to{transform:translateX(-50%)} }
@media (prefers-reduced-motion: reduce){ .ticker-track{animation:none} }
.tk{ color:var(--ink-2); margin-right:26px }
.tk b{ color:var(--ink); font-weight:600; margin-right:6px }
.tk .u{ color:var(--up) } .tk .d{ color:var(--down) }

.hero{
  background:var(--surface); border:1px solid var(--line); border-radius:14px;
  padding:22px 24px; box-shadow:var(--shadow); margin-bottom:14px;
  display:flex; gap:26px; align-items:center; justify-content:space-between; flex-wrap:wrap;
}
.hero .eyebrow{
  font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--ink-3); margin-bottom:8px;
}
.hero .big{
  font-family:"IBM Plex Mono",monospace; font-weight:600; line-height:1;
  font-size:clamp(34px,5vw,56px); letter-spacing:-.03em;
  font-variant-numeric:tabular-nums; color:var(--ink);
}
.hero .delta{
  display:inline-block; margin-top:11px; padding:4px 10px; border-radius:7px;
  font-family:"IBM Plex Mono",monospace; font-size:13.5px; font-weight:500;
}
.hero .delta.u{ color:var(--up); background:color-mix(in srgb,var(--up) 12%,transparent) }
.hero .delta.d{ color:var(--down); background:color-mix(in srgb,var(--down) 12%,transparent) }
.hero .note{ color:var(--ink-3); font-size:12.5px; margin-top:12px; max-width:38ch }

.pill{
  display:inline-flex; align-items:center; gap:8px; background:var(--surface);
  border:1px solid var(--line); border-radius:999px; padding:6px 13px 6px 10px;
  font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--ink-2);
}
.pill .dot{ width:8px;height:8px;border-radius:50% }

.kpi{
  background:var(--surface); border:1px solid var(--line); border-radius:12px;
  padding:14px 16px 11px; box-shadow:var(--shadow); height:100%;
}
.kpi .lab{
  font-family:"IBM Plex Mono",monospace; font-size:10.5px; letter-spacing:.12em;
  text-transform:uppercase; color:var(--ink-3);
}
.kpi .val{
  font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:24px;
  letter-spacing:-.02em; margin-top:5px; font-variant-numeric:tabular-nums; color:var(--ink);
}
.kpi .chg{ font-family:"IBM Plex Mono",monospace; font-size:12px; margin-top:2px }
.kpi .foot{ color:var(--ink-3); font-size:11.5px; margin-top:6px; line-height:1.4 }

.sec{ margin:26px 0 10px }
.sec h2{ font-size:17px !important; margin:0 !important }
.sec p{ margin:2px 0 0; color:var(--ink-3); font-size:12.5px }

.tbl{ width:100%; border-collapse:collapse; font-family:"IBM Plex Mono",monospace; font-size:13px }
.tbl th{
  text-align:right; font-weight:500; font-size:10.5px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--ink-3); padding:10px 14px;
  background:var(--surface-2); border-bottom:1px solid var(--line); white-space:nowrap;
}
.tbl th:first-child,.tbl th:nth-child(2){ text-align:left }
.tbl td{
  padding:8px 14px; border-bottom:1px solid var(--line); text-align:right;
  font-variant-numeric:tabular-nums; white-space:nowrap; color:var(--ink);
}
.tbl td:first-child{ color:var(--ink-3); text-align:left; width:44px }
.tbl td:nth-child(2){ text-align:left; font-family:"IBM Plex Sans",sans-serif }
.tbl tbody tr:hover td{ background:var(--surface-2) }
.tbl .sym{ color:var(--ink-3); margin-left:7px; font-size:11.5px }
.tbl .u{ color:var(--up) } .tbl .d{ color:var(--down) }
.tbl-wrap{ background:var(--surface); border:1px solid var(--line); border-radius:12px;
           overflow:hidden auto; box-shadow:var(--shadow); max-height:520px }

.aviso{
  display:flex; gap:9px; padding:11px 14px; border-radius:10px;
  border:1px solid var(--line); background:var(--surface); color:var(--ink-2);
  font-size:12.5px; line-height:1.5; margin-top:10px;
}
.aviso b{ color:var(--ink) }
</style>
"""

# Template de Plotly: fondo transparente, grilla recesiva, tipografía del sistema.
PLOTLY = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="IBM Plex Mono, monospace", size=11.5),
    margin=dict(l=0, r=0, t=10, b=0),
    hoverlabel=dict(font_family="IBM Plex Mono, monospace", font_size=12),
    xaxis=dict(showgrid=False, title=None),
    yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,.15)", zeroline=False, title=None),
)


def layout(**overrides) -> dict:
    """El layout base de Plotly, con overrides fusionados.

    Existe porque `**PLOTLY, yaxis=...` explota: PLOTLY YA trae `yaxis`, y
    Python no admite el mismo keyword dos veces. Sin esto, cada pagina
    resolvia el choque a su manera -- unas con un dict-comprehension que
    excluia claves, otras replicando el layout entero a mano.

        fig.update_layout(**layout(height=320, yaxis=dict(title="Base 100")))
    """
    return {**PLOTLY, **overrides}


def aplicar_tema(titulo: str, icono: str = "📊"):
    """Configura la página e inyecta el CSS. Llamar PRIMERO en cada página."""
    st.set_page_config(page_title=titulo, page_icon=icono, layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)


def encabezado(titulo: str, subtitulo: str, estado_html: str = ""):
    """Título + subtítulo + (opcional) pill de estado, con botón de refresco."""
    c1, c2 = st.columns([6, 1.15])
    with c1:
        st.markdown(
            f"<h1 style='margin-bottom:2px'>{titulo}</h1>"
            f"<div style='color:var(--ink-3);font-size:13px'>{subtitulo}</div>",
            unsafe_allow_html=True,
        )
    with c2:
        if estado_html:
            st.markdown(estado_html, unsafe_allow_html=True)
        if st.button("🔄 Actualizar", use_container_width=True,
                     help="Limpia el caché (60 s) y vuelve a consultar Gold"):
            st.cache_data.clear()
            st.rerun()


def pill(texto: str, color_var: str = "--up", detalle: str = "") -> str:
    det = f" <span style='color:var(--ink-3)'>· {detalle}</span>" if detalle else ""
    return (f"<div class='pill'><span class='dot' style='background:var({color_var});"
            f"box-shadow:0 0 0 3px color-mix(in srgb,var({color_var}) 22%,transparent)'></span>"
            f"{texto}{det}</div>")


def _spark(vals, color, w=230, h=34) -> str:
    """Sparkline SVG inline. Devuelve '' si no hay serie suficiente."""
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    r = (hi - lo) or 1
    pts = " ".join(
        f"{i / (len(vals) - 1) * w:.1f},{h - 3 - (v - lo) / r * (h - 6):.1f}"
        for i, v in enumerate(vals)
    )
    return (f"<svg viewBox='0 0 {w} {h}' preserveAspectRatio='none' "
            f"style='width:100%;height:{h}px;margin-top:7px'>"
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='1.8'/></svg>")


def hero(eyebrow: str, valor: str, delta_pct=None, serie=None, nota: str = ""):
    """Bloque principal: una métrica grande con su delta y sparkline."""
    d = ""
    if delta_pct is not None:
        cls = "u" if delta_pct >= 0 else "d"
        flecha = "▲" if delta_pct >= 0 else "▼"
        d = (f"<div class='delta {cls}'>{flecha} {abs(delta_pct):.2f} % "
             f"<span style='color:var(--ink-3);font-weight:400'>vs día anterior</span></div>")
    color = SUBE if (delta_pct or 0) >= 0 else BAJA
    sp = _spark(serie or [], color, w=460, h=96)
    nota_html = f"<div class='note'>{nota}</div>" if nota else ""
    st.markdown(
        f"<div class='hero'><div><div class='eyebrow'>{eyebrow}</div>"
        f"<div class='big'>{valor}</div>{d}{nota_html}</div>"
        f"<div style='flex:1;min-width:240px'>{sp}</div></div>",
        unsafe_allow_html=True,
    )


def kpi(lab: str, val: str, chg=None, serie=None, foot: str = "") -> str:
    """HTML de una tarjeta KPI (usar dentro de st.columns con unsafe_allow_html)."""
    c = ""
    if chg is not None:
        col = SUBE if chg >= 0 else BAJA
        c = (f"<div class='chg' style='color:{col}'>{chg:+.2f} % "
             f"<span style='color:var(--ink-3)'>vs ayer</span></div>")
    color = SUBE if (chg or 0) >= 0 else BAJA
    foot_html = f"<div class='foot'>{foot}</div>" if foot else ""
    return (f"<div class='kpi'><div class='lab'>{lab}</div><div class='val'>{val}</div>{c}"
            f"{_spark(serie or [], color)}{foot_html}</div>")


def seccion(titulo: str, subtitulo: str = ""):
    sub = f"<p>{subtitulo}</p>" if subtitulo else ""
    st.markdown(f"<div class='sec'><h2>{titulo}</h2>{sub}</div>",
                unsafe_allow_html=True)


def aviso(html: str, icono: str = "📅"):
    st.markdown(f"<div class='aviso'><span>{icono}</span><div>{html}</div></div>",
                unsafe_allow_html=True)


def ticker(items):
    """Cinta superior: items = [(símbolo, precio_fmt, variación_pct), ...]"""
    cuerpo = "".join(
        f"<span class='tk'><b>{s}</b>{p} "
        f"<span class='{'u' if v >= 0 else 'd'}'>{v:+.2f}%</span></span>"
        for s, p, v in items
    )
    st.markdown(f"<div class='ticker'><span class='ticker-track'>{cuerpo}{cuerpo}</span></div>",
                unsafe_allow_html=True)


def tabla(html_filas: str, encabezados: list) -> None:
    ths = "".join(f"<th>{h}</th>" for h in encabezados)
    st.markdown(
        f"<div class='tbl-wrap'><table class='tbl'><thead><tr>{ths}</tr></thead>"
        f"<tbody>{html_filas}</tbody></table></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- periodo
PRESETS = {"7 días": 7, "30 días": 30, "90 días": 90, "Todo": None}


def filtro_periodo(clave: str, default: str = "90 días") -> dict:
    """Un control de rango temporal, en su propia fila, arriba de todo.

    Devuelve ``{"desde", "hasta", "dias", "etiqueta"}`` — ``desde``/``hasta``
    son ``date`` o ``None`` (sin límite).

    Va ARRIBA de los gráficos que gobierna, no adentro de uno: si cada tarjeta
    trae su propio filtro, dos paneles vecinos terminan mostrando períodos
    distintos y nadie se da cuenta.

    `clave` separa el estado entre páginas (Streamlit comparte session_state
    entre todas): sin eso, mover el rango en una página lo movería en las otras.
    """
    import datetime as _dt

    c1, c2 = st.columns([2.2, 1.8])
    with c1:
        elegido = st.radio(
            "Período", list(PRESETS) + ["Personalizado"],
            index=list(PRESETS).index(default), horizontal=True,
            key=f"periodo_{clave}", label_visibility="collapsed",
        )

    hoy = _dt.date.today()
    if elegido == "Personalizado":
        with c2:
            rango = st.date_input(
                "Rango", value=(hoy - _dt.timedelta(days=30), hoy),
                key=f"rango_{clave}", label_visibility="collapsed",
            )
        if isinstance(rango, (tuple, list)) and len(rango) == 2:
            desde, hasta = rango
        else:                       # el usuario eligió la primera fecha nomás
            desde, hasta = (rango if not isinstance(rango, (tuple, list))
                            else rango[0]), hoy
        dias = (hasta - desde).days
        etiqueta = f"{desde:%d-%b} → {hasta:%d-%b}"
    elif PRESETS[elegido] is None:
        desde, hasta, dias, etiqueta = None, None, None, "todo el histórico"
    else:
        dias = PRESETS[elegido]
        desde, hasta = hoy - _dt.timedelta(days=dias), hoy
        etiqueta = f"últimos {dias} días"

    return {"desde": desde, "hasta": hasta, "dias": dias, "etiqueta": etiqueta}


def where_periodo(columna: str, periodo: dict) -> str:
    """El predicado SQL del rango, listo para pegar en un WHERE.

    Devuelve "" cuando no hay límite, así la query sigue siendo válida. El
    filtro se aplica en SQL y no en pandas a proposito: traer 90 días para
    descartar 80 en el cliente es mover datos al pedo.
    """
    if not periodo or periodo.get("desde") is None:
        return ""
    return (f" AND {columna} >= DATE '{periodo['desde']:%Y-%m-%d}'"
            f" AND {columna} < DATE '{periodo['hasta']:%Y-%m-%d}' + 1")


# ---------------------------------------------------------------- frescura
_COLOR_FRESCURA = {
    "al_dia": "--up",
    "demorado": "--accent",
    "detenido": "--down",
    "sin_datos": "--ink-3",
}
_TEXTO_FRESCURA = {
    "al_dia": "AL DÍA",
    "demorado": "DEMORADO",
    "detenido": "DETENIDO",
    "sin_datos": "SIN DATOS",
}


def frescura_pill(estado: dict) -> str:
    """Chip de frescura a partir del dict que devuelve ``db.frescura()``.

    Una sola redacción para todo el dashboard. Antes cada página inventaba la
    suya y el mismo estado se llamaba distinto en dos pantallas.
    """
    return pill(_TEXTO_FRESCURA.get(estado["estado"], "?"),
                _COLOR_FRESCURA.get(estado["estado"], "--ink-3"),
                estado["etiqueta"])


# ------------------------------------------------------- de dónde sale esto
def de_donde_sale(vista: str, que_responde: str = "") -> None:
    """Expander con el SQL REAL de la vista que alimenta la pantalla.

    No es documentación: es ``pg_get_viewdef`` contra Postgres, así que
    muestra la definición vigente y no puede quedar desactualizada. La idea es
    que el tablero enseñe la capa semántica mientras la usa — el número que
    ves arriba es exactamente este SELECT.
    """
    from db import definicion_vista          # import local: evita ciclo

    sql = definicion_vista(vista)
    if not sql:
        return
    with st.expander(f"🔍 ¿De dónde sale esto? · `{vista}`"):
        if que_responde:
            st.caption(que_responde)
        st.code(sql.strip(), language="sql")
        st.caption(
            "Definida **una sola vez**, en el warehouse. El dashboard no "
            "recalcula: lee. Si mañana cambia la definición del KPI, cambia "
            "acá y todas las pantallas quedan coherentes."
        )
