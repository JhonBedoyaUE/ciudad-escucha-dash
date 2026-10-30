#!/usr/bin/env python
"""
Dashboard Ciudad Escucha — versión Dash/Plotly
Sistema de reporte de daños en espacio público (datos SIMULADOS).
- Barra de filtros horizontal (flex-wrap) en lugar de columna lateral
- Mapa interactivo (Carto/Positron) con puntos-círculo por tipo de daño
- Límites de veredas DANE 2024 (GeoJSON filtrado en QGIS)
- Detalle del reporte con imagen al hacer clic en un punto
- Formulario para crear nuevos reportes (con subida de foto)
- Evolución acumulada (reportes / resueltos / pendientes) con `resuelta_en`
Autor: Jhon Bedoya — Habilidades Gerenciales
"""
import base64
import io
import json
import os
import random
import time

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback, ctx, dcc, html, no_update

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_CSV = os.path.join(BASE, "data", "generated", "dataset_simulado.csv")
VEREDAS_GEO = os.path.join(BASE, "data", "processed", "veredas_villavicencio_simpl.geojson")
UPLOADS = os.path.join(BASE, "assets", "uploads")
os.makedirs(UPLOADS, exist_ok=True)

VILLAVICENCIO = {"lat": 4.1425, "lon": -73.6294}

COLOR_TIPO = {
    "Vías": "#E74C3C",
    "Alumbrado público": "#3498DB",
    "Basuras": "#2ECC71",
    "Alcantarillado": "#E67E22",
    "Otro": "#95A5A6",
}
COLOR_ESTADO = {
    "Reportado": "#8e44ad",
    "En revisión": "#f39c12",
    "Programado": "#2980b9",
    "Resuelto": "#27ae60",
}
# Etiqueta corta para el embudo (el nombre completo se ve en el hover)
ETIQUETA_CANAL = {
    "Físico/PQRSD Telefónico": "Físico / PQRSD",
}
COLOR_CANAL = {
    "App Ciudad Escucha": "#3498DB",
    "WhatsApp": "#25D366",
    "Portal Web": "#9B59B6",
    "Físico/PQRSD Telefónico": "#E67E22",
}
IMG_TIPO = {
    "Vías": "vias.png",
    "Alumbrado público": "alumbrado.png",
    "Basuras": "basuras.png",
    "Alcantarillado": "alcantarillado.png",
    "Otro": "otro.png",
}

# Colores neutros que funcionan en tema oscuro y claro
GRID = "rgba(148,163,184,.20)"
TRANS = "rgba(0,0,0,0)"

# ------------------------------------------------------------------
# Datos
# ------------------------------------------------------------------
def cargar_df():
    df = pd.read_csv(DATA_CSV, encoding="utf-8")
    df["fecha_reporte"] = pd.to_datetime(df["fecha_reporte"])
    for col in ("foto_url", "descripcion", "resuelta_en"):
        if col not in df.columns:
            df[col] = ""
    df["foto_url"] = df["foto_url"].fillna("").astype(str)
    df["descripcion"] = df["descripcion"].fillna("").astype(str)
    # pandas lee las celdas vacías como NaN; `resuelta_en` se necesita como
    # fecha para calcular el saldo de pendientes en cada punto del tiempo.
    df["resuelta_en"] = pd.to_datetime(df["resuelta_en"], errors="coerce")
    m = df["foto_url"] == ""
    df.loc[m, "foto_url"] = df.loc[m, "tipo_dano"].map(
        lambda t: f"assets/img/{IMG_TIPO.get(t, 'otro.png')}")
    return df


def cargar_veredas_geojson():
    with open(VEREDAS_GEO, "r", encoding="utf-8") as f:
        return json.load(f)


def option_list(df, columna, valor_todos):
    return ([{"label": valor_todos, "value": valor_todos}] +
            [{"label": str(v), "value": v} for v in sorted(df[columna].unique())])


def filtrar(comuna, tipo, canal, estado, fi, ff):
    df = cargar_df()
    f = df.copy()
    if comuna and comuna != "Todas":
        f = f[f["comuna"] == comuna]
    if tipo and tipo != "Todos":
        f = f[f["tipo_dano"] == tipo]
    if canal and canal != "Todos":
        f = f[f["canal_reporte"] == canal]
    if estado and estado != "Todos":
        f = f[f["estado_gestion"] == estado]
    if fi and ff:
        f = f[(f["fecha_reporte"] >= pd.Timestamp(fi)) &
              (f["fecha_reporte"] < pd.Timestamp(ff) + pd.Timedelta(days=1))]
    return f


