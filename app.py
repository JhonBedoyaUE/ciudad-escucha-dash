#!/usr/bin/env python
"""
Dashboard Ciudad Escucha — versión Dash/Plotly
Sistema de reporte de daños en espacio público (datos SIMULADOS).
- Mapa interactivo OSM con puntos-círculo por tipo de daño
- Límites de veredas DANE 2024 (GeoJSON filtrado en QGIS)
- Detalle del reporte con imagen al hacer clic en un punto
- Formulario para crear nuevos reportes (con subida de foto)
Autor: Jhon Bedoya — Habilidades Gerenciales
"""
import base64
import io
import json
import os
import random

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
IMG_TIPO = {
    "Vías": "vias.png",
    "Alumbrado público": "alumbrado.png",
    "Basuras": "basuras.png",
    "Alcantarillado": "alcantarillado.png",
    "Otro": "otro.png",
}

# ------------------------------------------------------------------
# Datos
# ------------------------------------------------------------------
def cargar_df():
    df = pd.read_csv(DATA_CSV, encoding="utf-8")
    df["fecha_reporte"] = pd.to_datetime(df["fecha_reporte"])
    if "foto_url" not in df.columns:
        df["foto_url"] = ""
    if "descripcion" not in df.columns:
        df["descripcion"] = ""
    df["foto_url"] = df["foto_url"].fillna("")
    df["descripcion"] = df["descripcion"].fillna("")
    m = df["foto_url"] == ""
    df.loc[m, "foto_url"] = df.loc[m, "tipo_dano"].map(
        lambda t: f"assets/img/{IMG_TIPO.get(t, 'otro.png')}")
    return df


def cargar_veredas_geojson():
    with open(VEREDAS_GEO, "r", encoding="utf-8") as f:
        return json.load(f)


def option_list(columna, valor_todos):
    df = cargar_df()
    return ([{"label": valor_todos, "value": valor_todos}] +
            [{"label": str(v), "value": v} for v in sorted(df[columna].unique())])


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
            dbc.Col(dbc.Button([html.I(className="fa-solid fa-plus me-1"), " Nuevo reporte"],
                               id="btn_abrir_form", color="info", size="sm", className="text-nowrap"),
                    width="auto", className="ms-auto"),
            dbc.Col(dbc.Button([html.I(className="fa-solid fa-sun", id="icono_tema")],
                               id="btn_tema", color="outline-secondary", size="sm",
                               title="Alternar modo claro / oscuro", className="px-2"),
                    width="auto"),
        ], className="align-items-center g-2 py-1"),
        sticky="top", className="ce-navbar mb-3",
    ),

    dbc.Container([
        dbc.Row(id="kpis", className="g-2 mb-3"),
        dbc.Row([
            # Filtros
            dbc.Col(dbc.Card([
                dbc.CardHeader(html.Span("🎚️ Filtros", style={"font-weight": 600})),
                dbc.CardBody([
                    html.Label("Comuna", className="text-muted small mt-1"),
                    dcc.Dropdown(id="f_comuna", clearable=False, className="mb-2"),
                    html.Label("Tipo de daño", className="text-muted small"),
                    dcc.Dropdown(id="f_tipo", clearable=False, className="mb-2"),
                    html.Label("Canal de reporte", className="text-muted small"),
                    dcc.Dropdown(id="f_canal", clearable=False, className="mb-2"),
                    html.Label("Estado de gestión", className="text-muted small"),
                    dcc.Dropdown(id="f_estado", clearable=False, className="mb-2"),
                    html.Label("Rango de fechas", className="text-muted small mt-1"),
                    dcc.DatePickerRange(id="f_fechas", minimum_nights=0, className="mb-2",
                                        initial_visible_month=pd.Timestamp.now(),
                                        style={"font-size": ".78rem"}),
                    dbc.Button([html.I(className="fa-solid fa-rotate-left me-1"), " Restablecer"],
                               id="btn_reset", color="secondary", size="sm", outline=True, className="mt-2 w-100"),
                ]),
            ], className="surface shadow-sm border-0 mb-3"),
                width=12, lg=3, className="mb-3"),
            # Mapa + barras y canal
            dbc.Col([
                dbc.Card(dbc.CardBody([
                    dbc.Row([
                        dbc.Col(html.Span("🗺️ Mapa interactivo", style={"font-weight": 700}), width="auto"),
                        dbc.Col(html.Span("Haz clic en un punto 👆 · Carto/OpenStreetMap · datos simulados",
                                          className="text-muted", style={"font-size": ".72rem"}),
                                width="auto", className="ms-auto"),
                    ], className="align-items-center mb-1"),
                    dcc.Graph(id="mapa", config={"displayModeBar": False},
                              style={"height": "56vh"}),
                ]), className="surface shadow-sm border-0 mb-3"),
                dbc.Row([
                    dbc.Col(dbc.Card(dbc.CardBody([html.Span("📊 Reportes por tipo de daño",
                                                             style={"font-weight": 700}),
                                                   dcc.Graph(id="g_tipo", config={"displayModeBar": False},
                                                             style={"height": "26vh"}, className="mt-1")]),
                                     className="surface shadow-sm border-0 mb-3"),
                            width=12, md=6),
                    dbc.Col(dbc.Card(dbc.CardBody([html.Span("📱 Canal de reporte",
                                                             style={"font-weight": 700}),
                                                   dcc.Graph(id="g_canal", config={"displayModeBar": False},
                                                             style={"height": "26vh"}, className="mt-1")]),
                                     className="surface shadow-sm border-0 mb-3"),
                            width=12, md=6),
                ]),
            ], width=12, lg=9, className="mb-3"),
        ]),
        # Temporal a lo ancho
        dbc.Row(dbc.Col(dbc.Card(dbc.CardBody([html.Span("📈 Evolución diaria de reportes",
                                                         style={"font-weight": 700}),
                                               dcc.Graph(id="g_temporal", config={"displayModeBar": False},
                                                         style={"height": "22vh"}, className="mt-1")]),
                                className="surface shadow-sm border-0 mb-3"),
                        width=12)),
        # Tabla recientes
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
], fluid=True, className="g-3")


