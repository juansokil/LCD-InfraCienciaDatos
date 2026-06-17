"""Estilos compartidos del dashboard (paleta + tipografía CityBikes G04)."""
import streamlit as st

ROJO, AMBAR, VERDE, INK, GRIS = "#D7263D", "#E8A13A", "#2E9E5B", "#2B1B1B", "#8A8A8A"


def style():
    """CSS de marca: Inter en TODO, tarjetas de KPI, paneles y bastante aire."""
    st.markdown(
        """
        <style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');</style>
        <style>
          /* una sola tipografía: Inter en todo el texto (sin tocar los iconos, que tienen su propia fuente) */
          html, body, .stApp { font-family: 'Inter', system-ui, sans-serif; }
          .stApp p, .stApp div, .stApp label, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
          .stApp td, .stApp th, .stApp button, .stApp input, .stApp textarea,
          [data-baseweb="select"] div, [data-testid="stMarkdownContainer"],
          [data-testid="stMetricValue"], [data-testid="stMetricLabel"] p {
            font-family: 'Inter', system-ui, sans-serif !important;
          }

          /* look de app limpio — fuera el menú, el footer y la barra blanca de arriba */
          #MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; height: 0; }
          [data-testid="stHeader"] { display: none !important; }
          [data-testid="stDecoration"] { display: none !important; }
          .block-container { padding-top: 2rem; max-width: 100%; padding-left: 2.6rem; padding-right: 2.6rem; }

          /* === FONDO con diseño (no plano): textura de puntos + brillos de marca === */
          .stApp {
            background-color: #FBFAF9;
            background-image:
              radial-gradient(circle at 1px 1px, rgba(43,27,27,.045) 1px, transparent 0),
              radial-gradient(1000px 620px at 100% -6%, rgba(215,38,61,.07), transparent 55%),
              radial-gradient(820px 520px at -6% 100%, rgba(232,161,58,.06), transparent 60%);
            background-size: 22px 22px, 100% 100%, 100% 100%;
            background-attachment: fixed;
          }

          /* === SIDEBAR con diseño: degradado cálido + acento arriba + nav con estados === */
          [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #FDEEEF 0%, #FBE2E2 50%, #F8E7DE 100%);
            border-right: 1px solid #F0D5D0;
          }
          [data-testid="stSidebar"]::after {
            content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
            background: linear-gradient(90deg, #D7263D, #E8A13A);
          }
          /* pegamos el contenido del sidebar arriba (sin el hueco que dejaba el header oculto) */
          [data-testid="stSidebarHeader"] { padding: .5rem .6rem .1rem !important; min-height: 0 !important; }
          [data-testid="stSidebarUserContent"] { padding-top: .2rem !important; }

          /* marca arriba de todo: tarjeta con ícono de bici + título + bajada */
          .cb-brand {
            display: flex; align-items: center; gap: 13px;
            margin: 8px 6px 2px; padding: 15px 16px; border-radius: 16px;
            background: linear-gradient(135deg, #D7263D 0%, #E8662F 55%, #E8A13A 100%);
            box-shadow: 0 12px 24px rgba(215,38,61,.26);
          }
          .cb-brand .ic {
            width: 40px; height: 40px; flex: 0 0 40px; border-radius: 12px;
            background: rgba(255,255,255,.20); display: flex; align-items: center; justify-content: center;
          }
          .cb-brand .t { color: #FFFFFF; font-size: 1.18rem; font-weight: 800; letter-spacing: -.01em; line-height: 1.12; }
          .cb-brand .s { color: rgba(255,255,255,.88); font-size: .72rem; font-weight: 600; letter-spacing: .02em; }
          .cb-navlabel { margin: 18px 12px 4px; color: #B26B66; font-size: .68rem; font-weight: 800; letter-spacing: .16em; }

          /* navegación propia (st.page_link) con estados rojo/pastel + íconos */
          [data-testid="stSidebar"] [data-testid="stPageLink"] a {
            border-radius: 12px; margin: 3px 6px; padding: 11px 13px; gap: 12px;
            background: rgba(255,255,255,.55); border: 1px solid #F1DBD7; transition: all .18s;
          }
          [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {
            background: rgba(215,38,61,.10); border-color: #EEC4BF; transform: translateX(2px);
          }
          [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {
            background: linear-gradient(90deg, rgba(215,38,61,.18), rgba(232,161,58,.10));
            border-color: #E79B95; box-shadow: 0 4px 12px rgba(215,38,61,.10);
          }
          [data-testid="stSidebar"] [data-testid="stPageLink"] p { color: #2B1B1B; font-weight: 600; font-size: .98rem; }
          [data-testid="stSidebar"] [data-testid="stPageLink"] span[data-testid="stIconMaterial"] { color: #D7263D !important; }

          /* menú siempre visible: ocultamos el botón de minimizar/expandir (Streamlit no hace un riel prolijo) */
          [data-testid="stSidebarCollapseButton"],
          [data-testid="stSidebarCollapsedControl"],
          [data-testid="collapsedControl"] { display: none !important; }

          /* MÁS aire entre bloques (no apretado) */
          [data-testid="stVerticalBlock"] { gap: 1.5rem; }

          /* KPIs como tarjetas */
          [data-testid="stMetric"] {
            background: #FFFFFF; border: 1px solid #ECE3DF; border-left: 5px solid #D7263D;
            border-radius: 14px; padding: 18px 20px 12px; box-shadow: 0 8px 22px rgba(43,27,27,.06);
          }
          [data-testid="stMetricLabel"] p { color: #6B635F; font-weight: 600; }
          [data-testid="stMetricValue"] { color: #2B1B1B; font-weight: 700; }

          /* selectbox (Ciudad a analizar) dentro de su tarjeta: campo cómodo, con aire y acento rojo */
          .stSelectbox label p, [data-testid="stWidgetLabel"] p {
            color: #6B635F !important; font-weight: 700 !important; font-size: .82rem !important;
            text-transform: uppercase; letter-spacing: .09em; margin-bottom: .45rem !important;
          }
          [data-baseweb="select"] > div {
            background: #FAF6F4 !important; border: 1.5px solid #E7DAD4 !important;
            border-radius: 12px !important; box-shadow: none !important;
            min-height: 52px; transition: border-color .2s, box-shadow .2s;
          }
          [data-baseweb="select"] > div:hover { border-color: #D7263D !important; }
          [data-baseweb="select"] > div:focus-within {
            border-color: #D7263D !important; background: #FFFFFF !important;
            box-shadow: 0 0 0 3px rgba(215,38,61,.12) !important;
          }
          [data-baseweb="select"] svg { fill: #D7263D !important; }

          /* paneles blancos SOLO los anidados (= st.container(border=True)), NO el bloque principal
             — así no se forma una caja blanca gigante envolviendo toda la página */
          [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: none !important; border-radius: 16px !important;
            box-shadow: 0 8px 22px rgba(43,27,27,.05); background: #FFFFFF;
          }

          /* tablas de estaciones críticas (HTML propio): limpias, sin bordes raros, dentro de la card */
          .cb-table {
            width: 100%; border-collapse: separate; border-spacing: 0; font-size: .9rem;
            background: transparent; border: 1px solid #ECE3DF; border-radius: 10px; overflow: hidden;
          }
          /* anulamos el estilo por defecto de Streamlit y ponemos NUESTRA grilla (gris cálido suave, NO negra) */
          .cb-table th, .cb-table td {
            background: transparent !important; text-align: left !important; vertical-align: middle;
            padding: 11px 14px !important; border: none !important; border-bottom: 1px solid #F3ECE8 !important;
          }
          /* separador vertical entre las dos columnas */
          .cb-table th:first-child, .cb-table td:first-child { border-right: 1px solid #F3ECE8 !important; }
          .cb-table thead th {
            color: #9A8F8A !important; font-weight: 700; font-size: .7rem; white-space: nowrap;
            text-transform: uppercase; letter-spacing: .07em; border-bottom: 1.5px solid #ECE3DF !important;
          }
          .cb-table thead th:last-child { width: 55%; }
          .cb-table tbody tr:last-child td { border-bottom: none !important; }
          .cb-table tbody tr:hover td { background: rgba(215,38,61,.04) !important; }
          .cb-table .est { color: #2B1B1B; font-weight: 600; line-height: 1.3; }
          .cb-table .barwrap { display: flex; align-items: center; gap: 11px; }
          .cb-table .track { flex: 1; height: 8px; background: #F0E7E2; border-radius: 6px; overflow: hidden; }
          .cb-table .fill { height: 100%; border-radius: 6px; }
          .cb-table .pct { color: #2B1B1B; font-weight: 700; font-size: .82rem; min-width: 46px; text-align: right; }

          /* callout de insight */
          .insight {
            background: linear-gradient(135deg, #FCEEF0, #F6E0E3); border-left: 6px solid #D7263D;
            border-radius: 14px; padding: 18px 22px; margin: 14px 0 10px; color: #2B1B1B;
            font-size: 1.06rem; line-height: 1.5;
          }
          .insight b { color: #A51C2C; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar(inicio, gold):
    """Barra lateral propia: marca CityBikes + navegación con íconos (sobre st.navigation)."""
    bike = ("<svg width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='white' "
            "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
            "<circle cx='18.5' cy='17.5' r='3.5'/><circle cx='5.5' cy='17.5' r='3.5'/>"
            "<circle cx='15' cy='5' r='1'/><path d='M12 17.5V14l-3-3 4-3 2 3h2'/></svg>")
    with st.sidebar:
        st.markdown(
            f"<div class='cb-brand'><div class='ic'>{bike}</div>"
            f"<div class='txt'><div class='t'>CityBikes</div><div class='s'>G04 · Bicis públicas</div></div></div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div class='cb-navlabel'>NAVEGACIÓN</div>", unsafe_allow_html=True)
        st.page_link(inicio, label="Inicio", icon=":material/home:")
        st.page_link(gold, label="Gold", icon=":material/insights:")


def header(kicker, titulo, subtitulo=""):
    """Encabezado principal con diseño: acento rojo + kicker + título grande + subtítulo."""
    sub = (f"<div style='color:{GRIS};font-size:.96rem;margin:.35rem 0 .2rem'>{subtitulo}</div>"
           if subtitulo else "")
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:16px;margin-bottom:.1rem">
          <div style="width:6px;height:58px;background:{ROJO};border-radius:3px"></div>
          <div>
            <div style="color:{ROJO};font-size:.78rem;font-weight:700;letter-spacing:.2em;text-transform:uppercase">{kicker}</div>
            <div style="font-size:2.2rem;font-weight:800;color:{INK};line-height:1.18;letter-spacing:-.02em;padding-bottom:.04em">{titulo}</div>
          </div>
        </div>{sub}""",
        unsafe_allow_html=True,
    )


def panel(titulo, subtitulo=""):
    """Encabezado de panel: título en rojo + subtítulo gris."""
    sub = (f"<div style='color:{GRIS};font-size:.9rem;margin:.15rem 0 .8rem'>{subtitulo}</div>"
           if subtitulo else "<div style='margin-bottom:.6rem'></div>")
    st.markdown(
        f"<div style='color:{ROJO};font-size:1.18rem;font-weight:700;margin:0'>{titulo}</div>{sub}",
        unsafe_allow_html=True,
    )