def form_nuevo_reporte():
    return dbc.Row([
        dbc.Col([
            html.Label("Tipo de daño", className="text-muted small mt-1"),
            dcc.Dropdown(id="n_tipo", clearable=False),
            html.Label("Comuna", className="text-muted small mt-2"),
            dbc.Select(id="n_comuna"),
            dbc.Row([
                dbc.Col([html.Label("Latitud", className="text-muted small mt-2"),
                         dbc.Input(id="n_lat", type="number", step="0.000001")], width=6),
                dbc.Col([html.Label("Longitud", className="text-muted small mt-2"),
                         dbc.Input(id="n_lon", type="number", step="0.000001")], width=6),
            ]),
            dbc.Row([
                dbc.Col([html.Label("Canal de reporte", className="text-muted small mt-2"),
                         dbc.Select(id="n_canal")], width=6),
                dbc.Col([html.Label("Estado", className="text-muted small mt-2"),
                         dbc.Select(id="n_estado",
                                    options=["Reportado", "En revisión", "Programado", "Resuelto"])],
                        width=6),
            ]),
            html.Label("Descripción del problema", className="text-muted small mt-2"),
            dbc.Textarea(id="n_desc", rows=2,
                         placeholder="Ej: 'Alumbrado público descompuesto frente a la vereda...'"),
            dbc.Button([html.I(className="fa-solid fa-dice me-1"), " Sugerir punto en la comuna"],
                       id="btn_sugerir_punto", color="secondary", size="sm", outline=True,
                       className="mt-2 w-100"),
        ], width=12, lg=6),

        dbc.Col([
            html.Label("📸 Foto del problema (opcional)", className="text-muted small mt-1"),
            dcc.Upload(
                id="upload_foto",
                children=html.Div([
                    html.I(className="fa-solid fa-cloud-arrow-up fa-2x text-secondary d-block my-1"),
                    html.Div("Arrastra una foto o haz clic"),
                    html.Div("(JPG / PNG)", className="text-muted", style={"font-size": ".7rem"}),
                ]),
                style={"width": "100%", "minHeight": 110, "borderWidth": "1px",
                       "borderStyle": "dashed", "borderRadius": 8,
                       "textAlign": "center", "padding": "14px 8px"},
                className="mb-2", multiple=False,
            ),
            html.Img(id="preview_foto", src="", style={
                "maxHeight": 140, "display": "none", "borderRadius": 8}),
            html.Div(id="preview_texto", className="text-muted small"),
            html.Label("📍 Vista previa de la ubicación", className="text-muted small mt-2"),
            dcc.Graph(id="mini_mapa", config={"displayModeBar": False}, style={"height": "150px"}),
        ], width=12, lg=6),
    ])


def barra_filtros():
    """Barra de filtros horizontal: los campos se reparten el ancho y saltan de
    línea (flex-wrap) cuando ya no caben contraídos al mínimo."""
    return dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Span([html.I(className="fa-solid fa-sliders me-2 text-info"),
                               "Filtros"], className="ce-f-titulo"),
                    width="auto"),
            dbc.Col(html.Div(id="resumen_filtros", className="ce-resumen"),
                    width="auto", className="ms-auto"),
        ], className="align-items-center g-2 mb-2"),
        html.Div([
            html.Div([html.Label("Comuna", className="ce-f-label"),
                      dcc.Dropdown(id="f_comuna", clearable=False)], className="ce-f-item"),
            html.Div([html.Label("Tipo de daño", className="ce-f-label"),
                      dcc.Dropdown(id="f_tipo", clearable=False)], className="ce-f-item"),
            html.Div([html.Label("Canal de reporte", className="ce-f-label"),
                      dcc.Dropdown(id="f_canal", clearable=False)], className="ce-f-item"),
            html.Div([html.Label("Estado de gestión", className="ce-f-label"),
                      dcc.Dropdown(id="f_estado", clearable=False)], className="ce-f-item"),
            html.Div([html.Label("Rango de fechas", className="ce-f-label"),
                      dcc.DatePickerRange(id="f_fechas", minimum_nights=0,
                                          initial_visible_month=pd.Timestamp.now(),
                                          style={"fontSize": ".78rem"})],
                     className="ce-f-item ce-f-fechas"),
            html.Div(dbc.Button([html.I(className="fa-solid fa-rotate-left me-1"),
                                 "Restablecer"], id="btn_reset", color="secondary",
                                size="sm", outline=True, className="text-nowrap"),
                     className="ce-f-item ce-f-btn"),
        ], className="ce-filtros"),
    ]), className="surface shadow-sm border-0 mb-3")


def tarjeta(titulo, icono, graph_id, alto, extra=None):
    """Tarjeta con cabecera y un dcc.Graph."""
    return dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Span([html.I(className=f"fa-solid {icono} me-2"), titulo],
                              style={"font-weight": 700}), width="auto"),
            dbc.Col(html.Span(extra or "", className="text-muted",
                              style={"font-size": ".72rem"}),
                    width="auto", className="ms-auto"),
        ], className="align-items-center mb-1"),
        dcc.Graph(id=graph_id, config={"displayModeBar": False},
                  style={"height": alto}, className="mt-1"),
    ]), className="surface shadow-sm border-0 mb-3")


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.DARKLY,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css",
    ],
    title="Ciudad Escucha · Villavicencio",
    suppress_callback_exceptions=True,
    prevent_initial_callbacks="initial_duplicate",
)
# `_favicon` es una RUTA relativa a assets/ (no un emoji suelto): si apunta a
# un archivo inexistente, Dash lanza 500 en TODAS las peticiones.
app._favicon = "img/favicon.png"
server = app.server

