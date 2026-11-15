
#tema.py
#Este módulo centraliza los estilos visuales del dashboard G06.
#Define la tipografía, los colores y el diseño de los distintos
#componentes de la interfaz para mantener una apariencia uniforme
#en todas las páginas de la aplicación.


import streamlit as st
import plotly.io as pio
import plotly.express as px


def aplicar_tema():

    # Configuración general de los gráficos Plotly
    pio.templates["tema_viajes"] = pio.templates["plotly_white"]

    pio.templates["tema_viajes"].layout.update(
        font=dict(
            family="DM Sans",
            color="#343A35",
            size=13
        ),
        title=dict(
            font=dict(
                family="DM Sans",
                color="#344E41",
                size=19
            )
        ),
        xaxis=dict(
            color="#343A35",
            tickfont=dict(color="#343A35"),
            title_font=dict(color="#344E41"),
            gridcolor="#E1E6DE"
        ),
        yaxis=dict(
            color="#343A35",
            tickfont=dict(color="#343A35"),
            title_font=dict(color="#344E41"),
            gridcolor="#E1E6DE"
        ),
        legend=dict(
            font=dict(color="#343A35")
        ),
        paper_bgcolor="#F6F7F3",
        plot_bgcolor="#FFFFFF"
    )

    px.defaults.template = "tema_viajes"

    # Estilos generales de Streamlit
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp,
    [data-testid="stAppViewContainer"] {
        background-color: #F6F7F3 !important;
        color: #343A35 !important;
    }

    /* Ocultar la franja superior de Streamlit */
    div[data-testid="stDecoration"] {
        display: none !important;
        height: 0 !important;
    }

    /* Encabezado superior transparente */
    header[data-testid="stHeader"] {
        background: transparent !important;
        box-shadow: none !important;
    }

    [data-testid="stToolbar"] {
        background: transparent !important;
    }

    .stAppToolbar {
        background: transparent !important;
    }

    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    .stApp p,
    .stApp label,
    .stApp li {
        color: #343A35;
    }

    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #E7EAE4;
    }

    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label {
        color: #343A35 !important;
    }

    [data-testid="stSidebarNavLink"][aria-current="page"] {
        background-color: #E8EEE6 !important;
        color: #344E41 !important;
        border-radius: 8px;
    }

    h1, h2, h3 {
        color: #344E41 !important;
        font-weight: 700 !important;
    }

    [data-testid="stCaptionContainer"] {
        color: #69736B !important;
    }

    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E7EAE4;
        padding: 18px;
        border-radius: 14px;
    }

    [data-testid="stMetricLabel"] {
        color: #69736B !important;
    }

    [data-testid="stMetricValue"] {
        color: #344E41 !important;
    }

    [data-testid="stSelectbox"] label {
        color: #344E41 !important;
        font-weight: 600;
    }

    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border: 1px solid #DCE3DA !important;
        border-radius: 9px;
    }

    div[data-baseweb="select"] input {
        color: #343A35 !important;
    }

    div[data-baseweb="select"] span,
    div[data-baseweb="select"] div {
        color: #343A35 !important;
    }

    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    div[data-baseweb="menu"] {
        background-color: #FFFFFF !important;
    }

    ul[role="listbox"] {
        background-color: #FFFFFF !important;
    }

    li[role="option"] {
        background-color: #FFFFFF !important;
        color: #343A35 !important;
    }

    li[role="option"] * {
        color: #343A35 !important;
    }

    li[role="option"]:hover {
        background-color: #E8EEE6 !important;
    }

    li[role="option"][aria-selected="true"] {
        background-color: #E8EEE6 !important;
        color: #344E41 !important;
    }

    /* Botones: texto blanco en todos sus elementos */
    div.stButton > button {
        background-color: #344E41 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 9px;
        padding: 0.55rem 1.2rem;
        font-weight: 600;
    }

    div.stButton > button p,
    div.stButton > button span,
    div.stButton > button div {
        color: #FFFFFF !important;
    }

    div.stButton > button:hover {
        background-color: #426653 !important;
        color: #FFFFFF !important;
    }

    div.stButton > button:hover p,
    div.stButton > button:hover span,
    div.stButton > button:hover div {
        color: #FFFFFF !important;
    }

    [data-testid="stAlert"] {
        background-color: #FFFFFF !important;
        color: #343A35 !important;
        border: 1px solid #E7EAE4;
        border-radius: 12px;
    }

    [data-testid="stAlert"] p {
        color: #343A35 !important;
    }

    [data-testid="stSlider"] label {
        color: #344E41 !important;
        font-weight: 600;
    }

    [data-testid="stSlider"] [role="slider"] {
        background-color: #426653 !important;
    }

    hr {
        border-color: #E1E6DE !important;
    }
    </style>
    """, unsafe_allow_html=True)