# ------------------------------------------------------------------
# Figuras
# ------------------------------------------------------------------
def figura_mapa(df_f):
    geo = cargar_veredas_geojson()
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
        paper_bgcolor="rgba(0,0,0,0)",
        map={"style": "carto-positron", "center": VILLAVICENCIO, "zoom": 11.35},
    )
    return fig


def barras_tipo(df_f):
    data = df_f.groupby("tipo_dano", as_index=False).size().rename(columns={"size": "n"})
    fig = px.bar(data, x="tipo_dano", y="n", color="tipo_dano",
                 color_discrete_map=COLOR_TIPO)
    fig.update_traces(marker_line_width=0, width=.55)
    fig.update_layout(margin=dict(l=15, r=8, t=4, b=0), height=260,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"size": 11},
                      xaxis={"showgrid": False, "title": "", "tickangle": -15,
                             "categoryorder": "total descending"},
                      yaxis={"showgrid": True, "gridcolor": "#2b3441", "gridwidth": .5,
                             "title": ""},
                      showlegend=False)
    return fig


def dona_canal(df_f):
    df_c = df_f.groupby("canal_reporte", as_index=False).size().rename(columns={"size": "n"})
    fig = px.pie(df_c, values="n", names="canal_reporte", hole=.45)
    fig.update_traces(textposition="inside", textinfo="label+percent",
                      textfont={"size": 10},
                      marker={"line": {"color": "rgba(0,0,0,0)", "width": 1.2}})
    fig.update_layout(margin=dict(l=8, r=8, t=4, b=4), height=260,
                      paper_bgcolor="rgba(0,0,0,0)", font={"size": 10.5},
                      showlegend=False)
    return fig


def area_temporal(df_f):
    t = df_f.groupby(df_f["fecha_reporte"].dt.date, as_index=False).size().rename(columns={"size": "n"})
    fig = go.Figure(go.Scatter(x=t["fecha_reporte"], y=t["n"], line_shape="spline",
                               mode="lines", fill="tozeroy",
                               line={"color": "#3498DB", "width": 2},
                               fillcolor="rgba(52,152,219,.18)"))
    fig.update_layout(margin=dict(l=25, r=10, t=4, b=0), height=250,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"size": 11},
                      xaxis={"showgrid": False, "title": ""},
                      yaxis={"showgrid": True, "gridcolor": "#2b3441", "gridwidth": .5,
                             "title": ""})
    return fig