app.layout = dbc.Container([
    # ---------- Barra superior ----------
    dbc.Navbar(
        dbc.Row([
            dbc.Col(html.I(className="fa-solid fa-city text-info"), width="auto",
                    style={"font-size": "1.5rem"}),
            dbc.Col(html.Span("Ciudad Escucha", className="ce-title", style={
                "font-weight": 800, "font-size": "1.2rem"}), width="auto"),
            dbc.Col(html.Span("· Villavicencio ", className="text-secondary d-none d-md-block",
                              style={"font-size": ".78rem"}), width="auto"),
            dbc.Col(dbc.Badge("DATOS SIMULADOS · PROYECTO ACADÉMICO", color="secondary",
                              className="d-none d-md-block",
                              style={"font-size": ".62rem", "letter-spacing": ".05em"}),
                    width="auto"),
            # El toggle de tema queda junto a la acción principal, que va al extremo derecho
            dbc.Col(dbc.Button([html.I(className="fa-solid fa-sun", id="icono_tema")],
                               id="btn_tema", color="outline-secondary", size="sm",
                               title="Alternar modo claro / oscuro", className="px-2"),
                    width="auto", className="ms-auto"),
            dbc.Col(dbc.Button([html.I(className="fa-solid fa-plus me-1"), " Nuevo reporte"],
                               id="btn_abrir_form", color="info", size="sm",
                               className="text-nowrap px-3 py-1 ce-btn-nuevo"),
                    width="auto"),
        ], className="align-items-center g-2 py-1 flex-nowrap w-100"),
        sticky="top", className="ce-navbar mb-3",
    ),

    dbc.Container([
        # ---------- Barra de filtros (ocupa el ancho que antes eran las tarjetas) ----------
        barra_filtros(),

        # ---------- Mapa (25 % más alto) + tipo/canal apilados a la derecha ----------
        dbc.Row([
            dbc.Col(tarjeta("Mapa interactivo", "fa-map-location-dot", "mapa", "70vh",
                            "Haz clic en un punto 👆 · fondo oscuro/acorde al tema · datos simulados"),
                    width=12, xl=8, className="mb-0"),
            dbc.Col([
                tarjeta("Reportes por tipo de daño", "fa-chart-column", "g_tipo", "32vh"),
                tarjeta("Canal de reporte", "fa-filter", "g_canal", "32vh"),
            ], width=12, xl=4),
        ], className="g-3 mb-3"),

        # ---------- Parte inferior: visible al hacer scroll ----------
        dbc.Row(dbc.Col(
            tarjeta("Evolución acumulada: reportes, resueltos y pendientes",
                    "fa-chart-line", "g_evol", "38vh",
                    "saldo = reportes creados − resueltos a esa fecha (usa resuelta_en)"),
                   width=12), className="g-3 mb-3"),

        dbc.Row([
            dbc.Col(tarjeta("Entradas y salidas por semana", "fa-right-left",
                            "g_semana", "30vh"), width=12, md=4),
            dbc.Col(tarjeta("Reportes por comuna", "fa-map", "g_comuna", "30vh"),
                    width=12, md=4),
            dbc.Col(tarjeta("Tiempo medio de resolución por tipo", "fa-stopwatch",
                            "g_resolucion", "30vh"), width=12, md=4),
        ], className="g-3 mb-3"),

        # ---------- Tabla recientes ----------
        dbc.Row(dbc.Col(dbc.Card([
            dbc.CardHeader(html.Span([html.I(className="fa-solid fa-list me-2"),
                                      "Últimos reportes registrados"])),
            dbc.CardBody(html.Div(id="tabla_recientes")),
        ], className="surface shadow-sm border-0 mb-4"))),

        html.Hr(className="border-dark"),
        html.P("🚨 DATOS SIMULADOS · PROYECTO ACADÉMICO · Habilidades Gerenciales · "
               "Autor: Jhon Bedoya (Analista) · Veredas: shapefile DANE 2024 filtrado en QGIS",
               className="text-center text-muted small mb-2"),
    ], fluid=True),

    # ---------- Modal: detalle del reporte ----------
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle([html.I(className="fa-solid fa-magnifying-glass me-2"),
                                        "Detalle del reporte"])),
        dbc.ModalBody(id="detalle_cuerpo"),
        dbc.ModalFooter(dbc.Button("Cerrar", id="btn_cerrar_detalle", color="secondary",
                                   size="sm", outline=True)),
    ], id="modal_detalle", size="lg", is_open=False, centered=True, scrollable=True),

    # ---------- Modal: nuevo reporte ----------
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle([html.I(className="fa-solid fa-pen-to-square text-info me-2"),
                                        "Registrar nuevo reporte"])),
        dbc.ModalBody(form_nuevo_reporte()),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn_cancelar_form", color="secondary", size="sm",
                       outline=True, className="me-2"),
            dbc.Button([html.I(className="fa-solid fa-paper-plane me-1"), " Enviar reporte"],
                       id="btn_enviar_form", color="info", size="sm"),
        ]),
    ], id="modal_form", size="lg", is_open=False, centered=True, scrollable=True),

    # Toast global
    dbc.Toast(id="toast_nuevo", is_open=False, duration=3500, class_name="shadow-sm",
              style={"position": "fixed", "top": 14, "right": 14, "zIndex": 9999, "minWidth": 310}),

    dcc.Store(id="store_actualizado"),
    # Tema actual (lo mantiene assets/theme.js): el mapa cambia de basemap claro/oscuro
    dcc.Store(id="store_tema", data="dark"),
], fluid=True, className="g-3")


