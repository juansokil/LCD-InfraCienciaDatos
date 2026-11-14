
# g06_dashboard_historico — análisis histórico del clima.
# Permite visualizar el comportamiento de las variables meteorológicas de los destinos seleccionados durante el período histórico disponible.

# Presenta gráficos comparativos para facilitar la identificación de patrones y variaciones climáticas.

# Por ahora utiliza datos de ejemplo para probar la interfaz.
# La versión final consultará la información procesada en Gold.

import streamlit as st
import pandas as pd
import plotly.express as px


# TEMA VISUAL — PALETA NATURAL

st.markdown("""
<style>
    .stApp {
        background-color: #EAE5D9;
        color: #343C32;
    }

    h1, h2, h3 {
        color: #35513D !important;
    }

    p, label, [data-testid="stCaptionContainer"] {
        color: #454B42 !important;
    }

    [data-testid="stSelectbox"] label,
    [data-testid="stSlider"] label {
        color: #35513D !important;
        font-weight: 600;
    }

    div.stButton > button {
        background-color: #526B50;
        color: #FFFFFF !important;
        border: none;
        border-radius: 9px;
        font-weight: 600;
    }

    div.stButton > button:hover {
        background-color: #35513D;
        color: #FFFFFF !important;
    }

    [data-testid="stAlert"] {
        background-color: #F2EFE7;
        color: #343C32;
        border-radius: 10px;
    }

    hr {
        border-color: #D2CCBD;
    }
</style>
""", unsafe_allow_html=True)


# PRESENTACIÓN

st.title(" Análisis histórico del clima")

st.markdown("""
Esta sección permite explorar el comportamiento histórico
de las variables meteorológicas en los destinos seleccionados.

A través de gráficos y filtros se busca identificar
patrones y variaciones climáticas a lo largo del tiempo.
""")

st.divider()


# FILTROS

st.subheader("Seleccioná los parámetros de consulta")

destinos = {
    "Noroeste": ["Purmamarca"],
    "Patagonia": ["Bariloche"],
    "Noreste": ["Puerto Iguazú"]
}

col1, col2 = st.columns(2)

with col1:
    region = st.selectbox(
        "Región",
        list(destinos.keys())
    )

with col2:
    ciudad = st.selectbox(
        "Destino",
        destinos[region]
    )

anio_inicio, anio_fin = st.select_slider(
    "Período de análisis",
    options=[2021, 2022, 2023, 2024, 2025],
    value=(2021, 2025)
)

consultar = st.button(
    "🔎 Consultar histórico",
    type="primary",
    use_container_width=True
)

st.divider()


# VISUALIZACIÓN HISTÓRICA

st.subheader("Comportamiento de las precipitaciones")

if consultar:

    # Datos ficticios para probar el diseño.
    # Se reemplazarán por las consultas reales a Gold.

    datos_demo = pd.DataFrame({
        "Año": [
            2021, 2021, 2022, 2022, 2023,
            2023, 2024, 2024, 2025, 2025
        ],
        "Mes": [
            "Enero", "Julio", "Enero", "Julio",
            "Enero", "Julio", "Enero", "Julio",
            "Enero", "Julio"
        ],
        "Precipitaciones": [
            120, 20, 110, 25, 130,
            18, 115, 30, 125, 22
        ]
    })

    # Filtramos los datos según el período seleccionado.

    datos = datos_demo[
        (datos_demo["Año"] >= anio_inicio) &
        (datos_demo["Año"] <= anio_fin)
    ]

    fig = px.line(
        datos,
        x="Año",
        y="Precipitaciones",
        color="Mes",
        markers=True,
        title=f"Precipitaciones históricas — {ciudad}",
        labels={
            "Año": "Año",
            "Precipitaciones": "Precipitaciones (mm)",
            "Mes": "Mes"
        }
    )

    # ESTILO DEL GRÁFICO

    fig.update_layout(
        paper_bgcolor="#EAE5D9",
        plot_bgcolor="#F2EFE7",
        font=dict(
            family="Arial",
            size=13,
            color="#343C32"
        ),
        title_font=dict(
            family="Arial",
            size=20,
            color="#35513D"
        ),
        legend=dict(
            font=dict(color="#343C32"),
            title_font=dict(color="#35513D")
        ),
        xaxis=dict(
            title_font=dict(color="#35513D"),
            tickfont=dict(color="#343C32", size=12),
            showgrid=False,
            linecolor="#BEB8A9",
            automargin=True
        ),
        yaxis=dict(
            title_font=dict(color="#35513D"),
            tickfont=dict(color="#343C32", size=12),
            gridcolor="#D2CCBD",
            linecolor="#BEB8A9",
            automargin=True
        ),
        margin=dict(b=60, t=65)
    )

    fig.update_traces(
        line=dict(color="#75866A", width=3),
        marker=dict(
            size=9,
            color="#526B50",
            line=dict(color="#F2EFE7", width=1)
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "DEMO: datos ficticios utilizados para probar "
        "la visualización. No representan registros reales."
    )

else:
    st.info(
        "Seleccioná el destino y el período para consultar "
        "el comportamiento histórico."
    )