def tabla_recientes_html(df_f, n=10):
    df_v = df_f.sort_values("fecha_reporte", ascending=False).head(n)
    filas = [html.Tr([
        html.Td(html.Code(r["id_reporte"], style={"font-size": ".74rem"})),
        html.Td(html.Span([html.Span("●", style={"color": COLOR_TIPO.get(r["tipo_dano"], "#999"),
                                                 "marginRight": 6}), r["tipo_dano"]])),
        html.Td(r["comuna"]),
        html.Td(r["canal_reporte"], className="d-none d-md-table-cell"),
        html.Td(dbc.Badge(r["estado_gestion"], color="secondary", className="d-block",
                          style={"font-size": ".68rem", "background": {
                              "Reportado": "#8e44ad", "En revisión": "#f39c12",
                              "Programado": "#2980b9", "Resuelto": "#27ae60"}.get(
                              r["estado_gestion"], "#555") if "estado_gestion" in r else "#555"})),
        html.Td(r["fecha_reporte"].strftime("%Y-%m-%d"), className="d-none d-md-table-cell"),
        html.Td(html.I(className="fa-solid fa-camera-retro text-secondary"
                       if "uploads/" in str(r.get("foto_url", "")) else
                       "fa-solid fa-images text-secondary",
                       **{"data-id": r["id_reporte"]}), style={"width": 30}),
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


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------
# 1. Cargar opciones de filtros + formulario al abrir la app
@callback(
    Output("f_comuna", "options"), Output("f_tipo", "options"),
    Output("f_canal", "options"), Output("f_estado", "options"),
    Output("f_fechas", "start_date"), Output("f_fechas", "end_date"),
    Output("n_tipo", "options"), Output("n_comuna", "options"),
    Output("n_canal", "options"),
    Output("modal_form", "is_open", allow_duplicate=True),
    Input("store_actualizado", "id"),
    prevent_initial_call="initial_duplicate",
)
def cargar_opciones_iniciales(_):
    df = cargar_df()
    return (option_list("comuna", "Todas"), option_list("tipo_dano", "Todos"),
            option_list("canal_reporte", "Todos"), option_list("estado_gestion", "Todos"),
            df["fecha_reporte"].min().date(), df["fecha_reporte"].max().date(),
            option_list("tipo_dano", "—"), option_list("comuna", "—"),
            option_list("canal_reporte", "—"), False)


# 2. Panel principal: KPIs + figuras
@callback(
    Output("kpis", "children"), Output("mapa", "figure"),
    Output("g_tipo", "figure"), Output("g_canal", "figure"),
    Output("g_temporal", "figure"), Output("tabla_recientes", "children"),
    Input("f_comuna", "value"), Input("f_tipo", "value"),
    Input("f_canal", "value"), Input("f_estado", "value"),
    Input("f_fechas", "start_date"), Input("f_fechas", "end_date"),
    Input("btn_reset", "n_clicks"), Input("store_actualizado", "modified_timestamp"),
)
def actualizar_dashboard(comuna, tipo, canal, estado, fi, ff, _reset, _ts):
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
              (f["fecha_reporte"] <= pd.Timestamp(ff) + pd.Timedelta(days=1))]

    top_tipo = f["tipo_dano"].mode()
    top_comuna = f.groupby("comuna").size().sort_values(ascending=False)
    pct_resueltos = (f["estado_gestion"] == "Resuelto").mean() * 100 if len(f) else 0

    def kpi_card(titulo, valor, icono, color):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([html.I(className=f"fa-solid {icono} me-2",
                             style={"color": color, "font-size": "1rem"}),
                      html.Span(titulo, className="text-muted", style={
                          "font-size": ".68rem", "letter-spacing": ".07em"})],
                     className="d-flex align-items-center mb-1"),
            html.H5(valor, className="mb-0", style={"font-weight": 700}),
        ]), className="surface shadow-sm border-0 h-100"), width=6, md=4, xl=2, className="mb-2")

    kpis = [
        kpi_card("TOTAL REPORTES", f"{len(f)}", "fa-clipboard-list", "#3498DB"),
        kpi_card("COMUNAS ACTIVAS", f"{f['comuna'].nunique()}", "fa-map", "#27AE60"),
        kpi_card("TIPO PREDOMINANTE", top_tipo.iloc[0] if len(top_tipo) else "—",
                 "fa-bolt", "#E67E22"),
        kpi_card("TOP COMUNA", top_comuna.index[0] if len(top_comuna) else "—",
                 "fa-circle-dot", "#9B59B6"),
        kpi_card("% RESUELTOS", f"{pct_resueltos:.1f}%", "fa-circle-check", "#E74C3C"),
        kpi_card("ÚLTIMA HORA", str(df["fecha_reporte"].max().strftime("%b %d")),
                 "fa-clock", "#1ABC9C"),
    ]

    return (kpis, figura_mapa(f), barras_tipo(f), dona_canal(f),
            area_temporal(f), tabla_recientes_html(f))


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
    Output("toast_nuevo", "is_open"),
    Output("toast_nuevo", "children"),
    Output("mapa", "figure", allow_duplicate=True),
    Output("tabla_recientes", "children", allow_duplicate=True),
    Input("dd_estado_nuevo", "value"),
    State("mapa", "clickData"),
    State("tabla_recientes", "children"),
    prevent_initial_call=True,
)
def cambiar_estado(nuevo_estado, click_data, tabla):
    if click_data and click_data.get("points"):
        id_rep = click_data["points"][0]["customdata"][0]
        df = cargar_df()
        df.loc[df["id_reporte"] == id_rep, "estado_gestion"] = nuevo_estado
        df.to_csv(DATA_CSV, index=False, encoding="utf-8")
        df_r = cargar_df()
        toast = html.Div([html.I(className="fa-solid fa-circle-check text-success me-2"),
                          f"Estado de {id_rep} actualizado a “{nuevo_estado}”"])
        return True, toast, figura_mapa(df_r), tabla_recientes_html(df_r)
    return no_update, no_update, no_update, no_update