# ------------------------------------------------------------------
# Figuras
# ------------------------------------------------------------------
def figura_mapa(df_f, tema="dark"):
    geo = cargar_veredas_geojson()
    # En tema oscuro el basemap también es oscuro (Carto Dark Matter)
    estilo = "carto-positron" if tema == "light" else "carto-darkmatter"
    fig = go.Figure()
    fig.add_trace(go.Choroplethmap(
        geojson=geo,
        featureidkey="properties.NOMBRE_VER",
        locations=[f["properties"]["NOMBRE_VER"] for f in geo["features"]],
        z=[0] * len(geo["features"]),
        colorscale=[[0, "rgba(230,126,34,0.07)"], [1, "rgba(230,126,34,0.07)"]],
        marker={"line_color": "#E67E22", "line_width": 1.05},
        showscale=False, hoverinfo="skip",
    ))
    df_m = df_f.copy()
    if len(df_m):
        df_m["fecha_s"] = df_m["fecha_reporte"].dt.strftime("%Y-%m-%d %H:%M")
        fig.add_trace(go.Scattermap(
            lat=df_m["latitud"], lon=df_m["longitud"], mode="markers",
            marker={"size": 11, "color": df_m["tipo_dano"].map(COLOR_TIPO),
                    "opacity": 0.85},
            customdata=df_m[["id_reporte", "comuna", "tipo_dano", "canal_reporte",
                             "estado_gestion", "fecha_s", "descripcion"]].values.tolist(),
            hovertemplate=("<b>%{customdata[0]}</b><br>"
                           "Comuna: %{customdata[1]}<br>"
                           "Tipo: %{customdata[2]}<br>"
                           "Canal: %{customdata[3]}<br>"
                           "Estado: <b>%{customdata[4]}</b><br>"
                           "Fecha: %{customdata[5]}<extra>🔍 clic = detalle con foto</extra>"),
        ))
    fig.update_layout(
        margin={"r": 0, "t": 0, "b": 0, "l": 0},
        paper_bgcolor=TRANS, showlegend=False,
        map={"style": estilo, "center": VILLAVICENCIO, "zoom": 11.35},
    )
    return fig


def _fig_vacia(msg="Sin reportes para los filtros seleccionados"):
    fig = go.Figure()
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor=TRANS,
                      xaxis={"visible": False}, yaxis={"visible": False},
                      annotations=[{"text": msg, "showarrow": False, "font": {"size": 12},
                                    "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5}])
    return fig


def _layout_base(fig, alto, leyenda=False, categorias=False):
    """Estilos comunes. `categorias=True` = barras horizontales (categorías en Y):
    sin rejilla y con separación entre los nombres de categoría y la barra."""
    fig.update_layout(
        margin=dict(l=38, r=12, t=6, b=6), height=alto,
        paper_bgcolor=TRANS, plot_bgcolor=TRANS, font={"size": 13.5},
        showlegend=leyenda,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0,
                "font": {"size": 12.5}},
        hoverlabel={"font": {"size": 13}},
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, title="",
                     tickfont={"size": 12.5})
    fig.update_yaxes(showgrid=not categorias, gridcolor=GRID, gridwidth=0.5,
                     zeroline=False, title="", tickfont={"size": 13})
    if categorias:
        fig.update_yaxes(ticklabelstandoff=12, ticks="")
    return fig


def barras_tipo(df_f):
    if df_f.empty:
        return _fig_vacia()
    # Orden fijo por color turístico => mismo orden que la leyenda del mapa
    data = (df_f.groupby("tipo_dano").size().rename("n").reset_index()
            .sort_values("n", ascending=True))
    fig = go.Figure(go.Bar(
        x=data["n"], y=data["tipo_dano"], orientation="h",
        marker={"color": data["tipo_dano"].map(COLOR_TIPO), "cornerradius": 5,
                "line": {"width": 0}},
        text=data["n"], textposition="outside", cliponaxis=False,
        textfont={"size": 13},
        hovertemplate="%{y}: <b>%{x}</b> reportes<extra></extra>",
    ))
    fig = _layout_base(fig, 250, categorias=True)
    fig.update_layout(margin=dict(l=112, r=30, t=6, b=6))
    return fig


def embudo_canal(df_f):
    """Embudo de canales: del que más reportes trae al que menos."""
    if df_f.empty:
        return _fig_vacia()
    df_c = (df_f.groupby("canal_reporte").size().rename("n").reset_index()
            .sort_values("n", ascending=False))
    fig = go.Figure(go.Funnel(
        y=[ETIQUETA_CANAL.get(c, c) for c in df_c["canal_reporte"]], x=df_c["n"],
        customdata=df_c[["canal_reporte"]].values.tolist(),
        textposition="inside", textinfo="value+percent total", constraintext="inside",
        insidetextfont={"size": 13, "color": "#ffffff", "family": "Inter, Segoe UI, sans-serif"},
        outsidetextfont={"size": 13},
        marker={"color": [COLOR_CANAL.get(c, "#95A5A6") for c in df_c["canal_reporte"]],
                "line": {"color": TRANS, "width": 0}},
        connector={"fillcolor": TRANS, "line": {"color": GRID, "width": 1.5}},
        hovertemplate="%{customdata[0]}: <b>%{x}</b> reportes<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=8, r=14, t=8, b=8), height=250,
        paper_bgcolor=TRANS, plot_bgcolor=TRANS, font={"size": 13},
        hoverlabel={"font": {"size": 13}}, showlegend=False,
    )
    fig.update_yaxes(tickfont={"size": 12.5}, ticks="", ticklabelstandoff=6)
    fig.update_xaxes(visible=False)
    return fig


def serie_evolucion(df_f):
    """Devoluelve (días, acumulados, resueltos_acum, pendientes)."""
    f = df_f.copy()
    f["creado"] = f["fecha_reporte"].dt.normalize()
    inicio = f["creado"].min()
    fin = f["creado"].max()
    if f["resuelta_en"].notna().any():
        fin = max(fin, f["resuelta_en"].max().normalize())
    dias = pd.date_range(inicio, fin, freq="D")
    nuevos = f.groupby("creado").size().reindex(dias, fill_value=0)
    resueltos = (f["resuelta_en"].dropna().dt.normalize().value_counts()
                 .reindex(dias, fill_value=0))
    acum = nuevos.cumsum()
    acum_res = resueltos.cumsum()
    return dias, acum, acum_res, acum - acum_res


def fig_evolucion(df_f):
    if df_f.empty:
        return _fig_vacia()
    dias, acum, acum_res, saldo = serie_evolucion(df_f)
    fig = go.Figure()
    # Sin área bajo las líneas: el sombreado no aporta significado propio
    fig.add_trace(go.Scatter(
        x=dias, y=saldo, name="Pendientes (saldo)", mode="lines",
        line={"color": "#E74C3C", "width": 2.4},
        hovertemplate="Pendientes: <b>%{y}</b><extra></extra>"))
    fig.add_trace(go.Scatter(
        x=dias, y=acum, name="Reportes acumulados", mode="lines",
        line={"color": "#3498DB", "width": 2.6},
        hovertemplate="Acumulados: <b>%{y}</b><extra></extra>"))
    fig.add_trace(go.Scatter(
        x=dias, y=acum_res, name="Resueltos acumulados", mode="lines",
        line={"color": "#1ABC9C", "width": 2.6},
        hovertemplate="Resueltos: <b>%{y}</b><extra></extra>"))
    fig = _layout_base(fig, 300, leyenda=True)
    fig.update_xaxes(tickformat="%d %b")
    return fig


def fig_semanal(df_f):
    if df_f.empty:
        return _fig_vacia()
    f = df_f.copy()
    nuevos = (f["fecha_reporte"].dt.to_period("W-MON").dt.start_time
              .value_counts().sort_index())
    resueltos = (f["resuelta_en"].dropna().dt.to_period("W-MON").dt.start_time
                 .value_counts().sort_index())
    idx = nuevos.index.union(resueltos.index)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=idx, y=nuevos.reindex(idx, fill_value=0), name="Nuevos",
                         marker_color="#3498DB", marker_line_width=0,
                         hovertemplate="Nuevos: <b>%{y}</b><extra></extra>"))
    fig.add_trace(go.Bar(x=idx, y=resueltos.reindex(idx, fill_value=0), name="Resueltos",
                         marker_color="#1ABC9C", marker_line_width=0,
                         hovertemplate="Resueltos: <b>%{y}</b><extra></extra>"))
    fig = _layout_base(fig, 230, leyenda=True)
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.06)
    fig.update_xaxes(tickformat="%d %b")
    return fig


