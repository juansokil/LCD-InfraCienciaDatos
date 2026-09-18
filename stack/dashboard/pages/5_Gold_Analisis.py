"""
Análisis — más allá de la foto: riesgo, correlación y amplitud.

Las páginas anteriores son DESCRIPTIVAS (qué pasó). Esta es ANALÍTICA:
compara activos entre sí y busca estructura en los datos.

Todo se calcula en SQL (gold.v_metricas_riesgo, v_amplitud_mercado,
v_intradia, v_concentracion, v_estacionalidad) con window functions y
agregados — nada de agregar en pandas. pandas solo reordena para dibujar.

La matriz de correlación es la excepción, y a propósito: depende de qué
activos elegiste, así que es una consulta de CONSUMO, no capa semántica.
Sigue calculándose en Postgres con corr(), pero la query vive en esta página.

RESOLUCIÓN: los análisis comparativos usan el grano INTRADÍA (un snapshot
cada 15 minutos), no el cierre diario. Con pocos días de historia una
correlación diaria se calcula sobre 3 puntos; la intradía, sobre ~200. El
pipeline ya recolectaba ese detalle: lo que faltaba era consumirlo.

Lo que sí necesita días (drawdown, amplitud) sigue diciendo cuántos faltan.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from db import run_query
from theme import (aplicar_tema, encabezado, seccion, de_donde_sale,
                   filtro_periodo, where_periodo, layout,
                   PLOTLY, SUBE, BAJA, GRIS, SERIES)

aplicar_tema("Gold · Análisis", "🥇")
# La correlacion ya no espera dias: se calcula sobre snapshots intradia y
# funciona desde el primer dia. Solo la volatilidad clasica (desvio de
# retornos DIARIOS) sigue necesitando historia.
MIN_VOLATILIDAD = 5


# run_query ya viene cacheado desde db.py (ttl=60). Este alias queda solo
# por comodidad de lectura: `q(...)` es mas corto dentro de las paginas.
q = run_query


def faltan(actual, minimo, que):
    st.caption(f"⏳ **{que}** necesita ~{minimo} días para ser confiable · llevás **{actual}**. "
               f"El pipeline suma un día cada día: se habilita solo.")


encabezado("🥇 Gold · Análisis",
           "Riesgo, correlación y amplitud · capa semántica de Gold")

# El filtro va en UNA fila, arriba de todo lo que gobierna.
periodo = filtro_periodo("analisis")
st.caption("Riesgo, correlación y estructura del mercado · mostrando **" + periodo["etiqueta"] + "**")

try:
    riesgo = q("""
        SELECT r.symbol, r.name, r.dias, r.volatilidad_pct, r.rango_medio_pct,
               r.retorno_periodo_pct, r.max_drawdown_pct, u.market_cap, u.market_cap_rank
        FROM gold.v_metricas_riesgo r
        JOIN gold.v_ultimo_snapshot u USING (crypto_id)
        ORDER BY u.market_cap_rank
    """)
    amplitud = q("SELECT * FROM gold.v_amplitud_mercado WHERE true"
                 + where_periodo("fecha", periodo) + " ORDER BY fecha")
except Exception:
    st.info("🕐 **Gold todavía no tiene las vistas de análisis.** Corren con `crypto_gold`, cada 15 minutos.")
    st.stop()

if riesgo.empty:
    st.info("🕐 Sin datos suficientes todavía — esperá la próxima corrida de `crypto_gold`.")
    st.stop()

ndias = int(riesgo["dias"].max())

# =============================================================
# 1) RIESGO vs RETORNO
# =============================================================
seccion("Riesgo y retorno")
st.caption("Cada burbuja es un activo · eje X: cuánto se mueve · eje Y: cuánto rindió · tamaño: capitalización")

# Con pocos días la volatilidad (desvío de retornos) es NULL, pero el rango
# intradía promedio ya mide "cuánto se mueve" desde el primer día.
usa_volatilidad = riesgo["volatilidad_pct"].notna().sum() >= 5 and ndias >= MIN_VOLATILIDAD
eje_x = "volatilidad_pct" if usa_volatilidad else "rango_medio_pct"
label_x = "Volatilidad diaria (%)" if usa_volatilidad else "Rango intradía promedio (%)"

d = riesgo.dropna(subset=[eje_x, "retorno_periodo_pct"]).head(30)
if d.empty:
    st.info("Todavía no hay métricas de riesgo calculables.")
else:
    fig = go.Figure(go.Scatter(
        x=d[eje_x], y=d["retorno_periodo_pct"],
        mode="markers+text",
        text=d["symbol"], textposition="top center",
        textfont=dict(size=10),
        marker=dict(
            size=np.sqrt(d["market_cap"] / 1e9).clip(6, 55),
            color=[SUBE if r >= 0 else BAJA for r in d["retorno_periodo_pct"]],
            opacity=.45, line=dict(width=1.5,
                                   color=[SUBE if r >= 0 else BAJA for r in d["retorno_periodo_pct"]]),
        ),
        customdata=np.stack([d["name"], d["market_cap"] / 1e9], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>" + label_x + ": %{x:.2f}%"
                      "<br>Retorno: %{y:+.2f}%<br>Market cap: $%{customdata[1]:,.1f}B<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=GRIS, line_width=1, line_dash="dot")
    fig.update_layout(
        height=400, margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title=label_x, showgrid=True, gridcolor="rgba(128,128,128,.15)", zeroline=False),
        yaxis=dict(title="Retorno del período (%)", showgrid=True,
                   gridcolor="rgba(128,128,128,.15)", zeroline=False),
    )
    st.plotly_chart(fig, use_container_width=True)
    if not usa_volatilidad:
        st.caption(
            f"ℹ️ Con **{ndias} días** el desvío de los retornos todavía no es estable, así que el eje X usa el "
            "**rango intradía promedio** — que mide lo mismo (cuánto se mueve el precio) y funciona desde el primer día. "
            f"A partir de {MIN_VOLATILIDAD} días pasa a volatilidad clásica, sola."
        )

st.divider()

# =============================================================
# 2) COMPARACIÓN INDEXADA + CORRELACIÓN
# =============================================================
seccion("Comparar activos entre sí",
        "Sobre el grano intradía: un punto cada 15 minutos, no un cierre por día")

# UN filtro, arriba, gobernando los dos graficos de abajo. Antes vivia adentro
# de la columna izquierda y solo scopeaba ese grafico: dos paneles al lado, uno
# filtrado y el otro no.
opciones = list(riesgo["name"].head(12))
sel = st.multiselect("Activos a comparar", opciones, default=opciones[:4],
                     max_selections=6)

if not sel:
    st.caption("Elegí al menos un activo arriba.")
else:
    nombres = "', '".join(s.replace("'", "''") for s in sel)
    intra = q(f"""
        SELECT name, symbol, snapshot_ts, current_price, retorno_pct
        FROM gold.v_intradia
        WHERE name IN ('{nombres}')
          {where_periodo("snapshot_ts", periodo)}
        ORDER BY name, snapshot_ts
    """)

    izq, der = st.columns([1.15, .85])

    # ---------------------------------------------------------- base 100
    with izq:
        st.caption("Todas las series arrancan en 100: así se comparan activos de "
                   "precios muy distintos en un solo eje")
        if intra["snapshot_ts"].nunique() < 2:
            st.info("📅 Todavía no hay dos snapshots para dibujar una serie.")
        else:
            figc = go.Figure()
            for i, nom in enumerate(sel):
                s = intra[intra["name"] == nom]
                if s.empty:
                    continue
                idx = s["current_price"] / s["current_price"].iloc[0] * 100
                figc.add_trace(go.Scatter(
                    x=s["snapshot_ts"], y=idx, mode="lines", name=nom,
                    line=dict(color=SERIES[i % len(SERIES)], width=2),
                    hovertemplate=f"<b>{nom}</b><br>%{{x|%d-%b %H:%M}} · "
                                  f"índice %{{y:.2f}}<extra></extra>",
                ))
            figc.add_hline(y=100, line_color=GRIS, line_width=1, line_dash="dot")
            figc.update_layout(**layout(
                height=320,
                yaxis=dict(title="Base 100", showgrid=True,
                           gridcolor="rgba(128,128,128,.15)"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                hovermode="x unified",
            ))
            st.plotly_chart(figc, use_container_width=True)
            st.caption(f"**{intra['snapshot_ts'].nunique()} snapshots** de historia. "
                       "La misma serie en cierres diarios tendría "
                       f"{ndias} punto{'s' if ndias != 1 else ''}.")

    # ---------------------------------------------------------- correlacion
    with der:
        st.caption("¿Se mueven juntas? 1 = idénticas · 0 = independientes · −1 = opuestas")
        simbolos = sorted(intra["symbol"].dropna().unique())
        if len(simbolos) < 2:
            st.info("Elegí al menos dos activos para comparar.")
        else:
            lista = "', '".join(s.replace("'", "''") for s in simbolos)
            # CONSULTA DE CONSUMO, no capa semántica. Depende de qué activos
            # elegiste recién, así que no define ninguna métrica gobernada: es
            # una pregunta puntual. Por eso vive acá, en la página que la hace,
            # y no como vista en el warehouse.
            #
            # Que sea ad-hoc no significa que vaya en pandas: el corr() lo
            # sigue haciendo Postgres. Lo que cambia es de quién es la query.
            pares = q(f"""
                WITH r AS (
                    SELECT symbol, snapshot_ts, retorno_pct
                    FROM gold.v_intradia
                    WHERE retorno_pct IS NOT NULL
                      AND symbol IN ('{lista}')
                      {where_periodo("snapshot_ts", periodo)}
                )
                SELECT a.symbol AS symbol_a, b.symbol AS symbol_b,
                       corr(a.retorno_pct, b.retorno_pct) AS correlacion,
                       count(*)                           AS observaciones
                FROM r a JOIN r b ON a.snapshot_ts = b.snapshot_ts
                GROUP BY a.symbol, b.symbol
                HAVING count(*) >= 5
            """)
            if pares.empty:
                faltan(ndias, 1, "La matriz de correlación")
            else:
                # pandas SOLO reordena para dibujar: el corr() lo hizo Postgres.
                m = pares.pivot(index="symbol_a", columns="symbol_b",
                                values="correlacion")
                obs = int(pares["observaciones"].min())
                figm = go.Figure(go.Heatmap(
                    z=m.values, x=list(m.columns), y=list(m.index),
                    zmin=-1, zmax=1,
                    # Divergente: dos hues opuestos y un midpoint NEUTRO. Sobre
                    # fondo oscuro el cero tiene que desaparecer, no brillar.
                    colorscale=[[0, BAJA], [.5, "#1b2330"], [1, SUBE]],
                    text=m.round(2).values, texttemplate="%{text}",
                    hovertemplate="%{y} ↔ %{x}: %{z:.2f}<extra></extra>",
                ))
                figm.update_layout(**layout(height=320))
                st.plotly_chart(figm, use_container_width=True)
                st.caption(
                    f"Calculada sobre **{obs} observaciones** intradía. "
                    "Si todo correlaciona cerca de 1, **diversificar entre criptos "
                    "no reduce el riesgo**: es una sola apuesta repartida."
                )

de_donde_sale("gold.v_intradia",
              "El grano fino del pipeline: 1 fila por cripto y por snapshot, "
              "con el retorno ya calculado en SQL. La correlación de arriba NO "
              "es una vista: es SQL de esta página sobre estos datos.")

st.divider()

# =============================================================
# 3) AMPLITUD + CONCENTRACIÓN + DRAWDOWN
# =============================================================
seccion("Salud del mercado")
a, b, c = st.columns(3)

with a:
    if amplitud.empty:
        st.metric("Amplitud del mercado", "—")
        st.caption("Cuántos activos suben cada día. Se habilita con el segundo día.")
    else:
        u = amplitud.iloc[-1]
        st.metric("Activos en alza", f"{int(u['suben'])} de {int(u['suben'] + u['bajan'] + u['planos'])}",
                  f"{u['pct_alza']:.0f}% del mercado")
        figb = go.Figure()
        figb.add_trace(go.Bar(x=amplitud["fecha"], y=amplitud["suben"], name="Suben", marker_color=SUBE))
        figb.add_trace(go.Bar(x=amplitud["fecha"], y=amplitud["bajan"], name="Bajan", marker_color=BAJA))
        figb.update_layout(
            barmode="stack", height=140, margin=dict(l=0, r=0, t=4, b=0), showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, title=None), yaxis=dict(showgrid=False, title=None),
            bargap=0.4,
        )
        st.plotly_chart(figb, use_container_width=True)
        st.caption("Un mercado que sube con **pocos** activos es frágil: el índice tapa lo que pasa abajo.")

with b:
    # El HHI sale de gold.v_concentracion, calculado en SQL. Antes se computaba
    # acá en pandas, en la pagina cuyo docstring dice "nada de agregar en pandas".
    conc = q("SELECT * FROM gold.v_concentracion")
    if conc.empty:
        st.metric("Concentración (HHI)", "—")
    else:
        c0 = conc.iloc[0]
        hhi = int(c0["hhi"])
        lider = riesgo.iloc[0]
        st.metric("Concentración (HHI)", f"{hhi:,}".replace(",", "."),
                  "muy concentrado" if hhi > 2500 else "moderado")
        st.caption(
            f"Índice Herfindahl sobre la capitalización, en la escala de los "
            f"reguladores de competencia (0–10.000). Arriba de **2.500** un mercado "
            f"se considera altamente concentrado. Acá los **5 primeros** explican "
            f"{c0['top5_pct']:.0f}% y **{lider['symbol']}** solo, buena parte de eso: "
            "el 'mercado cripto' se mueve, en medida importante, como se mueve uno solo."
        )

with c:
    dd = riesgo.dropna(subset=["max_drawdown_pct"]).nsmallest(1, "max_drawdown_pct")
    if ndias < 3 or dd.empty or dd.iloc[0]["max_drawdown_pct"] == 0:
        st.metric("Peor caída (drawdown)", "—")
        faltan(ndias, 3, "El drawdown")
    else:
        w = dd.iloc[0]
        st.metric("Peor caída (drawdown)", f"{w['max_drawdown_pct']:.2f}%", w["symbol"])
        st.caption("Cuánto cayó desde su máximo previo. Es el riesgo que el retorno promedio esconde: "
                   "dos activos con el mismo retorno pueden haber dolido muy distinto.")

st.divider()

# =============================================================
# EL STAR SCHEMA, FUNCIONANDO
# =============================================================
seccion("El star schema, funcionando",
        "Una fact al centro, dimensiones colgando · y por qué eso te deja "
        "preguntar cosas que la fact sola no contesta")

# El esquema va ANTES de los ejemplos, no despues. Los dos paneles de abajo
# son la misma operacion sobre dimensiones distintas, y eso solo se ve si
# primero quedo claro cual es la operacion.
st.markdown(
    "En clase 05 modelaste un **star schema**. No es una formalidad de "
    "diagrama: es lo que hace que las dos preguntas de abajo se contesten "
    "**sin tocar un solo hecho**.\n\n"
    "La regla es una sola: **los hechos van al centro, las descripciones van "
    "afuera.**\n\n"
    "- `fact_crypto_markets` guarda lo que *pasó*: un precio, un volumen, "
    "en un instante. Y dos claves: `crypto_id` y `fecha_id`.\n"
    "- `dim_crypto` describe **quién**: symbol, name, `categoria`.\n"
    "- `dim_tiempo` describe **cuándo**: fecha, `dia_semana`, "
    "`es_fin_de_semana`.\n\n"
    "Ningún hecho guarda si fue sábado ni si la moneda es una stablecoin. "
    "Lo saben las dimensiones, y la clave alcanza para traerlo."
)

st.markdown(
    "**Lo que compra ese diseño:** para cortar por categoría *no hubo que "
    "agregar una columna `categoria` a la fact*. Está en `dim_crypto`, la "
    "fact tiene el `crypto_id`, y con eso alcanza. Lo mismo para el día de "
    "la semana. Si mañana querés cortar por trimestre, por país del emisor o "
    "por lo que sea, se agrega el atributo **a la dimensión** y **ningún "
    "hecho se toca**.\n\n"
    "Abajo están las dos preguntas, una al lado de la otra. Fijate que es "
    "**el mismo SQL** — solo cambia de qué tabla sale el `GROUP BY`."
)

st.markdown("##### 1 · Cortando por `dim_tiempo` — *cuándo*")

est = q("SELECT * FROM gold.v_estacionalidad ORDER BY es_fin_de_semana, dia_semana")

if est.empty:
    st.caption("Todavía sin días suficientes para comparar.")
else:
    izq2, der2 = st.columns([.9, 1.1])
    with izq2:
        st.markdown(
            "La medida (`rango_pct`) sale de la **fact**. El atributo por el "
            "que se corta (`es_fin_de_semana`) vive en **`dim_tiempo`**. El "
            "`fecha_id` es todo lo que hace falta para unirlos.\n\n"
            "Ningún hecho guarda si fue sábado: lo sabe el calendario."
        )
        st.code(
            "SELECT t.es_fin_de_semana,\n"
            "       avg(o.rango_pct)\n"
            "FROM gold.fact_crypto_markets f\n"
            "JOIN gold.dim_crypto  d USING (crypto_id)   -- quién\n"
            "JOIN gold.dim_tiempo  t USING (fecha_id)    -- cuándo\n"
            "GROUP BY t.es_fin_de_semana",
            language="sql",
        )
    with der2:
        est["etiqueta"] = est["dia_semana"].str.strip()
        colores = [BAJA if f else SUBE for f in est["es_fin_de_semana"]]
        fige = go.Figure(go.Bar(
            x=est["etiqueta"], y=est["rango_medio_pct"],
            marker_color=colores,
            hovertemplate="<b>%{x}</b><br>rango medio %{y:.2f}%<extra></extra>",
        ))
        fige.update_layout(**layout(
            height=260,
            yaxis=dict(title="Rango medio del día (%)", showgrid=True,
                       gridcolor="rgba(128,128,128,.15)"),
        ))
        st.plotly_chart(fige, use_container_width=True)
        st.caption(
            f"Azul = día hábil · rojo = fin de semana. Con **{int(est['dias'].sum())} "
            "días** acumulados esto todavía no concluye nada: cada barra es un "
            "solo día. El mecanismo ya funciona; la conclusión llega con las "
            "semanas."
        )
    st.dataframe(
        est, hide_index=True, use_container_width=True,
        column_config={
            "es_fin_de_semana": st.column_config.CheckboxColumn("Finde"),
            "dia_semana": "Día",
            "dias": st.column_config.NumberColumn("Días", width="small"),
            "observaciones": st.column_config.NumberColumn("Obs.", width="small"),
            "rango_medio_pct": st.column_config.NumberColumn("Rango medio", format="%.2f%%"),
            "retorno_medio_pct": st.column_config.NumberColumn("Retorno medio", format="%+.2f%%"),
            "desvio_pct": st.column_config.NumberColumn("Desvío", format="%.2f%%"),
        },
    )
    de_donde_sale("gold.v_estacionalidad",
                  "El JOIN de la fact con dim_tiempo por fecha_id: corta por un "
                  "atributo que vive en la dimensión, no en la fact.")

# --- la MISMA leccion, con la OTRA dimension -------------------------------
# dim_tiempo responde "cuando". dim_crypto responde "quien". Mismo mecanismo,
# mismas metricas y misma forma de panel que arriba: ponerlos uno debajo del
# otro es lo que hace evidente que es el mismo modelo, no dos trucos.
cat = q("SELECT * FROM gold.v_por_categoria")

if not cat.empty:
    st.markdown("##### 2 · Cortando por `dim_crypto` — *quién*")
    izq3, der3 = st.columns([.9, 1.1])
    with izq3:
        st.markdown(
            "**Cambió una sola cosa**: el `GROUP BY` ahora apunta a "
            "`dim_crypto.categoria` en vez de a `dim_tiempo`. Misma fact, "
            "mismas medidas, misma query — otra dimensión.\n\n"
            "El JOIN del ejemplo de arriba **ya traía las dos** (`-- quién` y "
            "`-- cuándo`) y usaba una sola. Esta es la otra, y no hubo que "
            "tocar un solo hecho para tenerla.\n\n"
            "Encima agrega algo que la temporal no puede dar: **cuánto pesa** "
            "cada familia. *Cuántas hay* y *cuánto valen* son dos preguntas "
            "distintas, y la tabla de abajo las muestra juntas."
        )
        st.code(
            "SELECT o.categoria,\n"
            "       avg(o.rango_pct),\n"
            "       count(DISTINCT o.crypto_id)\n"
            "FROM gold.v_ohlc_diario o     -- fact + dims ya unidas\n"
            "GROUP BY o.categoria",
            language="sql",
        )
    with der3:
        # El color sigue a la ENTIDAD, no a su posicion: si manana las
        # memecoins se mueven mas que las altcoins, cada familia conserva su
        # color y el grafico se sigue leyendo igual.
        COLOR_CAT = {"bitcoin": SERIES[0], "altcoin": SERIES[1],
                     "memecoin": SERIES[4], "commodity": SERIES[3],
                     "stablecoin": SERIES[2]}
        figc = go.Figure(go.Bar(
            x=cat["categoria"], y=cat["rango_medio_pct"],
            marker_color=[COLOR_CAT.get(c, GRIS) for c in cat["categoria"]],
            text=[f"{v:.2f}%" for v in cat["rango_medio_pct"]],
            textposition="outside",
            customdata=cat[["criptos", "participacion_mcap_pct"]].to_numpy(),
            hovertemplate="<b>%{x}</b><br>rango medio %{y:.2f}%"
                          "<br>%{customdata[0]} criptos"
                          "<br>%{customdata[1]:.1f}% del market cap<extra></extra>",
        ))
        figc.update_layout(**layout(
            height=260,
            yaxis=dict(title="Rango medio del día (%)", showgrid=True,
                       gridcolor="rgba(128,128,128,.15)"),
        ))
        st.plotly_chart(figc, use_container_width=True)
        st.caption(
            "Mismo eje que el gráfico de arriba, para que se puedan comparar. "
            "Las stablecoins casi no se mueven: para eso están. Que el orden "
            "salga solo es la prueba de que la dimensión clasifica bien — "
            "nadie le dijo al gráfico qué es una stablecoin, lo dice "
            "`dim_crypto`."
        )
    st.dataframe(
        cat, hide_index=True, use_container_width=True,
        column_config={
            "categoria": "Familia",
            "criptos": st.column_config.NumberColumn("Criptos", width="small"),
            "observaciones": st.column_config.NumberColumn("Obs.", width="small"),
            "rango_medio_pct": st.column_config.NumberColumn("Rango medio", format="%.2f%%"),
            "retorno_medio_pct": st.column_config.NumberColumn("Retorno medio", format="%+.2f%%"),
            "desvio_pct": st.column_config.NumberColumn("Desvío", format="%.2f%%"),
            "participacion_mcap_pct": st.column_config.NumberColumn(
                "Del market cap", format="%.2f%%"),
        },
    )
    _btc = cat[cat["categoria"] == "bitcoin"]
    _alt = cat[cat["categoria"] == "altcoin"]
    if not _btc.empty and not _alt.empty:
        st.caption(
            f"Las dos últimas columnas dicen cosas distintas: **{int(_alt['criptos'].iloc[0])} "
            f"altcoins** suman {_alt['participacion_mcap_pct'].iloc[0]:.0f}% del market cap; "
            f"**una sola moneda**, Bitcoin, pesa {_btc['participacion_mcap_pct'].iloc[0]:.0f}%. "
            "Contar monedas y medir peso no son la misma pregunta — y la "
            "dimensión deja hacer las dos sin tocar la fact."
        )
    de_donde_sale("gold.v_por_categoria",
                  "La hermana de v_estacionalidad: mismas métricas, pero "
                  "agrupando por un atributo de dim_crypto en vez de uno de "
                  "dim_tiempo. La columna `categoria` sale de la taxonomía de "
                  "CoinGecko y vive en la dimensión, no en la fact.")

st.divider()
seccion("Tabla de métricas")
st.dataframe(
    riesgo, hide_index=True, use_container_width=True,
    column_config={
        "market_cap_rank": st.column_config.NumberColumn("#", width="small"),
        "symbol": st.column_config.TextColumn("Símbolo", width="small"),
        "name": "Activo",
        "dias": st.column_config.NumberColumn("Días", width="small"),
        "volatilidad_pct": st.column_config.NumberColumn("Volatilidad", format="%.2f%%"),
        "rango_medio_pct": st.column_config.NumberColumn("Rango medio", format="%.2f%%"),
        "retorno_periodo_pct": st.column_config.NumberColumn("Retorno", format="%+.2f%%"),
        "max_drawdown_pct": st.column_config.NumberColumn("Drawdown", format="%.2f%%"),
        "market_cap": st.column_config.NumberColumn("Market cap", format="compact"),
    },
    column_order=["market_cap_rank", "symbol", "name", "dias", "rango_medio_pct",
                  "volatilidad_pct", "retorno_periodo_pct", "max_drawdown_pct", "market_cap"],
)