# 5. Abrir/cerrar modal del formulario
@callback(
    Output("modal_form", "is_open", allow_duplicate=True),
    Input("btn_abrir_form", "n_clicks"),
    Input("btn_cancelar_form", "n_clicks"),
    Input("btn_enviar_form", "n_clicks"),
    State("upload_foto", "contents"),
    State("n_tipo", "value"),
    State("n_comuna", "value"),
    State("n_lat", "value"),
    State("n_lon", "value"),
    State("n_canal", "value"),
    State("n_estado", "value"),
    State("n_desc", "value"),
    prevent_initial_call=True,
)
def toggle_modal_form(abrir, cancelar, enviar, *_):
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
    ahora = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

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

    nueva = pd.DataFrame([{
        "id_reporte": nuevo_id,
        "fecha_reporte": ahora,
        "latitud": round(float(lat), 6),
        "longitud": round(float(lon), 6),
        "comuna": comuna,
        "tipo_dano": tipo,
        "canal_reporte": canal if canal else "App Ciudad Escucha",
        "estado_gestion": estado if estado else "Reportado",
        "origen_datos": "SIMULADO_FORMULARIO_APP",
        "foto_url": foto_url,
        "descripcion": (desc or "").strip(),
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
def sugerir(n_clicks, comuna):
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
                      paper_bgcolor="rgba(0,0,0,0)",
                      map={"style": "carto-positron",
                           "center": {"lat": lat, "lon": lon}, "zoom": 12.6})
    return lat, lon, fig, comuna_sel


# 8. Mini-mapa también al mover lat/lon manuales
@callback(
    Output("n_lat", "value"), Output("n_lon", "value"),
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
                      paper_bgcolor="rgba(0,0,0,0)",
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
    State("n_tipo", "options"), State("n_comuna", "options"),
    prevent_initial_call=True,
)
def reset_formulario(n, opts_tipo, opts_com):
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
    return True, toast, str(n)


@app.server.route("/health")
def _health():
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8505))
    print(f"🚀 Dashboard Ciudad Escucha (Dash) — http://localhost:{port}")
    app.run(debug=False, host="0.0.0.0", port=port)