def fig_comunas(df_f):
    if df_f.empty:
        return _fig_vacia()
    data = (df_f.groupby("comuna").size().rename("n").reset_index()
            .sort_values("n", ascending=True))
    fig = go.Figure(go.Bar(
        x=data["n"], y=data["comuna"], orientation="h",
        marker={"color": "#3498DB", "cornerradius": 5, "line": {"width": 0}},
        text=data["n"], textposition="outside", cliponaxis=False,
        textfont={"size": 13},
        hovertemplate="%{y}: <b>%{x}</b> reportes<extra></extra>",
    ))
    fig = _layout_base(fig, 230, categorias=True)
    fig.update_layout(margin=dict(l=82, r=30, t=6, b=6))
    return fig


def fig_resolucion(df_f):
    r = df_f.dropna(subset=["resuelta_en"]).copy()
    if r.empty:
        return _fig_vacia("Todavía no hay reportes resueltos")
    r["dias"] = (r["resuelta_en"] - r["fecha_reporte"]).dt.total_seconds() / 86400
    g = r.groupby("tipo_dano").agg(dias=("dias", "mean"), n=("dias", "size")).reset_index()
    g = g.sort_values("dias")
    fig = go.Figure(go.Bar(
        x=g["dias"], y=g["tipo_dano"], orientation="h",
        marker={"color": g["tipo_dano"].map(COLOR_TIPO), "cornerradius": 5,
                "line": {"width": 0}},
        text=[f"{d:.1f} d" for d in g["dias"]], textposition="outside",
        cliponaxis=False, textfont={"size": 13},
        customdata=g[["n"]].values.tolist(),
        hovertemplate="%{y}: <b>%{x:.1f}</b> días de media (%{customdata[0]} resueltos)"
                      "<extra></extra>",
    ))
    fig = _layout_base(fig, 230, categorias=True)
    fig.update_layout(margin=dict(l=108, r=48, t=6, b=6))
    return fig


def tabla_recientes_html(df_f, n=10):
    df_v = df_f.sort_values("fecha_reporte", ascending=False).head(n)
    filas = [html.Tr([
        html.Td(html.Code(r["id_reporte"], style={"font-size": ".74rem"})),
        html.Td(html.Span([html.Span("●", style={"color": COLOR_TIPO.get(r["tipo_dano"], "#999"),
                                                 "marginRight": 6}), r["tipo_dano"]])),
        html.Td(r["comuna"]),
        html.Td(r["canal_reporte"], className="d-none d-md-table-cell"),
        html.Td(dbc.Badge(r["estado_gestion"], className="d-block",
                          style={"font-size": ".68rem",
                                 "background": COLOR_ESTADO.get(r["estado_gestion"], "#555")})),
        html.Td(r["fecha_reporte"].strftime("%Y-%m-%d"), className="d-none d-md-table-cell"),
        html.Td(html.I(className="fa-solid fa-camera-retro text-secondary"
                       if "uploads/" in str(r["foto_url"]) else
                       "fa-solid fa-images text-secondary"),
                style={"width": 30}),
    ], className="border-dark border-top", style={"font-size": ".8rem"})
        for _, r in df_v.iterrows()]
    return html.Table([
        html.Thead(html.Tr([html.Th("ID", style={"font-size": ".7rem"}),
                            html.Th("Tipo", style={"font-size": ".7rem"}),
                            html.Th("Comuna", style={"font-size": ".7rem"}),
                            html.Th("Canal", className="d-none d-md-table-cell",
                                    style={"font-size": ".7rem"}),
                            html.Th("Estado", style={"font-size": ".7rem"}),
                            html.Th("Fecha", className="d-none d-md-table-cell",
                                    style={"font-size": ".7rem"}),
                            html.Th("📷", style={"font-size": ".7rem"})],
                           className="text-muted")),
        html.Tbody(filas),
    ], className="table-responsive table-sm table-hover mb-0")


