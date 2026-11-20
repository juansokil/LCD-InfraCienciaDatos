"""
Estilo comun de los graficos (plotly) para que todo el tablero se lea igual.

Reglas que seguimos:
- Un eje por grafico (nunca dos escalas Y en el mismo grafico).
- Magnitud es un ORDEN -> una sola familia de azules, mas claro = mas fuerte
  (el fondo es oscuro: lo que mas importa es lo que mas brilla).
- Grilla y ejes discretos; el dato es lo que resalta.
"""

import plotly.graph_objects as go

SUPERFICIE = "#1a1a19"
TINTA = "#f0efec"
TINTA_2 = "#c3c2b7"
TINTA_MUTED = "#898781"
GRILLA = "#2c2c2a"
EJE = "#383835"
AZUL = "#3987e5"          # serie principal
NARANJA = "#d95926"       # segunda serie (cuando hace falta destacar algo)

# Escala ordinal de azules para las 7 categorias de magnitud (oscuro -> claro)
AZULES_MAGNITUD = ["#184f95", "#1c5cab", "#256abf", "#3987e5",
                   "#6da7ec", "#9ec5f4", "#cde2fb"]
ESCALA_CONTINUA = [[0.0, "#184f95"], [0.5, "#3987e5"], [1.0, "#cde2fb"]]

ORDEN_MAGNITUD = ["Micro", "Menor", "Ligero", "Moderado", "Fuerte", "Mayor", "Gran sismo"]
COLOR_MAGNITUD = dict(zip(ORDEN_MAGNITUD, AZULES_MAGNITUD))


def estilo(fig: go.Figure, alto: int = 360, leyenda: bool = False) -> go.Figure:
    fig.update_layout(
        height=alto,
        margin=dict(l=8, r=8, t=36, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif",
                  color=TINTA_2, size=13),
        title_font=dict(color=TINTA, size=15),
        showlegend=leyenda,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(color=TINTA_2)),
        hoverlabel=dict(bgcolor=SUPERFICIE, bordercolor=EJE,
                        font=dict(color=TINTA)),
        barcornerradius=4,
        bargap=0.25,
    )
    fig.update_xaxes(gridcolor=GRILLA, linecolor=EJE, zeroline=False,
                     tickfont=dict(color=TINTA_MUTED))
    fig.update_yaxes(gridcolor=GRILLA, linecolor=EJE, zeroline=False,
                     tickfont=dict(color=TINTA_MUTED))
    fig.update_traces(selector=dict(type="bar"),
                      marker_line_color=SUPERFICIE, marker_line_width=2)
    return fig


def mapa_base(fig: go.Figure, alto: int = 520, alcance: str = "world") -> go.Figure:
    fig.update_geos(
        scope=alcance,
        projection_type="natural earth",
        showland=True, landcolor="#24241f",
        showocean=True, oceancolor="#121211",
        showcountries=True, countrycolor="#3a3a35",
        showcoastlines=True, coastlinecolor="#4a4a44",
        showframe=False, bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(height=alto, margin=dict(l=0, r=0, t=10, b=0),
                      paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=TINTA_2),
                      hoverlabel=dict(bgcolor=SUPERFICIE, bordercolor=EJE,
                                      font=dict(color=TINTA)))
    return fig
