"""
Dashboard G09 - Clima en la provincia de Buenos Aires.

Lee únicamente la capa Gold:
    gold.v_clima_diario
    (vista sobre fact_clima_horario y dimensiones del modelo estrella).
"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="G09 - Clima PBA", layout="wide")

# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------
URL = (
    f"postgresql+psycopg2://{os.environ['SOURCE_DB_USER']}:{os.environ['SOURCE_DB_PASS']}"
    f"@{os.environ.get('SOURCE_DB_HOST', 'data_warehouse')}:{os.environ.get('SOURCE_DB_PORT', '5432')}"
    f"/{os.environ['SOURCE_DB_NAME']}"
)
engine = create_engine(URL)

# ---------------------------------------------------------------------------
# Constantes de diseño
# ---------------------------------------------------------------------------
# El color sigue a la ciudad, nunca a su posición: filtrar no repinta las series.
# Primeros 3 slots de la paleta categórica validada (seguros para daltonismo).
COLOR_CIUDAD = {
    "Mar del Plata": "#2a78d6",
    "Tandil": "#eb6834",
    "Bahía Blanca": "#1baf7a",
}
# Codificación secundaria: el tipo de línea también identifica a la ciudad.
TRAZO_CIUDAD = {"Mar del Plata": "solid", "Tandil": "dash", "Bahía Blanca": "dot"}
ORDEN_CIUDADES = list(COLOR_CIUDAD)

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

FUENTE = "Fira Sans, sans-serif"
TEXTO = "#0F172A"
TEXTO_SECUNDARIO = "#475569"
GRILLA = "#E2E8F0"


def num(valor: float, decimales: int = 1) -> str:
    """Formatea un número con coma decimal y punto de miles (es-AR)."""
    s = f"{valor:,.{decimales}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def fecha(valor) -> str:
    return pd.Timestamp(valor).strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def cargar_gold() -> pd.DataFrame:
    consulta = text("""
        SELECT
            fecha,
            EXTRACT(YEAR FROM fecha)::int AS anio,
            EXTRACT(MONTH FROM fecha)::int AS mes,
            ciudad,
            region,
            temp_media_c,
            temp_max_c,
            temp_min_c,
            lluvia_mm,
            viento_medio_kmh AS viento_kmh,
            horas_medidas,
            horas_pronostico,
            tipo_dia
        FROM gold.v_clima_diario
        ORDER BY fecha, ciudad
    """)

    with engine.connect() as conn:
        df = pd.read_sql(consulta, conn)

    df["fecha"] = pd.to_datetime(df["fecha"])

    for col in ["anio", "mes"]:
        df[col] = df[col].astype(int)

    columnas_numericas = [
        "temp_media_c", "temp_max_c", "temp_min_c",
        "lluvia_mm", "viento_kmh"
    ]

    for col in columnas_numericas:
        df[col] = df[col].astype(float)

    return df


try:
    datos = cargar_gold()
except Exception as error:  # la tabla aún no existe o la base no responde
    st.title("Clima en la provincia de Buenos Aires")
    st.info(
        "Todavía no hay datos en la capa Gold. Esperá a que Airflow termine el pipeline "
        "(Bronze → Silver → Gold) y recargá la página."
    )
    with st.expander("Detalle técnico"):
        st.code(str(error))
    st.stop()

if datos.empty:
    st.info("La capa Gold existe pero está vacía. Revisá las corridas en Airflow.")
    st.stop()


# ---------------------------------------------------------------------------
# Estilo común de los gráficos
# ---------------------------------------------------------------------------
def estilo(fig: go.Figure, titulo_y: str, alto: int = 360) -> go.Figure:
    fig.update_layout(
        height=alto,
        margin=dict(l=8, r=8, t=8, b=8),
        font=dict(family=FUENTE, size=13, color=TEXTO),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        separators=",.",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            title_text="", font=dict(size=13),
        ),
        hoverlabel=dict(font_family=FUENTE, bgcolor="white", bordercolor=GRILLA),
        barcornerradius=4,
        bargap=0.25,
        bargroupgap=0.08,
    )
    fig.update_xaxes(
        title_text="", showgrid=False, linecolor=GRILLA,
        tickfont=dict(color=TEXTO_SECUNDARIO),
    )
    fig.update_yaxes(
        title_text=titulo_y, title_font=dict(color=TEXTO_SECUNDARIO, size=12),
        gridcolor=GRILLA, zeroline=False, tickfont=dict(color=TEXTO_SECUNDARIO),
    )
    return fig


def lineas(fig: go.Figure) -> go.Figure:
    """Líneas finas de 2px con el trazo de cada ciudad."""
    for traza in fig.data:
        traza.line.width = 2
        traza.line.dash = TRAZO_CIUDAD.get(traza.name, "solid")
    return fig


CONFIG_PLOTLY = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def mostrar(fig: go.Figure) -> None:
    st.plotly_chart(fig, use_container_width=True, config=CONFIG_PLOTLY)


# ---------------------------------------------------------------------------
# Encabezado y filtros
# ---------------------------------------------------------------------------
fecha_min = datos["fecha"].min().date()
fecha_max = datos["fecha"].max().date()

st.title("Clima en la provincia de Buenos Aires")
st.caption(
    f"Costa, interior y sur bonaerense · datos meteorológicos de Open-Meteo "
    f"del {fecha(fecha_min)} al {fecha(fecha_max)} · "
    "históricos y pronósticos según disponibilidad."
)

f1, f2, f3, f4 = st.columns([3, 3, 1.3, 1.3], vertical_alignment="bottom")
with f1:
    ciudades = st.multiselect(
        "Ciudades",
        ORDEN_CIUDADES,
        default=ORDEN_CIUDADES,
    )
with f2:
    rango = st.slider(
        "Período",
        min_value=fecha_min,
        max_value=fecha_max,
        value=(fecha_min, fecha_max),
        format="DD/MM/YYYY",
    )
with f3:
    umbral_calor = st.number_input(
        "Calor extremo (°C)", value=35.0, step=1.0, format="%.0f",
        help="Un día cuenta como calor extremo si su máxima es igual o mayor a este valor.",
    )
with f4:
    umbral_frio = st.number_input(
        "Helada (°C)", value=0.0, step=1.0, format="%.0f",
        help="Un día cuenta como helada si su mínima es igual o menor a este valor.",
    )

if not ciudades:
    st.warning("Elegí al menos una ciudad para ver los datos.")
    st.stop()

desde, hasta = pd.Timestamp(rango[0]), pd.Timestamp(rango[1])
df = datos[datos["ciudad"].isin(ciudades) & datos["fecha"].between(desde, hasta)].copy()
if df.empty:
    st.warning("No hay datos para ese período.")
    st.stop()

ciudades = [c for c in ORDEN_CIUDADES if c in ciudades]
df["calor_extremo"] = df["temp_max_c"] >= umbral_calor
df["helada"] = df["temp_min_c"] <= umbral_frio
anios_periodo = (hasta - desde).days / 365.25 + 1 / 365.25

# ---------------------------------------------------------------------------
# Indicadores por ciudad
# ---------------------------------------------------------------------------
tarjetas = st.columns(len(ciudades))
for col, ciudad in zip(tarjetas, ciudades):
    d = df[df["ciudad"] == ciudad]
    fila_max = d.loc[d["temp_max_c"].idxmax()]
    fila_min = d.loc[d["temp_min_c"].idxmin()]
    lluvia_anual = d["lluvia_mm"].sum() / max(anios_periodo, 1 / 365.25)
    with col.container(border=True):
        st.markdown(
            f"<span style='display:inline-block;width:12px;height:12px;border-radius:3px;"
            f"background:{COLOR_CIUDAD[ciudad]};margin-right:8px;vertical-align:middle'></span>"
            f"**{ciudad}** <span style='color:{TEXTO_SECUNDARIO}'>· "
            f"{d['region'].iat[0]}</span>",
            unsafe_allow_html=True,
        )
        a, b = st.columns(2)
        a.metric("Temp. media", f"{num(d['temp_media_c'].mean())} °C")
        b.metric(
            "Lluvia por año" if anios_periodo >= 1 else "Lluvia total",
            f"{num(lluvia_anual if anios_periodo >= 1 else d['lluvia_mm'].sum(), 0)} mm",
        )
        a, b = st.columns(2)
        a.metric("Máxima récord", f"{num(fila_max['temp_max_c'])} °C",
                 help=f"Registrada el {fecha(fila_max['fecha'])}")
        b.metric("Mínima récord", f"{num(fila_min['temp_min_c'])} °C",
                 help=f"Registrada el {fecha(fila_min['fecha'])}")
        st.caption(
            f"{fecha(fila_max['fecha'])} (máx.) · {fecha(fila_min['fecha'])} (mín.)"
        )

st.write("")
tab_temp, tab_lluvia, tab_alertas, tab_datos = st.tabs(
    ["Temperatura", "Lluvia y viento", "Alertas extremas", "Datos"]
)

# ---------------------------------------------------------------------------
# Temperatura
# ---------------------------------------------------------------------------
with tab_temp:
    st.subheader("Evolución de la temperatura media mensual")
    mensual = (
        df.set_index("fecha")
        .groupby("ciudad")["temp_media_c"]
        .resample("MS")
        .mean()
        .reset_index()
    )
    mensual["ciudad"] = pd.Categorical(mensual["ciudad"], ORDEN_CIUDADES, ordered=True)
    mensual = mensual.sort_values(["ciudad", "fecha"])
    fig = px.line(
        mensual, x="fecha", y="temp_media_c", color="ciudad",
        color_discrete_map=COLOR_CIUDAD, category_orders={"ciudad": ciudades},
    )
    fig.update_traces(hovertemplate="%{fullData.name}: %{y:.1f} °C<extra></extra>")
    fig = estilo(lineas(fig), "Temperatura media (°C)", alto=380)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(hoverformat="%m/%Y")
    mostrar(fig)

    st.subheader("Ciclo anual: cómo cambia cada ciudad según el mes")
    st.caption(
        "Temperatura media de cada mes del año dentro del período elegido. "
        "Al pasar el mouse se ven también la máxima y la mínima promedio."
    )
    clima = (
        df.groupby(["ciudad", "mes"])[["temp_media_c", "temp_max_c", "temp_min_c"]]
        .mean()
        .reset_index()
    )
    clima["mes_nombre"] = clima["mes"].map(lambda m: MESES[m - 1])
    fig = go.Figure()
    for ciudad in ciudades:
        c = clima[clima["ciudad"] == ciudad].sort_values("mes")
        color = COLOR_CIUDAD[ciudad]
        fig.add_trace(go.Scatter(
            x=c["mes_nombre"], y=c["temp_media_c"], name=ciudad,
            mode="lines+markers", line=dict(color=color, width=2, dash=TRAZO_CIUDAD[ciudad]),
            marker=dict(size=8, line=dict(color="white", width=2)),
            customdata=c[["temp_max_c", "temp_min_c"]],
            hovertemplate=(
                "%{fullData.name}: %{y:.1f} °C "
                "(máx. %{customdata[0]:.1f} · mín. %{customdata[1]:.1f})<extra></extra>"
            ),
        ))
    fig = estilo(fig, "Temperatura (°C)", alto=380)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(categoryorder="array", categoryarray=MESES)
    mostrar(fig)

# ---------------------------------------------------------------------------
# Lluvia y viento
# ---------------------------------------------------------------------------
with tab_lluvia:
    izq, der = st.columns(2, gap="large")

    with izq:
        st.subheader("Lluvia acumulada por año")
        anual = df.groupby(["anio", "ciudad"])["lluvia_mm"].sum().reset_index()
        fig = px.bar(
            anual, x="anio", y="lluvia_mm", color="ciudad", barmode="group",
            color_discrete_map=COLOR_CIUDAD, category_orders={"ciudad": ciudades},
        )
        fig.update_traces(
            marker_line_color="white", marker_line_width=1,
            hovertemplate="%{fullData.name} · %{x}: %{y:,.0f} mm<extra></extra>",
        )
        fig = estilo(fig, "Lluvia (mm)")
        fig.update_xaxes(dtick=1, type="category")
        mostrar(fig)
        incompletos = [
            str(a) for a, g in df.groupby("anio")
            if g["fecha"].min() > pd.Timestamp(a, 1, 1) or g["fecha"].max() < pd.Timestamp(a, 12, 31)
        ]
        if incompletos:
            st.caption(
                "Años con datos parciales en el período elegido: " + ", ".join(incompletos) + "."
            )

    with der:
        st.subheader("Viento medio según el mes del año")
        viento = df.groupby(["ciudad", "mes"])["viento_kmh"].mean().reset_index()
        viento["mes_nombre"] = viento["mes"].map(lambda m: MESES[m - 1])
        viento = viento.sort_values(["ciudad", "mes"])
        fig = px.line(
            viento, x="mes_nombre", y="viento_kmh", color="ciudad", markers=True,
            color_discrete_map=COLOR_CIUDAD, category_orders={"ciudad": ciudades},
        )
        fig.update_traces(
            marker=dict(size=8, line=dict(color="white", width=2)),
            hovertemplate="%{fullData.name}: %{y:.1f} km/h<extra></extra>",
        )
        fig = estilo(lineas(fig), "Viento medio (km/h)")
        fig.update_layout(hovermode="x unified")
        fig.update_xaxes(categoryorder="array", categoryarray=MESES)
        mostrar(fig)

    st.subheader("Lluvia media según el mes del año")
    lluvia_mes = (
        df.groupby(["ciudad", "anio", "mes"])["lluvia_mm"].sum()
        .groupby(["ciudad", "mes"]).mean().reset_index()
    )
    lluvia_mes["mes_nombre"] = lluvia_mes["mes"].map(lambda m: MESES[m - 1])
    fig = px.bar(
        lluvia_mes.sort_values("mes"), x="mes_nombre", y="lluvia_mm", color="ciudad",
        barmode="group", color_discrete_map=COLOR_CIUDAD, category_orders={"ciudad": ciudades},
    )
    fig.update_traces(
        marker_line_color="white", marker_line_width=1,
        hovertemplate="%{fullData.name} · %{x}: %{y:.0f} mm<extra></extra>",
    )
    fig = estilo(fig, "Lluvia por mes (mm)", alto=320)
    fig.update_xaxes(categoryorder="array", categoryarray=MESES)
    mostrar(fig)


# ---------------------------------------------------------------------------
# Alertas de temperaturas extremas
# ---------------------------------------------------------------------------
with tab_alertas:
    st.caption(
        f"Calor extremo: máxima de {num(umbral_calor)} °C o más · "
        f"Helada: mínima de {num(umbral_frio)} °C o menos. "
        "Los umbrales se cambian en los filtros de arriba."
    )

    # Últimos 7 días históricos disponibles
    historicos = df[df["horas_medidas"] > 0]

    if not historicos.empty:
        ultimo_dia_historico = historicos["fecha"].max()

        recientes = historicos[
            historicos["fecha"] > ultimo_dia_historico - pd.Timedelta(days=7)
        ]

        alertas_recientes = recientes[
            recientes["calor_extremo"] | recientes["helada"]
        ]
    else:
        alertas_recientes = pd.DataFrame()

    if alertas_recientes.empty:
        st.success(
            "Sin alertas en los últimos 7 días históricos disponibles.",
            icon=":material/check_circle:",
        )
    else:
        for _, r in alertas_recientes.sort_values(
            "fecha", ascending=False
        ).iterrows():
            if r["calor_extremo"]:
                st.error(
                    f"**Calor extremo** en {r['ciudad']} el "
                    f"{fecha(r['fecha'])}: máxima de "
                    f"{num(r['temp_max_c'])} °C.",
                    icon=":material/local_fire_department:",
                )

            if r["helada"]:
                st.info(
                    f"**Helada** en {r['ciudad']} el "
                    f"{fecha(r['fecha'])}: mínima de "
                    f"{num(r['temp_min_c'])} °C.",
                    icon=":material/ac_unit:",
                )

    # Resumen por ciudad
    resumen = st.columns(len(ciudades))

    for col, ciudad in zip(resumen, ciudades):
        d = df[df["ciudad"] == ciudad]

        with col.container(border=True):
            st.markdown(f"**{ciudad}**")

            a, b = st.columns(2)
            a.metric("Días de calor extremo", num(d["calor_extremo"].sum(), 0))
            b.metric("Días de helada", num(d["helada"].sum(), 0))

    # Evolución anual
    por_anio = (
        df.groupby(["anio", "ciudad"])[
            ["calor_extremo", "helada"]
        ].sum().reset_index()
    )

    izq, der = st.columns(2, gap="large")

    for contenedor, columna, titulo in [
        (izq, "calor_extremo", "Días de calor extremo por año"),
        (der, "helada", "Días de helada por año"),
    ]:
        with contenedor:
            st.subheader(titulo)

            fig = px.bar(
                por_anio,
                x="anio",
                y=columna,
                color="ciudad",
                barmode="group",
                color_discrete_map=COLOR_CIUDAD,
                category_orders={"ciudad": ciudades},
            )

            fig.update_traces(
                marker_line_color="white",
                marker_line_width=1,
                hovertemplate=(
                    "%{fullData.name} · %{x}: %{y} días<extra></extra>"
                ),
            )

            fig = estilo(fig, "Cantidad de días")
            fig.update_xaxes(dtick=1, type="category")
            mostrar(fig)

    # Días más extremos del período
    st.subheader("Días más extremos del período")

    calor = df.nlargest(10, "temp_max_c").assign(
        tipo="Calor extremo",
        valor=lambda x: x["temp_max_c"],
    )

    frio = df.nsmallest(10, "temp_min_c").assign(
        tipo="Frío extremo",
        valor=lambda x: x["temp_min_c"],
    )

    c1, c2 = st.columns(2, gap="large")

    for contenedor, tabla, etiqueta in [
        (c1, calor, "Las 10 máximas más altas"),
        (c2, frio, "Las 10 mínimas más bajas"),
    ]:
        with contenedor:
            st.markdown(f"**{etiqueta}**")

            st.dataframe(
                tabla[["fecha", "ciudad", "valor", "temp_media_c"]],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "fecha": st.column_config.DateColumn(
                        "Fecha", format="DD/MM/YYYY"
                    ),
                    "ciudad": "Ciudad",
                    "valor": st.column_config.NumberColumn(
                        "Temperatura (°C)", format="%.1f"
                    ),
                    "temp_media_c": st.column_config.NumberColumn(
                        "Media del día (°C)", format="%.1f"
                    ),
                },
            )

# ---------------------------------------------------------------------------
# Datos (vista tabular de todo lo graficado)
# ---------------------------------------------------------------------------
with tab_datos:
    st.caption(
        f"{num(len(df), 0)} filas de gold.v_clima_diario con los filtros aplicados "
        "(una fila por ciudad y día)."
    )
    tabla = df[[
    "fecha", "ciudad", "region", "tipo_dia",
    "temp_media_c", "temp_max_c", "temp_min_c",
    "lluvia_mm", "viento_kmh",
    ]].sort_values(["fecha", "ciudad"], ascending=[False, True])
    st.dataframe(
        tabla,
        hide_index=True,
        use_container_width=True,
        height=460,
        column_config={
            "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "ciudad": "Ciudad",
            "region": "Región",
            "temp_media_c": st.column_config.NumberColumn("Media (°C)", format="%.1f"),
            "temp_max_c": st.column_config.NumberColumn("Máxima (°C)", format="%.1f"),
            "temp_min_c": st.column_config.NumberColumn("Mínima (°C)", format="%.1f"),
            "lluvia_mm": st.column_config.NumberColumn("Lluvia (mm)", format="%.1f"),
            "viento_kmh": st.column_config.NumberColumn("Viento (km/h)", format="%.1f"),
        },
    )
    st.download_button(
        "Descargar CSV",
        tabla.to_csv(index=False).encode("utf-8"),
        file_name="g09_clima_filtrado.csv",
        mime="text/csv",
        icon=":material/download:",
    )