def resumen_html(df_f):
    """Las dos cifras que sí aportaban de las tarjetas, ahora como chips compactos."""
    n = len(df_f)
    resueltos = int((df_f["estado_gestion"] == "Resuelto").sum())
    pct = resueltos / n * 100 if n else 0
    comunas = df_f["comuna"].nunique()

    def chip(icono, texto, color):
        return html.Span([html.I(className=f"fa-solid {icono} me-1", style={"color": color}),
                          texto], className="ce-chip")

    return [
        chip("fa-clipboard-list", f"{n:,} reportes".replace(",", " "), "#3498DB"),
        chip("fa-circle-check", f"{pct:.1f} % resueltos", "#1ABC9C"),
        chip("fa-hourglass-half", f"{n - resueltos} pendientes", "#E74C3C"),
        chip("fa-map", f"{comunas} comunas", "#E67E22"),
    ]


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------
# 1. Cargar opciones de filtros + formulario al abrir la app
@callback(
    Output("f_comuna", "options"), Output("f_tipo", "options"),
    Output("f_canal", "options"), Output("f_estado", "options"),
    # Sin `value` inicial el filtro queda en blanco y parece que no hay datos
    Output("f_comuna", "value"), Output("f_tipo", "value"),
    Output("f_canal", "value"), Output("f_estado", "value"),
    Output("f_fechas", "start_date"), Output("f_fechas", "end_date"),
    Output("n_tipo", "options"), Output("n_comuna", "options"),
    Output("n_canal", "options"),
    Output("modal_form", "is_open", allow_duplicate=True),
    Input("store_actualizado", "id"),
    prevent_initial_call="initial_duplicate",
)
def cargar_opciones_iniciales(_):
    df = cargar_df()
    return (option_list(df, "comuna", "Todas"), option_list(df, "tipo_dano", "Todos"),
            option_list(df, "canal_reporte", "Todos"), option_list(df, "estado_gestion", "Todos"),
            "Todas", "Todos", "Todos", "Todos",
            df["fecha_reporte"].min().date(), df["fecha_reporte"].max().date(),
            option_list(df, "tipo_dano", "—"), option_list(df, "comuna", "—"),
            option_list(df, "canal_reporte", "—"), False)


# 2. Panel principal: resumen + figuras + tabla
@callback(
    Output("resumen_filtros", "children"), Output("mapa", "figure"),
    Output("g_tipo", "figure"), Output("g_canal", "figure"),
    Output("g_evol", "figure"), Output("g_semana", "figure"),
    Output("g_comuna", "figure"), Output("g_resolucion", "figure"),
    Output("tabla_recientes", "children"),
    Input("f_comuna", "value"), Input("f_tipo", "value"),
    Input("f_canal", "value"), Input("f_estado", "value"),
    Input("f_fechas", "start_date"), Input("f_fechas", "end_date"),
    Input("btn_reset", "n_clicks"), Input("store_actualizado", "modified_timestamp"),
    Input("store_tema", "data"),
)
def actualizar_dashboard(comuna, tipo, canal, estado, fi, ff, _reset, _ts, tema):
    f = filtrar(comuna, tipo, canal, estado, fi, ff)
    return (resumen_html(f), figura_mapa(f, tema), barras_tipo(f), embudo_canal(f),
            fig_evolucion(f), fig_semanal(f), fig_comunas(f), fig_resolucion(f),
            tabla_recientes_html(f))


