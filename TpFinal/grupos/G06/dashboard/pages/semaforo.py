
# G06 - Semáforo del Viajero
# Visualización de condiciones climáticas históricas.
# Versión de demostración con datos ficticios.
# La versión final consultará la capa Gold del warehouse.

import streamlit as st
import pandas as pd
import plotly.express as px


# ESTILO VISUAL

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

    [data-testid="stMetric"] {
        background-color: #F2EFE7;
        border: 1px solid #D2CCBD;
        padding: 18px;
        border-radius: 12px;
    }

    [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] {
        color: #35513D !important;
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

    [data-testid="stSelectbox"] label {
        color: #35513D !important;
        font-weight: 600;
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


# ENCABEZADO

st.title("🌿 Semáforo del Viajero")
st.caption("TP Final G06 - Infraestructura para Ciencia de Datos")

st.markdown(
    "Consultá las condiciones climáticas históricas de tu próximo destino."
)
st.divider()


# SELECCIÓN DE DESTINO

st.subheader("Seleccioná tu destino")

destinos = {
    "Noroeste": ["Purmamarca"],
    "Patagonia": ["Bariloche"],
    "Noreste": ["Puerto Iguazú"]
}

col1, col2, col3 = st.columns(3)

with col1:
    region = st.selectbox("Región", list(destinos.keys()))

with col2:
    ciudad = st.selectbox("Destino", destinos[region])

with col3:
    temporada = st.selectbox(
        "Temporada",
        ["Verano", "Otoño", "Invierno", "Primavera"]
    )

anio = st.selectbox("Año", [2021, 2022, 2023, 2024, 2025])

consultar = st.button(
    "🔎 Consultar destino",
    type="primary",
    use_container_width=True
)

if consultar:
    st.session_state["consulta_realizada"] = {
        "region": region,
        "ciudad": ciudad,
        "temporada": temporada,
        "anio": anio
    }

st.divider()


# DATOS DE DEMOSTRACIÓN

resultados_demo = {
    ("Noroeste", "Verano"): ("FAVORABLE", "#477A50", "Las condiciones son favorables según esta demostración.", "Podés planificar actividades al aire libre."),
    ("Noroeste", "Otoño"): ("FAVORABLE", "#477A50", "Las condiciones son favorables según esta demostración.", "Es una buena oportunidad para recorrer el destino."),
    ("Noroeste", "Invierno"): ("PRECAUCIÓN", "#B28A36", "Se recomienda revisar las condiciones climáticas.", "Consultá las temperaturas antes de organizar actividades."),
    ("Noroeste", "Primavera"): ("FAVORABLE", "#477A50", "Las condiciones son favorables según esta demostración.", "Podés planificar actividades al aire libre."),

    ("Patagonia", "Verano"): ("FAVORABLE", "#477A50", "Las condiciones son favorables según esta demostración.", "Podés aprovechar la temporada para visitar el destino."),
    ("Patagonia", "Otoño"): ("PRECAUCIÓN", "#B28A36", "Se recomienda revisar las condiciones climáticas.", "Considerá llevar ropa adecuada para temperaturas variables."),
    ("Patagonia", "Invierno"): ("DESFAVORABLE", "#B6534B", "Las condiciones podrían ser poco favorables.", "Revisá las condiciones meteorológicas antes de viajar."),
    ("Patagonia", "Primavera"): ("PRECAUCIÓN", "#B28A36", "Se recomienda revisar las condiciones climáticas.", "Consultá las condiciones antes de realizar actividades."),

    ("Noreste", "Verano"): ("PRECAUCIÓN", "#B28A36", "Se recomienda revisar las condiciones climáticas.", "Tené en cuenta las temperaturas y las precipitaciones."),
    ("Noreste", "Otoño"): ("FAVORABLE", "#477A50", "Las condiciones son favorables según esta demostración.", "Podés organizar tu visita con normalidad."),
    ("Noreste", "Invierno"): ("DESFAVORABLE", "#B6534B", "Las condiciones podrían ser poco favorables.", "Se recomienda evaluar las condiciones antes de viajar."),
    ("Noreste", "Primavera"): ("FAVORABLE", "#477A50", "Las condiciones son favorables según esta demostración.", "Podés planificar actividades al aire libre.")
}

indicadores_demo = {
    ("Noroeste", "Verano"): (25, 32, 120, 8.5),
    ("Noroeste", "Otoño"): (19, 26, 60, 7.0),
    ("Noroeste", "Invierno"): (12, 21, 15, 7.5),
    ("Noroeste", "Primavera"): (21, 29, 80, 8.0),

    ("Patagonia", "Verano"): (18, 25, 65, 9.0),
    ("Patagonia", "Otoño"): (12, 18, 45, 6.5),
    ("Patagonia", "Invierno"): (3, 9, 35, 5.0),
    ("Patagonia", "Primavera"): (13, 20, 50, 7.5),

    ("Noreste", "Verano"): (27, 34, 180, 8.0),
    ("Noreste", "Otoño"): (23, 29, 100, 7.0),
    ("Noreste", "Invierno"): (17, 24, 70, 7.5),
    ("Noreste", "Primavera"): (24, 31, 130, 8.0)
}

precipitaciones_demo = {
    "Noroeste": [120, 110, 95, 60, 30, 15, 10, 15, 25, 45, 80, 105],
    "Patagonia": [60, 55, 50, 45, 40, 35, 30, 35, 40, 50, 55, 65],
    "Noreste": [180, 170, 150, 120, 90, 70, 60, 75, 100, 130, 160, 190]
}


# RESULTADO DEL SEMÁFORO

st.subheader("Resultado del Semáforo")

if "consulta_realizada" in st.session_state:

    consulta = st.session_state["consulta_realizada"]
    clave = (consulta["region"], consulta["temporada"])

    estado, color, descripcion, recomendacion = resultados_demo[clave]

    st.info(f"💡 Recomendación: {recomendacion}")

    st.caption(
        f"Destino: {consulta['ciudad']} | "
        f"Temporada: {consulta['temporada']} | "
        f"Año: {consulta['anio']}"
    )

    st.markdown(f"""
    <div style="
        background-color: #F2EFE7;
        border: 1px solid #D2CCBD;
        border-left: 8px solid {color};
        padding: 24px;
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(53, 81, 61, 0.08);
    ">
        <h2 style="color: {color}; margin: 0;">
            ● {estado}
        </h2>
        <p style="color: #343C32 !important;">
            {descripcion}
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.caption(
        "DEMO: clasificación ficticia, no basada en datos meteorológicos."
    )

else:
    st.info("Seleccioná los filtros y presioná «Consultar destino».")


# INDICADORES CLIMÁTICOS

st.subheader("Indicadores Climáticos")

if "consulta_realizada" in st.session_state:

    consulta = st.session_state["consulta_realizada"]
    clave = (consulta["region"], consulta["temporada"])

    temp_media, temp_max, precipitaciones, horas_luz = indicadores_demo[clave]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Temperatura media", f"{temp_media} °C")
    col2.metric("Temperatura máxima", f"{temp_max} °C")
    col3.metric("Precipitaciones", f"{precipitaciones} mm")
    col4.metric("Horas de luz", f"{horas_luz} h")

    st.caption(
        "DEMO: valores ficticios, no representan datos meteorológicos reales."
    )

else:
    st.info("Los indicadores aparecerán después de consultar un destino.")


# HISTÓRICO CLIMÁTICO

st.subheader("Comportamiento histórico")

if "consulta_realizada" in st.session_state:

    consulta = st.session_state["consulta_realizada"]

    meses = [
        "Enero", "Febrero", "Marzo", "Abril",
        "Mayo", "Junio", "Julio", "Agosto",
        "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    datos = pd.DataFrame({
        "Mes": meses,
        "Precipitaciones (mm)": precipitaciones_demo[consulta["region"]]
    })

    fig = px.bar(
        datos,
        x="Mes",
        y="Precipitaciones (mm)",
        title=f"Precipitaciones mensuales — {consulta['ciudad']} ({consulta['anio']})"
    )

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
        xaxis=dict(
            title_font=dict(color="#35513D"),
            tickfont=dict(color="#343C32", size=12),
            showgrid=False,
            linecolor="#BEB8A9"
        ),
        yaxis=dict(
            title_font=dict(color="#35513D"),
            tickfont=dict(color="#343C32", size=12),
            gridcolor="#D2CCBD",
            linecolor="#BEB8A9"
        ),
        margin=dict(b=80, t=65)
    )

    fig.update_traces(
        marker_color="#75866A",
        marker_line_color="#526B50",
        marker_line_width=1
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "DEMO: datos ficticios con fines de visualización."
    )

else:
    st.info("El gráfico aparecerá después de consultar un destino.")

