import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from db import run_query

st.title("🗺️ Mapa de sismos")
st.markdown(
    "Cada punto representa un evento sísmico de Silver. El tamaño indica la "
    "magnitud y el color la profundidad en kilómetros."
)

try:
    mapa = run_query("""
        SELECT sismo_id, fecha_evento, magnitud, profundidad_km,
               latitud, longitud, tsunami, zona_reportada
        FROM gold.v_mapa_sismos
        ORDER BY fecha_evento DESC
    """)
except Exception as exc:
    st.error(f"No se pudo consultar la vista del mapa: {exc}")
    st.stop()

if mapa.empty:
    st.info("No hay sismos Gold para ubicar en el mapa.")
    st.stop()

limite = st.slider(
    "Eventos más recientes a mostrar",
    min_value=500,
    max_value=min(9500, max(500, len(mapa))),
    value=min(3000, max(500, len(mapa))),
    step=500,
)
mapa = mapa.head(limite)
mapa["dia"] = (
    pd.to_datetime(mapa["fecha_evento"], utc=True)
    .dt.strftime("%Y-%m-%d")
)
total_eventos = len(mapa)
magnitud_maxima = mapa["magnitud"].max()
profundidad_promedio = mapa["profundidad_km"].mean()
mapa["profundidad_km"] = mapa["profundidad_km"].fillna(0)
mapa["magnitud_marcador"] = mapa["magnitud"].clip(lower=0.1)


# Preparar los días en orden cronológico
mapa["fecha_evento"] = pd.to_datetime(mapa["fecha_evento"], utc=True)
mapa["dia"] = mapa["fecha_evento"].dt.strftime("%Y-%m-%d")

dias = sorted(mapa["dia"].dropna().unique())

# Preparar los datos para cada día
datos_por_dia = {
    dia: mapa[mapa["dia"] == dia].copy()
    for dia in dias
}

def crear_traza(datos, opacidad):
    return go.Scattergeo(
        lat=datos["latitud"],
        lon=datos["longitud"],
        mode="markers",
        text=datos["zona_reportada"],
        customdata=datos[
            ["sismo_id", "fecha_evento", "magnitud",
             "profundidad_km", "tsunami"]
        ].to_numpy(),
        marker=dict(
            size=datos["magnitud_marcador"] * 2 + 5,
            sizemode="diameter",
            sizeref=1,
            sizemin=4,
            color=datos["profundidad_km"],
            colorscale="Viridis",
            cmin=0,
            opacity=opacidad,
            colorbar=dict(title="Profundidad (km)")
        ),
        hovertemplate=(
            "<b>%{text}</b><br>"
            "ID: %{customdata[0]}<br>"
            "Fecha: %{customdata[1]}<br>"
            "Magnitud: %{customdata[2]:.1f}<br>"
            "Profundidad: %{customdata[3]:.1f} km<br>"
            "Indicador tsunami: %{customdata[4]}"
            "<extra></extra>"
        )
    )

# Crear la figura inicial
fig = go.Figure(
    data=[crear_traza(datos_por_dia[dias[0]], 0.85)]
)

frames = []
ultimo_frame_por_dia = {}

# Crear los fotogramas intermedios de fade-out / fade-in
for i in range(1, len(dias)):
    dia_anterior = dias[i - 1]
    dia_actual = dias[i]

    # Desvanecer los puntos del día anterior
    for opacidad in [0.55, 0.25, 0.05]:
        nombre = f"{dia_anterior}_salida_{opacidad}"

        frames.append(
            go.Frame(
                name=nombre,
                data=[crear_traza(datos_por_dia[dia_anterior], opacidad)],
                traces=[0]
            )
        )

    # Hacer aparecer los puntos del día siguiente
    for opacidad in [0.25, 0.55, 0.85]:
        nombre = f"{dia_actual}_entrada_{opacidad}"

        frames.append(
            go.Frame(
                name=nombre,
                data=[crear_traza(datos_por_dia[dia_actual], opacidad)],
                traces=[0]
            )
        )

    ultimo_frame_por_dia[dia_actual] = nombre

# Registrar los fotogramas
fig.frames = frames

# Configurar el mapa
fig.update_geos(
    showland=True,
    landcolor="rgb(243, 243, 243)",
    projection_type="natural earth"
)

# Controles de reproducción y pausa
fig.update_layout(
    title=f"Actividad sísmica: {dias[0]}",
    margin={"r": 0, "t": 50, "l": 0, "b": 0},
    updatemenus=[
    dict(
        type="buttons",
        direction="right",
        showactive=False,
        buttons=[
            dict(
                label="▶ Reproducir",
                method="animate",
                args=[
                    None,
                    {
                        "frame": {"duration": 240, "redraw": True},
                        "transition": {"duration": 0},
                        "fromcurrent": True,
                        "mode": "immediate"
                    }
                ]
            ),
            dict(
                label="⏸ Pausar",
                method="animate",
                args=[
                    [None],
                    {
                        "frame": {"duration": 0, "redraw": False},
                        "mode": "immediate",
                        "transition": {"duration": 0}
                    }
                ]
            )
        ],
        x=0.6,
        y=1.16,
        xanchor="center",
        yanchor="top"
    )
],
    sliders=[
        dict(
            active=0,
            currentvalue={"prefix": "Día: "},
            steps=[
                dict(
                    label=dia,
                    method="animate",
                    args=[
                        [ultimo_frame_por_dia.get(dia, frames[0].name if frames else "")],
                        {
                            "frame": {"duration": 0, "redraw": True},
                            "mode": "immediate",
                            "transition": {"duration": 0}
                        }
                    ]
                )
                for dia in dias
            ]
        )
    ]
)

st.plotly_chart(fig, use_container_width=True)


st.subheader("Conclusión")

st.markdown(
    f"""
    Se muestran **{total_eventos:,} eventos sísmicos**.
    La magnitud máxima registrada entre los eventos visualizados fue
    **{magnitud_maxima:.1f}** y la profundidad promedio fue de
    **{profundidad_promedio:.1f} km**.

    El mapa permite observar la distribución geográfica de los eventos,
    pero no representa riesgo ni predice futuros sismos.
    """
)