# 2b. Restablecer: vuelve los filtros al estado inicial
@callback(
    Output("f_comuna", "value", allow_duplicate=True),
    Output("f_tipo", "value", allow_duplicate=True),
    Output("f_canal", "value", allow_duplicate=True),
    Output("f_estado", "value", allow_duplicate=True),
    Output("f_fechas", "start_date", allow_duplicate=True),
    Output("f_fechas", "end_date", allow_duplicate=True),
    Input("btn_reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filtros(n):
    if not n:
        return (no_update,) * 6
    df = cargar_df()
    return ("Todas", "Todos", "Todos", "Todos",
            df["fecha_reporte"].min().date(), df["fecha_reporte"].max().date())


# 3. Detalle al hacer clic
@callback(
    Output("modal_detalle", "is_open"),
    Output("detalle_cuerpo", "children"),
    Input("mapa", "clickData"),
    Input("btn_cerrar_detalle", "n_clicks"),
    prevent_initial_call=True,
)
def mostrar_detalle(click_data, _cerrar):
    trig = ctx.triggered_id
    if trig == "btn_cerrar_detalle":
        return False, no_update
    if not click_data or not click_data.get("points"):
        return no_update, no_update
    cdata = click_data["points"][0]["customdata"]
    id_rep, comuna, tipo, canal, estado, fecha, desc = cdata
    df = cargar_df()
    fila = df[df["id_reporte"] == id_rep]
    foto_url = str(fila["foto_url"].iloc[0]) if len(fila) else ""
    if "/" not in foto_url:
        foto_url = f"assets/img/{IMG_TIPO.get(tipo, 'otro.png')}"
    img_url = "/" + foto_url
    resuelta = (fila["resuelta_en"].iloc[0] if len(fila) else pd.NaT)
    resuelta_txt = (resuelta.strftime("%Y-%m-%d %H:%M")
                    if pd.notna(resuelta) else "— sin resolver —")
    cuadro = dbc.Row([
        dbc.Col(html.Img(src=img_url, style={
            "width": "100%", "borderRadius": 10, "maxHeight": 330,
            "objectFit": "cover", "boxShadow": "0 6px 18px rgba(0,0,0,.45)"}),
            width=12, md=7, className="mb-2"),
        dbc.Col([
            html.H5(html.Code(id_rep), className="mb-1"),
            dcc.Dropdown(id="dd_estado_nuevo",
                         options=["Reportado", "En revisión", "Programado", "Resuelto"],
                         value=estado, clearable=False,
                         ),
            html.Hr(className="border-dark"),
            html.Div([html.Label("Comuna:", className="text-muted small mb-0"),
                      html.Span(comuna, style={"font-weight": 600})]),
            html.Div([html.Label("Tipo de daño:", className="text-muted small mb-0 mt-1"),
                      html.Span([html.Span("●", style={"color": COLOR_TIPO.get(tipo, "#999"),
                                                       "marginRight": 5}), tipo],
                                style={"font-weight": 600})]),
            html.Div([html.Label("Canal:", className="text-muted small mb-0 mt-1"),
                      html.Span(str(canal), style={"font-weight": 600})]),
            html.Div([html.Label("Fecha:", className="text-muted small mb-0 mt-1"),
                      html.Span(str(fecha), style={"font-weight": 600})]),
            html.Div([html.Label("Resuelta en:", className="text-muted small mb-0 mt-1"),
                      html.Span(resuelta_txt, style={"font-weight": 600})]),
            html.Div([html.Label("Origen:", className="text-muted small mb-0 mt-1"),
                      html.Span("SIMULADO_ACADEMICO",
                                className="badge bg-dark", style={"font-size": ".65rem"})]),
            html.Hr(className="border-dark"),
            html.Div([html.Label("Descripción", className="text-muted small mb-0"),
                      html.P(desc if isinstance(desc, str) and desc else
                             "— dato simulado sin descripción —",
                             className="small mb-0", style={"font-style": "italic"})]),
        ], width=12, md=5),
    ])
    return True, cuadro


# 4. Guarda el cambio de estado elegido dentro del detalle
@callback(
    Output("toast_nuevo", "is_open", allow_duplicate=True),
    Output("toast_nuevo", "children", allow_duplicate=True),
    Output("store_actualizado", "data", allow_duplicate=True),
    Input("dd_estado_nuevo", "value"),
    State("mapa", "clickData"),
    prevent_initial_call=True,
)
def cambiar_estado(nuevo_estado, click_data):
    if not nuevo_estado or not (click_data and click_data.get("points")):
        return no_update, no_update, no_update
    id_rep = click_data["points"][0]["customdata"][0]
    df = cargar_df()
    m = df["id_reporte"] == id_rep
    if not m.any():
        return no_update, no_update, no_update
    df.loc[m, "estado_gestion"] = nuevo_estado
    # `resuelta_en` alimenta los gráficos de evolución: se marca al resolver y
    # se limpia si el reporte vuelve a un estado abierto.
    df.loc[m, "resuelta_en"] = pd.Timestamp.now() if nuevo_estado == "Resuelto" else pd.NaT
    df.to_csv(DATA_CSV, index=False, encoding="utf-8")
    toast = html.Div([html.I(className="fa-solid fa-circle-check text-success me-2"),
                      f"Estado de {id_rep} actualizado a “{nuevo_estado}”"])
    # `store_actualizado` fuerza el refresco de todas las figuras
    return True, toast, f"estado-{time.time()}"


# 5. Abrir/cerrar modal del formulario
@callback(
    Output("modal_form", "is_open", allow_duplicate=True),
    Input("btn_abrir_form", "n_clicks"),
    Input("btn_cancelar_form", "n_clicks"),
    Input("btn_enviar_form", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_modal_form(abrir, cancelar, enviar):
    """Solo abre/cierra. El guardado lo hace la callback de notificación."""
    trig = ctx.triggered_id
    if trig == "btn_abrir_form":
        return True
    if trig in ("btn_cancelar_form", "btn_enviar_form"):
        return False
    return no_update


# 6. Guardar reporte en CSV
def guardar_reporte(tipo, comuna, lat, lon, canal, estado, desc, contenido):
    df = cargar_df()
    maxv = df["id_reporte"].str.extract(r"(\d+)$")[0].astype(int).max()
    nuevo_id = f"CE-2026-{int(maxv) + 1:04d}"
    ahora = pd.Timestamp.now()

    foto_url = ""
    if contenido:
        header, b64 = contenido.split(",")
        ext = "jpg" if ("jpeg" in header or "jpg" in header) else "png"
        nombre = f"{nuevo_id}.{ext}"
        data = base64.b64decode(b64)
        import PIL.Image
        img = PIL.Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((900, 900))
        img.save(os.path.join(UPLOADS, nombre), "JPEG", quality=86)
        foto_url = f"assets/uploads/{nombre}"

    estado = estado if estado else "Reportado"
    nueva = pd.DataFrame([{
        "id_reporte": nuevo_id,
        "fecha_reporte": ahora,
        "latitud": round(float(lat), 6),
        "longitud": round(float(lon), 6),
        "comuna": comuna,
        "tipo_dano": tipo,
        "canal_reporte": canal if canal else "App Ciudad Escucha",
        "estado_gestion": estado,
        "origen_datos": "SIMULADO_FORMULARIO_APP",
        "foto_url": foto_url,
        "descripcion": (desc or "").strip(),
        "resuelta_en": ahora if estado == "Resuelto" else pd.NaT,
    }])
    df = pd.concat([df, nueva], ignore_index=True)
    df.to_csv(DATA_CSV, index=False, encoding="utf-8")
    return nuevo_id


# 7. Sugerir coordenadas aleatorias + mini-mapa
@callback(
    Output("n_lat", "value", allow_duplicate=True),
    Output("n_lon", "value", allow_duplicate=True),
    Output("mini_mapa", "figure"),
    Output("n_comuna", "value"),
    Input("btn_sugerir_punto", "n_clicks"),
    State("n_comuna", "value"),
    prevent_initial_call=True,
)
def sugerir(_n_clicks, comuna):
    df = cargar_df()
    comuna_sel = comuna if comuna else random.choice(sorted(df["comuna"].unique()))
    sub = df[df["comuna"] == comuna_sel]
    fuente = sub if len(sub) >= 5 else df
    idx = random.randrange(len(fuente))
    lat = float(fuente["latitud"].iloc[idx]) + random.uniform(-.0018, .0018)
    lon = float(fuente["longitud"].iloc[idx]) + random.uniform(-.0018, .0018)
    lat, lon = round(lat, 6), round(lon, 6)
    fig = go.Figure(go.Scattermap(lat=[lat], lon=[lon], mode="markers",
                                  marker={"size": 14, "color": "#E74C3C",
                                          "opacity": .9}))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=150,
                      paper_bgcolor=TRANS,
                      map={"style": "carto-positron",
                           "center": {"lat": lat, "lon": lon}, "zoom": 12.6})
    return lat, lon, fig, comuna_sel


# 8. Mini-mapa también al mover lat/lon manuales
@callback(
    Output("n_lat", "value", allow_duplicate=True),
    Output("n_lon", "value", allow_duplicate=True),
    Output("mini_mapa", "figure", allow_duplicate=True),
    Input("n_lat", "value"), Input("n_lon", "value"),
    prevent_initial_call=True,
)
def mini_mapa_manual(lat, lon):
    lat = 4.1425 if lat is None else lat
    lon = -73.6294 if lon is None else lon
    fig = go.Figure(go.Scattermap(lat=[lat], lon=[lon], mode="markers",
                                  marker={"size": 14, "color": "#3498DB", "opacity": .9}))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=150,
                      paper_bgcolor=TRANS,
                      map={"style": "carto-positron",
                           "center": {"lat": lat, "lon": lon}, "zoom": 12.6})
    return round(float(lat), 6), round(float(lon), 6), fig


# 9. Preview de la foto subida
@callback(
    Output("preview_foto", "src"), Output("preview_foto", "style"),
    Output("preview_texto", "children"),
    Input("upload_foto", "contents"), State("upload_foto", "filename"),
)
def previsualizar(contenido, nombre):
    if contenido is None:
        return "", {"display": "none"}, ""
    return (contenido, {"maxHeight": 140, "display": "block", "borderRadius": 8},
            f"Vista previa: {nombre}")


# 10. Reset del formulario al abrirlo de nuevo (limpia campos)
@callback(
    Output("n_tipo", "value"), Output("n_desc", "value"),
    Output("upload_foto", "contents"), Output("preview_foto", "src"),
    Output("preview_foto", "style"), Output("preview_texto", "children"),
    Input("btn_abrir_form", "n_clicks"),
    State("n_tipo", "options"),
    prevent_initial_call=True,
)
def reset_formulario(n, opts_tipo):
    if n:
        tipo_def = (opts_tipo[1]["value"] if opts_tipo and len(opts_tipo) > 1 else None)
        return tipo_def, "", None, "", {"display": "none"}, ""
    return no_update, no_update, no_update, no_update, no_update, no_update


# 11. Notificación Toast (cierra sola)
@callback(
    Output("toast_nuevo", "is_open", allow_duplicate=True),
    Output("toast_nuevo", "children", allow_duplicate=True),
    Output("store_actualizado", "data"),
    Input("btn_enviar_form", "n_clicks"),
    State("n_tipo", "value"), State("n_comuna", "value"),
    State("n_lat", "value"), State("n_lon", "value"),
    State("n_canal", "value"), State("n_estado", "value"),
    State("n_desc", "value"), State("upload_foto", "contents"),
    prevent_initial_call=True,
)
def notificar_guardado(n, tipo, comuna, lat, lon, canal, estado, desc, contenido):
    if not n or tipo is None or lat is None or lon is None:
        return no_update, no_update, no_update
    nuevo = guardar_reporte(tipo, comuna, lat, lon, canal, estado, desc, contenido)
    fcom = f"{comuna} · {tipo}" if comuna and tipo else ""
    toast = html.Div([
        html.I(className="fa-solid fa-circle-check text-success me-2"),
        html.Div([
            html.Strong(f"Reporte {nuevo} registrado"),
            html.Span(fcom, className="ms-1 text-muted small"),
        ]),
    ])
    return True, toast, f"nuevo-{time.time()}"


@app.server.route("/health")
def _health():
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8505))
    print(f"🚀 Dashboard Ciudad Escucha (Dash) — http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
