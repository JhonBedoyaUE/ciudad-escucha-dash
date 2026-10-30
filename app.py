#!/usr/bin/env python
"""
Dashboard Ciudad Escucha — versión Dash/Plotly
Sistema de reporte de daños en espacio público (datos SIMULADOS).
- Barra de filtros horizontal (flex-wrap) en lugar de columna lateral
- Mapa interactivo (Carto/Positron) con puntos-círculo por tipo de daño
- Límites de veredas DANE 2024 (GeoJSON filtrado en QGIS)
- Detalle del reporte con imagen al hacer clic en un punto
- Formulario para crear nuevos reportes (con subida de foto)
- Evolución acumulada (reportes / resueltos / pendientes) con `fecha_resolucion`
Autor: Jhon Bedoya — Habilidades Gerenciales
"""
import base64
import io
import json
import math
import os
import random
import socket
import time

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import (ALL, Dash, Input, Output, State, callback, ctx, dcc, html,
                  no_update)

from priorizacion import (  # reglas compartidas con scripts/generar_dataset.py
    DEPENDENCIA_POR_TIPO, DEPENDENCIAS, NIVELES_RIESGO, PRIORIDADES,
    calcular_prioridad, detalle_puntaje, vecinos_cercanos,
)

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
COLOR_PRIORIDAD = {
    "Alta": "#E74C3C",
    "Media": "#F39C12",
    "Baja": "#27AE60",
}
COLOR_DEPENDENCIA = {
    "Infraestructura": "#4C78A8",
    "Alborada": "#F58518",
    "EMAB": "#54A24B",
    "EDESA": "#72B7B2",
    "Gobierno/PQRSD": "#B279A2",
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

# Las gráficas de barras/embudo ya llevan la categoría escrita al lado: el color
# no añade información, así que se usa uno solo. El resaltado (filtro cruzado)
# mantiene el azul y apaga el resto en gris.
C_DATO = "#3498DB"
C_APAGADO = "rgba(148,163,184,.30)"
PALETA_COMUNA = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
                 "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC"]

# Dimensiones por las que se pueden colorear los puntos del mapa
CAMPOS_COLOR_MAPA = [
    {"label": "Tipo de daño", "value": "tipo_dano"},
    {"label": "Prioridad", "value": "prioridad"},
    {"label": "Dependencia", "value": "dependencia"},
    {"label": "Canal de reporte", "value": "canal_reporte"},
    {"label": "Comuna", "value": "comuna"},
    {"label": "Estado de gestión", "value": "estado_gestion"},
]

# ------------------------------------------------------------------
# Datos
# ------------------------------------------------------------------
COLUMNAS_TEXTO = ("barrio", "dependencia", "riesgo", "prioridad", "descripcion",
                  "foto_url", "origen_datos")

ORDEN_COLUMNAS = ["id_reporte", "fecha_reporte", "latitud", "longitud", "comuna",
                  "barrio", "tipo_dano", "canal_reporte", "estado_gestion",
                  "dependencia", "riesgo", "reporte_repetido", "fecha_resolucion",
                  "dias_respuesta", "puntaje_prioridad", "prioridad",
                  "origen_datos", "foto_url", "descripcion"]


def cargar_df():
    df = pd.read_csv(DATA_CSV, encoding="utf-8")
    # Compatibilidad con el esquema anterior del dataset
    if "fecha_resolucion" not in df.columns and "resuelta_en" in df.columns:
        df["fecha_resolucion"] = df["resuelta_en"]
    df["fecha_reporte"] = pd.to_datetime(df["fecha_reporte"])
    for col in COLUMNAS_TEXTO:
        if col not in df.columns:
            df[col] = ""
    if "reporte_repetido" not in df.columns:
        df["reporte_repetido"] = False
    df["reporte_repetido"] = (df["reporte_repetido"].astype(str)
                              .str.lower().isin(["true", "1", "si", "sí"]))
    if "dias_respuesta" not in df.columns:
        df["dias_respuesta"] = ""
    if "puntaje_prioridad" not in df.columns:
        df["puntaje_prioridad"] = 0
    df["puntaje_prioridad"] = pd.to_numeric(df["puntaje_prioridad"], errors="coerce").fillna(0)
    for col in COLUMNAS_TEXTO:
        df[col] = df[col].fillna("").astype(str)
    df["foto_url"] = df["foto_url"].fillna("").astype(str)
    df["descripcion"] = df["descripcion"].fillna("").astype(str)
    # pandas lee las celdas vacías como NaN; `fecha_resolucion` se necesita como
    # fecha para calcular el saldo de pendientes en cada punto del tiempo.
    df["fecha_resolucion"] = pd.to_datetime(df["fecha_resolucion"], errors="coerce")
    m = df["foto_url"] == ""
    df.loc[m, "foto_url"] = df.loc[m, "tipo_dano"].map(
        lambda t: f"assets/img/{IMG_TIPO.get(t, 'otro.png')}")
    return df


def guardar_csv(df):
    """Escribe el CSV con las fechas en un formato fijo.

    pandas 3 conserva la unidad (µs) de `fecha_resolucion` y al volcar añadía
    ".000000"; con strftime el archivo queda idéntico al que lee la app.
    """
    out = df.copy()
    out["fecha_reporte"] = pd.to_datetime(out["fecha_reporte"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    out["fecha_resolucion"] = (pd.to_datetime(out["fecha_resolucion"], errors="coerce")
                               .dt.strftime("%Y-%m-%d %H:%M:%S").fillna(""))
    out["reporte_repetido"] = out["reporte_repetido"].astype(bool)
    out.to_csv(DATA_CSV, index=False, encoding="utf-8")


def cargar_veredas_geojson():
    with open(VEREDAS_GEO, "r", encoding="utf-8") as f:
        return json.load(f)


def option_list(df, columna, valor_todos):
    return ([{"label": valor_todos, "value": valor_todos}] +
            [{"label": str(v), "value": v} for v in sorted(df[columna].unique())])


def filtrar(df, comuna, tipo, canal, estado, fi, ff, prioridad=None, dependencia=None):
    f = df.copy()
    if comuna and comuna != "Todas":
        f = f[f["comuna"] == comuna]
    if tipo and tipo != "Todos":
        f = f[f["tipo_dano"] == tipo]
    if canal and canal != "Todos":
        f = f[f["canal_reporte"] == canal]
    if estado and estado != "Todos":
        f = f[f["estado_gestion"] == estado]
    if prioridad and prioridad != "Todas":
        f = f[f["prioridad"] == prioridad]
    if dependencia and dependencia != "Todas":
        f = f[f["dependencia"] == dependencia]
    if fi and ff:
        f = f[(f["fecha_reporte"] >= pd.Timestamp(fi)) &
              (f["fecha_reporte"] < pd.Timestamp(ff) + pd.Timedelta(days=1))]
    return f


def form_nuevo_reporte():
    return dbc.Row([
        dbc.Col([
            html.Label("Tipo de daño", className="text-muted small mt-1"),
            dcc.Dropdown(id="n_tipo", clearable=False),
            dbc.Row([
                dbc.Col([html.Label("Comuna", className="text-muted small mt-2"),
                         dbc.Select(id="n_comuna")], width=6),
                dbc.Col([html.Label("Canal de reporte", className="text-muted small mt-2"),
                         dbc.Select(id="n_canal")], width=6),
            ]),
            dbc.Row([
                dbc.Col([html.Label("Barrio", className="text-muted small mt-2"),
                         dbc.Select(id="n_barrio")], width=6),
                dbc.Col([html.Label("Riesgo percibido", className="text-muted small mt-2"),
                         dbc.Select(id="n_riesgo", options=NIVELES_RIESGO,
                                    value="Medio")], width=6),
            ]),
            dbc.Row([
                dbc.Col([html.Label("Estado", className="text-muted small mt-2"),
                         dbc.Select(id="n_estado",
                                    options=["Reportado", "En revisión", "Programado", "Resuelto"])],
                        width=6),
                dbc.Col([html.Label("Prioridad calculada", className="text-muted small mt-2"),
                         html.Div(id="n_prioridad", className="pt-1")], width=6),
            ]),
            html.Div([html.I(className="fa-solid fa-arrow-right-long me-2"),
                      html.Span("Dependencia responsable: ", className="text-muted"),
                      html.Span(id="n_dependencia", style={"fontWeight": 600})],
                     className="small mt-2"),
            html.Label("Descripción del problema", className="text-muted small mt-2"),
            dbc.Textarea(id="n_desc", rows=3,
                         placeholder="Ej: 'Alumbrado público descompuesto frente a la vereda...'"),
            html.Label("📸 Foto del problema (opcional)", className="text-muted small mt-2"),
            dcc.Upload(
                id="upload_foto",
                children=html.Div([
                    html.I(className="fa-solid fa-cloud-arrow-up fa-2x text-secondary d-block my-1"),
                    html.Div("Arrastra una foto o haz clic"),
                    html.Div("(JPG / PNG)", className="text-muted", style={"font-size": ".7rem"}),
                ]),
                style={"width": "100%", "minHeight": 96, "borderWidth": "1px",
                       "borderStyle": "dashed", "borderRadius": 8,
                       "textAlign": "center", "padding": "12px 8px"},
                className="mb-1", multiple=False,
            ),
            html.Img(id="preview_foto", src="", style={
                "maxHeight": 120, "display": "none", "borderRadius": 8}),
            html.Div(id="preview_texto", className="text-muted small"),
        ], width=12, lg=6),

        # ---- Ubicación: se fija con un clic en el mapa o con el GPS del equipo ----
        dbc.Col([
            html.Label("📍 Ubicación del problema", className="text-muted small mt-1"),
            html.Div("Haz clic en el mapa para marcar el punto exacto.",
                     className="text-muted", style={"font-size": ".7rem"}),
            html.Div([
                dcc.Graph(id="mini_mapa", style={"height": "230px"},
                          config={"displayModeBar": False, "scrollZoom": False,
                                  "doubleClick": False, "staticPlot": True}),
                # capa transparente: Plotly no emite clic sobre el fondo del mapa
                html.Div(id="capa_clic_mapa", title="Haz clic para fijar el punto"),
            ], className="ce-mapa-wrap mt-1"),
            dbc.Row([
                dbc.Col(dbc.Button([html.I(className="fa-solid fa-crosshairs me-1"),
                                    " Usar mi ubicación"], id="btn_gps", color="secondary",
                                   size="sm", outline=True, className="w-100"),
                        width=6),
                dbc.Col(dbc.Button([html.I(className="fa-solid fa-dice me-1"),
                                    " Punto sugerido"], id="btn_sugerir_punto",
                                   color="secondary", size="sm", outline=True,
                                   className="w-100"), width=6),
            ], className="g-2 mt-1"),
            html.Div(html.Code(id="txt_coords", children="sin punto seleccionado"),
                     className="mt-2", style={"font-size": ".78rem"}),
            html.Div(id="txt_geo", className="text-muted", style={"font-size": ".7rem"}),
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
            html.Div([html.Label("Prioridad", className="ce-f-label"),
                      dcc.Dropdown(id="f_prioridad", clearable=False)], className="ce-f-item"),
            html.Div([html.Label("Dependencia", className="ce-f-label"),
                      dcc.Dropdown(id="f_dependencia", clearable=False)], className="ce-f-item"),
            html.Div([html.Label("Rango de fechas", className="ce-f-label"),
                      dcc.DatePickerRange(id="f_fechas", minimum_nights=0,
                                          initial_visible_month=pd.Timestamp.now(),
                                          style={"fontSize": ".78rem"})],
                     className="ce-f-item ce-f-fechas"),
            html.Div([
                dbc.Button([html.I(className="fa-solid fa-download me-1"), "CSV"],
                           id="btn_descargar", color="secondary", size="sm",
                           outline=True, className="text-nowrap me-2",
                           title="Descargar los reportes filtrados"),
                dbc.Button([html.I(className="fa-solid fa-rotate-left me-1"),
                            "Restablecer"], id="btn_reset", color="secondary",
                           size="sm", outline=True, className="text-nowrap"),
            ], className="ce-f-item ce-f-btn"),
        ], className="ce-filtros"),
    ]), className="surface shadow-sm border-0 mb-3")


def tarjeta_mapa():
    """Tarjeta del mapa: incluye el selector de color de los puntos y la leyenda."""
    return dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Span([html.I(className="fa-solid fa-map-location-dot me-2"),
                               "Mapa interactivo"], style={"font-weight": 700}),
                    width="auto"),
            dbc.Col(html.Span(id="mapa_nota", className="text-muted d-none d-lg-block",
                              style={"font-size": ".72rem",
                                     "margin-left": ".6rem"}),
                    width="auto", className="align-self-center"),
            dbc.Col([
                dbc.RadioItems(
                    id="vista_mapa", value="puntos", inline=True,
                    className="ce-segmentado me-3",
                    options=[{"label": html.Span([html.I(className="fa-solid fa-circle "
                                                         "me-1"), "Puntos"]),
                              "value": "puntos"},
                             {"label": html.Span([html.I(className="fa-solid fa-fire "
                                                         "me-1"), "Calor"]),
                              "value": "calor"}],
                    inputClassName="btn-check", labelClassName="btn btn-sm btn-outline-secondary",
                ),
                html.Span("Colorear por", id="lbl_color_mapa", className="text-muted me-2",
                          style={"font-size": ".72rem"}),
                dbc.Select(id="color_mapa", size="sm", options=CAMPOS_COLOR_MAPA,
                           value="tipo_dano", className="ce-select-inline d-inline-block"),
            ], width="auto", className="ms-auto d-flex align-items-center"),
        ], className="align-items-center g-2 mb-1"),
        html.Div(id="leyenda_mapa", className="ce-leyenda mb-1"),
        dcc.Graph(id="mapa", config={"displayModeBar": False},
                  style={"height": "70vh"}, className="mt-1"),
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

        # ---------- Indicador del Plan de Desarrollo + priorización ----------
        dbc.Row([
            dbc.Col(tarjeta("Plan de Desarrollo · Villavo Somos Todos", "fa-bullseye",
                            "g_plan", "132px",
                            "216 de 300 km · LED 50 % → meta 90 %"),
                    width=12, xl=4),
            dbc.Col(tarjeta("Reportes por prioridad", "fa-flag", "g_prioridad", "165px",
                            "clic en una barra para filtrar"),
                    width=12, md=6, xl=3),
            dbc.Col(tarjeta("Ranking de comunas por prioridad", "fa-ranking-star",
                            "g_ranking", "195px",
                            "60 % altas + 25 % pendientes + 15 % antigüedad"),
                    width=12, md=6, xl=5),
        ], className="g-3 mb-3"),

        # ---------- Mapa (25 % más alto) + tipo/canal apilados a la derecha ----------
        dbc.Row([
            dbc.Col(tarjeta_mapa(), width=12, xl=8, className="mb-0"),
            dbc.Col([
                tarjeta("Reportes por tipo de daño", "fa-chart-column", "g_tipo", "32vh",
                        "clic en una barra para filtrar"),
                tarjeta("Canal de reporte", "fa-filter", "g_canal", "32vh",
                        "clic en una etapa para filtrar"),
            ], width=12, xl=4),
        ], className="g-3 mb-3"),

        # ---------- Parte inferior: visible al hacer scroll ----------
        dbc.Row(dbc.Col(
            tarjeta("Evolución acumulada: reportes, resueltos y pendientes",
                    "fa-chart-line", "g_evol", "38vh",
                    "saldo = reportes creados − resueltos a esa fecha (usa fecha_resolucion)"),
                   width=12), className="g-3 mb-3"),

        dbc.Row([
            dbc.Col(tarjeta("Entradas y salidas por semana", "fa-right-left",
                            "g_semana", "28vh", "clic en una semana para filtrar"),
                    width=12, md=6, xl=3),
            dbc.Col(tarjeta("Reportes por comuna", "fa-map", "g_comuna", "28vh",
                            "clic en una comuna para filtrar"),
                    width=12, md=6, xl=3),
            dbc.Col(tarjeta("Tiempo medio por tipo de daño", "fa-stopwatch",
                            "g_resolucion", "28vh", "clic para filtrar por tipo"),
                    width=12, md=6, xl=3),
            dbc.Col(tarjeta("Tiempo de respuesta por dependencia", "fa-building-columns",
                            "g_dependencia", "28vh", "días entre reporte y resolución"),
                    width=12, md=6, xl=3),
        ], className="g-3 mb-3"),

        # ---------- Detalle del registro seleccionado + tabla paginada ----------
        dbc.Row([
            dbc.Col(dbc.Card([
                dbc.CardHeader(html.Span([html.I(className="fa-solid fa-file-circle-check me-2"),
                                          "Detalle del reporte"])),
                dbc.CardBody(html.Div(id="panel_detalle")),
            ], className="surface shadow-sm border-0 mb-4 h-100"),
                width=12, lg=4, xl=3, className="mb-0"),
            dbc.Col(dbc.Card([
                dbc.CardHeader(dbc.Row([
                    dbc.Col(html.Span([html.I(className="fa-solid fa-list me-2"),
                                       "Reportes registrados"]),
                            width="auto", className="align-self-center"),
                    dbc.Col([
                        html.Span(id="info_pagina", className="text-muted me-3",
                                  style={"font-size": ".74rem"}),
                        dbc.Select(id="tam_pagina", size="sm",
                                   options=[{"label": f"{n} por página", "value": n}
                                            for n in (10, 25, 50, 100)],
                                   value=10, className="ce-tam-pagina d-inline-block align-middle me-2"),
                        dbc.Button([html.I(className="fa-solid fa-chevron-left")], id="btn_pag_prev",
                                   color="secondary", outline=True, size="sm",
                                   className="me-1 px-2", title="Página anterior"),
                        dbc.Button([html.I(className="fa-solid fa-chevron-right")], id="btn_pag_next",
                                   color="secondary", outline=True, size="sm",
                                   className="px-2", title="Página siguiente"),
                    ], width="auto", className="ms-auto d-flex align-items-center"),
                ], className="align-items-center g-2 flex-wrap")),
                dbc.CardBody(html.Div(id="tabla_recientes")),
            ], className="surface shadow-sm border-0 mb-4 h-100"),
                width=12, lg=8, xl=9, className="mb-0"),
        ], className="g-3"),

        html.Hr(className="border-dark"),
        html.P(["🚨 DATOS SIMULADOS · PROYECTO ACADÉMICO · Habilidades Gerenciales · "
                "Autor: Jhon Bedoya (Analista) · Veredas: shapefile DANE 2024 filtrado en QGIS",
                html.Br(),
                html.Span(f"Servido desde {socket.gethostname()} · "
                          f"sesión iniciada {pd.Timestamp.now():%Y-%m-%d %H:%M}",
                          style={"font-size": ".72rem"})],
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
    dcc.Store(id="store_pagina", data=1),
    dcc.Download(id="descarga_csv"),
    dcc.Store(id="store_seleccion"),
    dcc.Store(id="store_punto"),      # ubicación elegida en el formulario
    dcc.Store(id="store_gps"),        # la llena assets/geo.js con navigator.geolocation
    dcc.Store(id="store_click"),      # la llena assets/mapa_punto.js al clicar el mapa
], fluid=True, className="g-3")


# ------------------------------------------------------------------
# Figuras
# ------------------------------------------------------------------
def figura_mapa(df_f, tema="dark", campo="tipo_dano", vista="puntos"):
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
    if len(df_m) and vista == "calor":
        # Densidad: el color representa concentración, no la categoría
        fig.add_trace(go.Densitymap(
            lat=df_m["latitud"], lon=df_m["longitud"],
            radius=17, opacity=0.78,
            colorscale=[[0, "rgba(52,152,219,0)"], [0.25, "#3498DB"],
                        [0.55, "#F1C40F"], [0.8, "#E67E22"], [1, "#E74C3C"]],
            showscale=False, hoverinfo="skip",
        ))
    elif len(df_m):
        df_m["fecha_s"] = df_m["fecha_reporte"].dt.strftime("%Y-%m-%d %H:%M")
        paleta = paleta_campo(campo, df_m[campo].unique())
        fig.add_trace(go.Scattermap(
            lat=df_m["latitud"], lon=df_m["longitud"], mode="markers",
            marker={"size": 11, "color": df_m[campo].map(paleta),
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


def paleta_campo(campo, valores):
    """Color por valor del campo con el que se pintan los puntos del mapa.

    El orden del diccionario es el de la leyenda: el fijo de cada dimensión
    (no el de aparición en los datos)."""
    base = {"tipo_dano": COLOR_TIPO,
            "canal_reporte": COLOR_CANAL,
            "estado_gestion": COLOR_ESTADO,
            "prioridad": COLOR_PRIORIDAD,
            "dependencia": COLOR_DEPENDENCIA}.get(campo)
    if base:
        orden = ([v for v in base if v in set(valores)] +
                 [v for v in valores if v not in base])
        return {v: base.get(v, "#95A5A6") for v in orden}
    if campo == "comuna":
        orden = sorted(valores, key=lambda c: int(str(c).split()[-1])
                       if str(c).split()[-1].isdigit() else 99)
        return {v: PALETA_COMUNA[i % len(PALETA_COMUNA)] for i, v in enumerate(orden)}
    return {v: COLOR_TIPO.get(v, "#95A5A6") for v in valores}


def leyenda_mapa_html(df_f, campo):
    """Leyenda de puntos del mapa (HTML, para controlar el estilo)."""
    presentes = set(df_f[campo])
    paleta = {v: c for v, c in paleta_campo(campo, df_f[campo].unique()).items()
              if v in presentes}
    if not paleta:
        return html.Span("Sin datos para la leyenda", className="text-muted",
                         style={"fontSize": ".72rem"})
    return [html.Span([html.Span("●", style={"color": color, "marginRight": 5,
                                             "fontSize": ".85rem"}), str(v)],
                      className="ce-leyenda-item") for v, color in paleta.items()]


def _rgba(color, alfa):
    """#RRGGBB -> rgba(), para atenuar la categoría no seleccionada."""
    h = color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alfa})"


def _colores_categoria(categorias, seleccion, color=C_DATO):
    """Un solo color para todas las barras; si hay filtro cruzado, la categoría
    elegida conserva el color y el resto se apaga (ya hay etiquetas que
    identifican cada categoría, el color no aporta información extra)."""
    if not seleccion or str(seleccion) in ("Todos", "Todas"):
        return [color] * len(categorias)
    return [color if str(cat) == str(seleccion) else C_APAGADO for cat in categorias]


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


def barras_tipo(df_f, seleccion=None):
    if df_f.empty:
        return _fig_vacia()
    data = (df_f.groupby("tipo_dano").size().rename("n").reset_index()
            .sort_values("n", ascending=True))
    fig = go.Figure(go.Bar(
        x=data["n"], y=data["tipo_dano"], orientation="h",
        marker={"color": _colores_categoria(data["tipo_dano"], seleccion),
                "cornerradius": 5, "line": {"width": 0}},
        text=data["n"], textposition="outside", cliponaxis=False,
        textfont={"size": 13},
        hovertemplate="%{y}: <b>%{x}</b> reportes<extra></extra>",
    ))
    fig = _layout_base(fig, 250, categorias=True)
    fig.update_layout(margin=dict(l=112, r=30, t=6, b=6))
    return fig


def embudo_canal(df_f, seleccion=None):
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
        marker={"color": _colores_categoria(df_c["canal_reporte"], seleccion),
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
    # El eje se limita al rango de reportes seleccionado: si el filtro cubre una
    # semana, no se estira hasta las fechas de resolución de meses posteriores
    # (las resoluciones fuera del rango simplemente no entran en la serie).
    fin = f["creado"].max()
    dias = pd.date_range(inicio, fin, freq="D")
    nuevos = f.groupby("creado").size().reindex(dias, fill_value=0)
    resueltos = (f["fecha_resolucion"].dropna().dt.normalize().value_counts()
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
    fig.update_xaxes(tickformat="%d %b", nticks=min(8, max(2, len(dias))))
    return fig


def fig_semanal(df_f):
    if df_f.empty:
        return _fig_vacia()
    f = df_f.copy()
    nuevos = (f["fecha_reporte"].dt.to_period("W-MON").dt.start_time
              .value_counts().sort_index())
    # Solo cuentan las resoluciones ocurridas dentro de la ventana seleccionada
    dia_ini = f["fecha_reporte"].dt.normalize().min()
    dia_fin = f["fecha_reporte"].dt.normalize().max()
    r = f["fecha_resolucion"].dropna().dt.normalize()
    resueltos = (r[(r >= dia_ini) & (r <= dia_fin)]
                 .dt.to_period("W-MON").dt.start_time.value_counts().sort_index())
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


def fig_comunas(df_f, seleccion=None):
    if df_f.empty:
        return _fig_vacia()
    data = (df_f.groupby("comuna").size().rename("n").reset_index()
            .sort_values("n", ascending=True))
    fig = go.Figure(go.Bar(
        x=data["n"], y=data["comuna"], orientation="h",
        marker={"color": _colores_categoria(data["comuna"], seleccion),
                "cornerradius": 5, "line": {"width": 0}},
        text=data["n"], textposition="outside", cliponaxis=False,
        textfont={"size": 13},
        hovertemplate="%{y}: <b>%{x}</b> reportes<extra></extra>",
    ))
    fig = _layout_base(fig, 230, categorias=True)
    fig.update_layout(margin=dict(l=82, r=30, t=6, b=6))
    return fig


def fig_resolucion(df_f, seleccion=None):
    r = df_f.dropna(subset=["fecha_resolucion"]).copy()
    if r.empty:
        return _fig_vacia("Todavía no hay reportes resueltos")
    r["dias"] = (r["fecha_resolucion"] - r["fecha_reporte"]).dt.total_seconds() / 86400
    g = r.groupby("tipo_dano").agg(dias=("dias", "mean"), n=("dias", "size")).reset_index()
    g = g.sort_values("dias")
    fig = go.Figure(go.Bar(
        x=g["dias"], y=g["tipo_dano"], orientation="h",
        marker={"color": _colores_categoria(g["tipo_dano"], seleccion),
                "cornerradius": 5, "line": {"width": 0}},
        text=[f"{d:.1f} d" for d in g["dias"]], textposition="outside",
        cliponaxis=False, textfont={"size": 13},
        customdata=g[["n"]].values.tolist(),
        hovertemplate="%{y}: <b>%{x:.1f}</b> días de media (%{customdata[0]} resueltos)"
                      "<extra></extra>",
    ))
    fig = _layout_base(fig, 230, categorias=True)
    fig.update_layout(margin=dict(l=108, r=48, t=6, b=6))
    return fig




# ------------------------------------------------------------------
# Plan de Desarrollo, priorización y dependencias
# ------------------------------------------------------------------
META_VIAS_KM = 300.0        # meta del Plan "Villavo Somos Todos 2024-2027"
VIAS_AVANCE_KM = 216.0      # km intervenidos a mayo de 2026 (fuente oficial)
META_LED = 90.0             # % de alumbrado modernizado
LED_AVANCE = 50.0           # % a finales de 2025 (fuente oficial)


def _gauge(valor, meta, titulo, sufijo, color, dominio):
    return go.Indicator(
        mode="gauge+number",
        value=valor,
        domain=dominio,
        number={"suffix": sufijo, "font": {"size": 21}},
        title={"text": f"<b>{titulo}</b><br>"
                       f"<span style='font-size:10.5px'>{valor:.0f} de {meta:.0f}{sufijo}</span>",
               "font": {"size": 11}},
        gauge={
            "axis": {"visible": False, "range": [0, meta]},
            "bar": {"color": color, "thickness": .62},
            "bgcolor": "rgba(148,163,184,.12)",
            "borderwidth": 0,
            "threshold": {"line": {"color": "#E74C3C", "width": 3},
                          "thickness": .9, "value": meta},
        },
    )


def fig_plan_desarrollo(df_f):
    """Indicadores del Plan de Desarrollo (requisito de la rúbrica).

    Parte del avance oficial publicado (216 de 300 km de vías y 50 % de LED) y
    le suma la evidencia ciudadana del periodo filtrado, con supuestos
    declarados: 1 reporte de vías ≈ 0.25 km priorizados y 30 puntos de LED por
    cada 1000 reportes de alumbrado.
    """
    vias = int((df_f["tipo_dano"] == "Vías").sum())
    luminarias = int((df_f["tipo_dano"] == "Alumbrado público").sum())
    km_total = min(META_VIAS_KM, VIAS_AVANCE_KM + round(vias * 0.25, 1))
    led_total = min(META_LED, LED_AVANCE + luminarias / 1000 * 30)

    fig = go.Figure()
    fig.add_trace(_gauge(km_total, META_VIAS_KM, "Vías intervenidas", " km",
                         "#3498DB", {"x": [0.0, 0.48], "y": [0, 0.8]}))
    fig.add_trace(_gauge(led_total, META_LED, "Alumbrado LED", " %",
                         "#1ABC9C", {"x": [0.52, 1.0], "y": [0, 0.8]}))
    fig.update_layout(margin=dict(l=6, r=6, t=16, b=0), height=150,
                      paper_bgcolor=TRANS, showlegend=False, font={"size": 11})
    return fig


def fig_prioridades(df_f, seleccion=None):
    """Reportes por nivel de prioridad (Alta / Media / Baja).

    Aquí el color sí aporta: es el semáforo de priorización.
    """
    if df_f.empty:
        return _fig_vacia()
    data = (df_f.groupby("prioridad").size().reindex(PRIORIDADES, fill_value=0)
            .rename("n").reset_index().iloc[::-1])   # Alta arriba
    colores = [COLOR_PRIORIDAD.get(p, C_DATO) for p in data["prioridad"]]
    if seleccion and seleccion != "Todas":
        colores = [c if p == seleccion else C_APAGADO
                   for c, p in zip(colores, data["prioridad"])]
    fig = go.Figure(go.Bar(
        x=data["n"], y=data["prioridad"], orientation="h",
        marker={"color": colores, "cornerradius": 5, "line": {"width": 0}},
        text=data["n"].astype(int), textposition="outside", cliponaxis=False,
        textfont={"size": 13},
        hovertemplate="Prioridad %{y}: <b>%{x}</b> reportes<extra></extra>",
    ))
    fig = _layout_base(fig, 150, categorias=True)
    fig.update_layout(margin=dict(l=72, r=34, t=4, b=4))
    return fig


def fig_ranking_comunas(df_f):
    """Ranking de comunas por índice de prioridad (entregable del Analista)."""
    if df_f.empty:
        return _fig_vacia()
    hoy = pd.Timestamp.now()
    filas = []
    for comuna, g in df_f.groupby("comuna"):
        total = len(g)
        altas = float((g["prioridad"] == "Alta").mean() * 100)
        pendientes = g[g["fecha_resolucion"].isna()]
        pct_pend = len(pendientes) / total * 100 if total else 0
        dias = (((hoy - pendientes["fecha_reporte"]).dt.days.clip(lower=0).mean())
                if len(pendientes) else 0.0)
        filas.append({"comuna": comuna, "altas": altas, "pendientes": pct_pend,
                      "dias": float(dias), "n": total,
                      "n_altas": int((g["prioridad"] == "Alta").sum())})
    rk = pd.DataFrame(filas)
    max_dias = max(1.0, rk["dias"].max())
    rk["indice"] = (0.60 * rk["altas"] + 0.25 * rk["pendientes"]
                    + 0.15 * (rk["dias"] / max_dias * 100)).round(1)
    rk = rk.sort_values("indice", ascending=True)

    # Los tres primeros puestos se resaltan: es un ranking de atención
    colores = ["#E74C3C" if p >= len(rk) - 3 else "#4C78A8" for p in range(len(rk))]
    fig = go.Figure(go.Bar(
        x=rk["indice"], y=rk["comuna"], orientation="h",
        marker={"color": colores, "cornerradius": 5, "line": {"width": 0}},
        text=[f"{v:.0f}" for v in rk["indice"]], textposition="outside",
        cliponaxis=False, textfont={"size": 12.5},
        customdata=rk[["n_altas", "n"]].values.tolist(),
        hovertemplate=("%{y}: índice <b>%{x:.1f}</b><br>"
                       "%{customdata[0]} de %{customdata[1]} reportes en prioridad alta"
                       "<extra></extra>"),
    ))
    fig = _layout_base(fig, 195, categorias=True)
    fig.update_layout(margin=dict(l=82, r=42, t=6, b=6))
    fig.update_xaxes(range=[0, 100], tickvals=[0, 25, 50, 75, 100])
    return fig


def fig_dependencias(df_f, seleccion=None):
    """Tiempo medio de respuesta por dependencia (días)."""
    r = df_f.dropna(subset=["fecha_resolucion"]).copy()
    if r.empty:
        return _fig_vacia("Todavía no hay reportes resueltos")
    r["dias"] = (r["fecha_resolucion"] - r["fecha_reporte"]).dt.total_seconds() / 86400
    g = (r.groupby("dependencia")
         .agg(dias=("dias", "mean"), n=("dias", "size")).reset_index()
         .sort_values("dias"))
    fig = go.Figure(go.Bar(
        x=g["dias"], y=g["dependencia"], orientation="h",
        marker={"color": _colores_categoria(g["dependencia"], seleccion),
                "cornerradius": 5, "line": {"width": 0}},
        text=[f"{d:.1f} d" for d in g["dias"]], textposition="outside",
        cliponaxis=False, textfont={"size": 13},
        customdata=g[["n"]].values.tolist(),
        hovertemplate="%{y}: <b>%{x:.1f}</b> días de media (%{customdata[0]} resueltos)"
                      "<extra></extra>",
    ))
    fig = _layout_base(fig, 230, categorias=True)
    fig.update_layout(margin=dict(l=116, r=48, t=6, b=6))
    return fig




def tabla_recientes_html(df_f, pagina=1, tam=10, seleccion=None):
    """Tabla paginada de reportes (más recientes primero).

    Devuelve (tabla, texto_de_rango, pagina_efectiva, total_paginas).
    """
    total = len(df_f)
    paginas = max(1, math.ceil(total / tam))
    pagina = min(max(1, int(pagina or 1)), paginas)
    ini = (pagina - 1) * tam
    df_v = (df_f.sort_values("fecha_reporte", ascending=False)
            .iloc[ini:ini + tam])
    filas = [html.Tr([
        html.Td(html.Code(r["id_reporte"], style={"font-size": ".74rem"})),
        html.Td(html.Span([html.Span("●", style={"color": COLOR_TIPO.get(r["tipo_dano"], "#999"),
                                                 "marginRight": 6}), r["tipo_dano"]])),
        html.Td(r["comuna"]),
        html.Td(dbc.Badge(r["prioridad"] or "—", style={
            "font-size": ".66rem",
            "background": COLOR_PRIORIDAD.get(r["prioridad"], "#555")})),
        html.Td(r["canal_reporte"], className="d-none d-md-table-cell"),
        html.Td(dbc.Badge(r["estado_gestion"], className="d-block",
                          style={"font-size": ".68rem",
                                 "background": COLOR_ESTADO.get(r["estado_gestion"], "#555")})),
        html.Td(r["fecha_reporte"].strftime("%Y-%m-%d"), className="d-none d-md-table-cell"),
        html.Td(html.I(className="fa-solid fa-camera-retro text-secondary"
                       if "uploads/" in str(r["foto_url"]) else
                       "fa-solid fa-images text-secondary"),
                style={"width": 30}),
    ], id={"type": "fila_reporte", "index": r["id_reporte"]}, n_clicks=0,
        className=("ce-fila border-dark border-top"
                   + (" ce-fila-sel" if r["id_reporte"] == seleccion else "")),
        style={"font-size": ".8rem"})
        for _, r in df_v.iterrows()]
    tabla = html.Table([
        html.Thead(html.Tr([html.Th("ID", style={"font-size": ".7rem"}),
                            html.Th("Tipo", style={"font-size": ".7rem"}),
                            html.Th("Comuna", style={"font-size": ".7rem"}),
                            html.Th("Prioridad", style={"font-size": ".7rem"}),
                            html.Th("Canal", className="d-none d-md-table-cell",
                                    style={"font-size": ".7rem"}),
                            html.Th("Estado", style={"font-size": ".7rem"}),
                            html.Th("Fecha", className="d-none d-md-table-cell",
                                    style={"font-size": ".7rem"}),
                            html.Th("📷", style={"font-size": ".7rem"})],
                           className="text-muted")),
        html.Tbody(filas),
    ], className="table-responsive table-sm table-hover mb-0")

    if total:
        texto = (f"Mostrando {ini + 1:,}–{ini + len(df_v):,} de {total:,} reportes".replace(",", " ")
                 + f" · página {pagina} de {paginas}")
    else:
        texto = "Sin reportes con los filtros actuales"
    return tabla, texto, pagina, paginas


def panel_detalle_html(id_rep):
    """Detalle del reporte seleccionado en la tabla, con el mismo aspecto de
    las tarjetas de gráficos (no un modal)."""
    if not id_rep:
        return html.Div([
            html.I(className="fa-solid fa-hand-pointer fa-2x text-secondary mb-2"),
            html.P("Haz clic en una fila de la tabla para ver aquí el reporte completo.",
                   className="text-muted small mb-0"),
        ], className="text-center py-5 ce-panel-vacio")

    df = cargar_df()
    fila = df[df["id_reporte"] == id_rep]
    if fila.empty:
        return html.Div([html.P("El reporte ya no existe (puede haberse filtrado).",
                                className="text-muted small mb-0")],
                        className="text-center py-4")
    r = fila.iloc[0]
    tipo = r["tipo_dano"]
    foto = str(r["foto_url"]) or f"assets/img/{IMG_TIPO.get(tipo, 'otro.png')}"
    resuelta = r["fecha_resolucion"]
    resuelta_txt = ("— sin resolver —" if pd.isna(resuelta)
                    else resuelta.strftime("%Y-%m-%d %H:%M"))

    def campo(etiqueta, valor, color=None):
        return html.Div([
            html.Div(etiqueta, className="ce-panel-label"),
            html.Div(valor, className="ce-panel-valor",
                     style={"color": color} if color else None),
        ], className="mb-2")

    return [
        html.Img(src="/" + foto, style={
            "width": "100%", "borderRadius": 10, "height": 150,
            "objectFit": "cover", "boxShadow": "0 6px 18px rgba(0,0,0,.35)"}),
        dbc.Row([
            dbc.Col(html.Code(r["id_reporte"], className="h6"), width="auto",
                    className="align-self-center"),
            dbc.Col(dbc.Badge(r["estado_gestion"], className="float-end",
                              style={"background": COLOR_ESTADO.get(r["estado_gestion"], "#555"),
                                     "font-size": ".68rem"}),
                    width="auto", className="ms-auto align-self-center"),
        ], className="align-items-center mt-3 mb-2 g-1"),
        campo("Comuna / barrio", f"{r['comuna']} · {r['barrio']}" if r["barrio"] else r["comuna"]),
        campo("Tipo de daño", r["tipo_dano"], COLOR_TIPO.get(tipo)),
        campo("Dependencia", r["dependencia"] or "—"),
        campo("Canal", r["canal_reporte"]),
        campo("Reportado", r["fecha_reporte"].strftime("%Y-%m-%d %H:%M")),
        campo("Resuelto", resuelta_txt),
        campo("Prioridad", f"{r['prioridad']} · {int(r['puntaje_prioridad'])} pts"
              + ("  (repetido)" if r["reporte_repetido"] else ""),
              COLOR_PRIORIDAD.get(r["prioridad"])),
        campo("Riesgo declarado", r["riesgo"] or "—"),
        campo("Ubicación", f"{r['latitud']:.5f}, {r['longitud']:.5f}"),
        html.Div([
            html.Div("Estado de gestión", className="ce-panel-label"),
            dcc.Dropdown(id="dd_estado_panel", clearable=False,
                         options=["Reportado", "En revisión", "Programado", "Resuelto"],
                         value=r["estado_gestion"]),
        ], className="mb-2"),
        html.Div([
            html.Div("Descripción", className="ce-panel-label"),
            html.P(r["descripcion"] or "— dato simulado sin descripción —",
                   className="small mb-0", style={"fontStyle": "italic"}),
        ]),
        html.Div(f"origen: {r['origen_datos']}", className="text-muted mt-2",
                 style={"font-size": ".66rem"}),
    ]


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
    Output("f_prioridad", "options"), Output("f_dependencia", "options"),
    # Sin `value` inicial el filtro queda en blanco y parece que no hay datos
    Output("f_comuna", "value"), Output("f_tipo", "value"),
    Output("f_canal", "value"), Output("f_estado", "value"),
    Output("f_prioridad", "value"), Output("f_dependencia", "value"),
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
            option_list(df, "prioridad", "Todas"), option_list(df, "dependencia", "Todas"),
            "Todas", "Todos", "Todos", "Todos", "Todas", "Todas",
            df["fecha_reporte"].min().date(), df["fecha_reporte"].max().date(),
            option_list(df, "tipo_dano", "—"), option_list(df, "comuna", "—"),
            option_list(df, "canal_reporte", "—"), False)


# 2. Panel principal: resumen + figuras + tabla
@callback(
    Output("resumen_filtros", "children"), Output("mapa", "figure"),
    Output("g_tipo", "figure"), Output("g_canal", "figure"),
    Output("g_evol", "figure"), Output("g_semana", "figure"),
    Output("g_comuna", "figure"), Output("g_resolucion", "figure"),
    Output("g_plan", "figure"), Output("g_prioridad", "figure"),
    Output("g_ranking", "figure"), Output("g_dependencia", "figure"),
    Output("leyenda_mapa", "children"), Output("mapa_nota", "children"),
    Output("color_mapa", "disabled"),
    Input("f_comuna", "value"), Input("f_tipo", "value"),
    Input("f_canal", "value"), Input("f_estado", "value"),
    Input("f_prioridad", "value"), Input("f_dependencia", "value"),
    Input("f_fechas", "start_date"), Input("f_fechas", "end_date"),
    Input("btn_reset", "n_clicks"), Input("store_actualizado", "modified_timestamp"),
    Input("store_tema", "data"), Input("color_mapa", "value"),
    Input("vista_mapa", "value"),
)
def actualizar_dashboard(comuna, tipo, canal, estado, prioridad, dependencia,
                         fi, ff, _reset, _ts, tema, color_mapa, vista):
    df = cargar_df()
    # Filtro cruzado "estilo Power BI": las tarjetas, el mapa, la evolución y la
    # tabla usan TODOS los filtros; cada gráfico de categorías se calcula sin su
    # propia dimensión para seguir mostrando las demás categorías (atenuadas) y
    # poder cambiar de selección con un clic.
    base = filtrar(df, comuna, tipo, canal, estado, fi, ff, prioridad, dependencia)
    sin_tipo = filtrar(df, comuna, "Todos", canal, estado, fi, ff, prioridad, dependencia)
    sin_canal = filtrar(df, comuna, tipo, "Todos", estado, fi, ff, prioridad, dependencia)
    sin_comuna = filtrar(df, "Todas", tipo, canal, estado, fi, ff, prioridad, dependencia)
    sin_prioridad = filtrar(df, comuna, tipo, canal, estado, fi, ff, "Todas", dependencia)
    color_mapa = color_mapa or "tipo_dano"
    vista = vista or "puntos"
    if vista == "calor":
        leyenda = [html.Span([html.Span("●", style={"color": c, "marginRight": 4,
                                                    "fontSize": ".85rem"}), txt],
                             className="ce-leyenda-item")
                   for c, txt in (("#3498DB", "baja"), ("#F1C40F", "media"),
                                  ("#E67E22", "alta"), ("#E74C3C", "muy alta"))]
        leyenda = [html.Span("Densidad de reportes:", className="me-2")] + leyenda
        nota = "Mapa de calor · cambia a Puntos para abrir el detalle"
    else:
        leyenda = leyenda_mapa_html(base, color_mapa)
        nota = "Haz clic en un punto 👆 para ver el detalle"
    return (resumen_html(base), figura_mapa(base, tema, color_mapa, vista),
            barras_tipo(sin_tipo, tipo), embudo_canal(sin_canal, canal),
            fig_evolucion(base), fig_semanal(base),
            fig_comunas(sin_comuna, comuna), fig_resolucion(sin_tipo, tipo),
            fig_plan_desarrollo(base), fig_prioridades(sin_prioridad, prioridad),
            fig_ranking_comunas(base), fig_dependencias(base),
            leyenda, nota, vista == "calor")


# ------------------------------------------------------------------
# 2c. Filtros cruzados: clic en una barra/etapa de un gráfico
# ------------------------------------------------------------------
def _categoria_click(click_data):
    """Categoría del punto clicado; el embudo usa etiqueta corta en `y`, por eso
    se prefiere customdata[0] cuando existe."""
    if not click_data or not click_data.get("points"):
        return None
    punto = click_data["points"][0]
    cdata = punto.get("customdata")
    if isinstance(cdata, list) and cdata:
        return cdata[0]
    return punto.get("y")


def _alternar(valor, actual, vacio="Todos"):
    """Clic en la categoría ya filtrada = quitar el filtro."""
    if valor is None:
        return no_update
    return vacio if valor == actual else valor


@callback(
    Output("f_tipo", "value", allow_duplicate=True),
    Input("g_tipo", "clickData"),
    State("f_tipo", "value"),
    prevent_initial_call=True,
)
def cruce_tipo(click, actual):
    return _alternar(_categoria_click(click), actual)


@callback(
    Output("f_tipo", "value", allow_duplicate=True),
    Input("g_resolucion", "clickData"),
    State("f_tipo", "value"),
    prevent_initial_call=True,
)
def cruce_resolucion(click, actual):
    return _alternar(_categoria_click(click), actual)


@callback(
    Output("f_prioridad", "value", allow_duplicate=True),
    Input("g_prioridad", "clickData"),
    State("f_prioridad", "value"),
    prevent_initial_call=True,
)
def cruce_prioridad(click, actual):
    return _alternar(_categoria_click(click), actual, vacio="Todas")


@callback(
    Output("f_canal", "value", allow_duplicate=True),
    Input("g_canal", "clickData"),
    State("f_canal", "value"),
    prevent_initial_call=True,
)
def cruce_canal(click, actual):
    return _alternar(_categoria_click(click), actual)


@callback(
    Output("f_comuna", "value", allow_duplicate=True),
    Input("g_comuna", "clickData"),
    State("f_comuna", "value"),
    prevent_initial_call=True,
)
def cruce_comuna(click, actual):
    return _alternar(_categoria_click(click), actual, vacio="Todas")


@callback(
    Output("f_fechas", "start_date", allow_duplicate=True),
    Output("f_fechas", "end_date", allow_duplicate=True),
    Input("g_semana", "clickData"),
    State("f_fechas", "start_date"),
    prevent_initial_call=True,
)
def cruce_semana(click, inicio_actual):
    """Clic en una semana del gráfico de barras = filtrar ese rango de fechas."""
    if not click or not click.get("points"):
        return no_update, no_update
    x = click["points"][0].get("x")
    if not x:
        return no_update, no_update
    semana = pd.Timestamp(x).normalize()
    # Clic en la semana ya filtrada: vuelve al rango completo
    if inicio_actual and pd.Timestamp(inicio_actual) == semana:
        df = cargar_df()
        return df["fecha_reporte"].min().date(), df["fecha_reporte"].max().date()
    return semana.date(), (semana + pd.Timedelta(days=6)).date()


# 2e. Exportar los reportes filtrados a CSV
@callback(
    Output("descarga_csv", "data"),
    Input("btn_descargar", "n_clicks"),
    Input("f_comuna", "value"), Input("f_tipo", "value"),
    Input("f_canal", "value"), Input("f_estado", "value"),
    Input("f_prioridad", "value"), Input("f_dependencia", "value"),
    Input("f_fechas", "start_date"), Input("f_fechas", "end_date"),
    prevent_initial_call=True,
)
def descargar_csv(n, comuna, tipo, canal, estado, prioridad, dependencia, fi, ff):
    if ctx.triggered_id != "btn_descargar":
        return no_update
    f = filtrar(cargar_df(), comuna, tipo, canal, estado, fi, ff, prioridad, dependencia)
    out = f.copy()
    for col in ("fecha_reporte", "fecha_resolucion"):
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    out = out.fillna("")
    return dcc.send_data_frame(out.to_csv, "reportes_ciudad_escucha.csv",
                               index=False, encoding="utf-8-sig")


# 2d. Tabla paginada: página actual + página visualizada
@callback(
    Output("store_pagina", "data"),
    Input("btn_pag_prev", "n_clicks"), Input("btn_pag_next", "n_clicks"),
    Input("tam_pagina", "value"),
    Input("f_comuna", "value"), Input("f_tipo", "value"),
    Input("f_canal", "value"), Input("f_estado", "value"),
    Input("f_prioridad", "value"), Input("f_dependencia", "value"),
    Input("f_fechas", "start_date"), Input("f_fechas", "end_date"),
    Input("store_actualizado", "modified_timestamp"),
    State("store_pagina", "data"),
    prevent_initial_call=True,
)
def mover_pagina(_prev, _sig, tam, comuna, tipo, canal, estado, prioridad, dependencia,
                 fi, ff, _ts, pagina):
    """Cualquier cambio de filtro vuelve a la primera página."""
    if ctx.triggered_id not in ("btn_pag_prev", "btn_pag_next"):
        return 1
    tam = int(tam or 10)
    total = len(filtrar(cargar_df(), comuna, tipo, canal, estado, fi, ff,
                        prioridad, dependencia))
    maxp = max(1, math.ceil(total / tam))
    actual = min(max(1, pagina or 1), maxp)
    if ctx.triggered_id == "btn_pag_prev":
        return max(1, actual - 1)
    return min(maxp, actual + 1)


@callback(
    Output("tabla_recientes", "children"),
    Output("info_pagina", "children"),
    Output("btn_pag_prev", "disabled"),
    Output("btn_pag_next", "disabled"),
    Input("f_comuna", "value"), Input("f_tipo", "value"),
    Input("f_canal", "value"), Input("f_estado", "value"),
    Input("f_prioridad", "value"), Input("f_dependencia", "value"),
    Input("f_fechas", "start_date"), Input("f_fechas", "end_date"),
    Input("store_pagina", "data"), Input("tam_pagina", "value"),
    Input("store_actualizado", "modified_timestamp"),
    Input("store_seleccion", "data"),
)
def paginar_tabla(comuna, tipo, canal, estado, prioridad, dependencia,
                  fi, ff, pagina, tam, _ts, seleccion):
    f = filtrar(cargar_df(), comuna, tipo, canal, estado, fi, ff, prioridad, dependencia)
    tam = int(tam or 10)
    tabla, texto, pag, paginas = tabla_recientes_html(f, pagina, tam, seleccion)
    return tabla, texto, pag <= 1, pag >= paginas


# 2b. Restablecer: vuelve los filtros al estado inicial
@callback(
    Output("f_comuna", "value", allow_duplicate=True),
    Output("f_tipo", "value", allow_duplicate=True),
    Output("f_canal", "value", allow_duplicate=True),
    Output("f_estado", "value", allow_duplicate=True),
    Output("f_prioridad", "value", allow_duplicate=True),
    Output("f_dependencia", "value", allow_duplicate=True),
    Output("f_fechas", "start_date", allow_duplicate=True),
    Output("f_fechas", "end_date", allow_duplicate=True),
    Input("btn_reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filtros(n):
    if not n:
        return (no_update,) * 8
    df = cargar_df()
    return ("Todas", "Todos", "Todos", "Todos", "Todas", "Todas",
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
    resuelta = (fila["fecha_resolucion"].iloc[0] if len(fila) else pd.NaT)
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


def _aplicar_estado(id_rep, nuevo_estado):
    """Persiste el estado del reporte. Devuelve (ok, toast_children).

    Si el estado pedido es el actual no se reescribe nada: el desplegable se
    monta con el valor vigente y dispara la callback al abrir el detalle.
    """
    df = cargar_df()
    m = df["id_reporte"] == id_rep
    if not m.any() or df.loc[m, "estado_gestion"].iloc[0] == nuevo_estado:
        return False, None
    df.loc[m, "estado_gestion"] = nuevo_estado
    # `fecha_resolucion` alimenta los gráficos de evolución: se marca al resolver y
    # se limpia si el reporte vuelve a un estado abierto.
    df.loc[m, "fecha_resolucion"] = pd.Timestamp.now() if nuevo_estado == "Resuelto" else pd.NaT
    guardar_csv(df)
    toast = html.Div([html.I(className="fa-solid fa-circle-check text-success me-2"),
                      f"Estado de {id_rep} actualizado a “{nuevo_estado}”"])
    return True, toast


# 3b. Selección de una fila de la tabla -> panel de detalle
@callback(
    Output("store_seleccion", "data"),
    Input({"type": "fila_reporte", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def seleccionar_fila(_clicks):
    trig = ctx.triggered_id
    if not isinstance(trig, dict):
        return no_update
    # Al repintar la tabla las filas se recrean con n_clicks=0: no es una selección
    if not (ctx.triggered and ctx.triggered[0]["value"]):
        return no_update
    return trig["index"]


@callback(
    Output("panel_detalle", "children"),
    Input("store_seleccion", "data"),
    Input("store_actualizado", "modified_timestamp"),
)
def mostrar_panel(id_rep, _ts):
    return panel_detalle_html(id_rep)


# 3c. Cambio de estado desde el panel lateral
@callback(
    Output("toast_nuevo", "is_open", allow_duplicate=True),
    Output("toast_nuevo", "children", allow_duplicate=True),
    Output("store_actualizado", "data", allow_duplicate=True),
    Input("dd_estado_panel", "value"),
    State("store_seleccion", "data"),
    prevent_initial_call=True,
)
def cambiar_estado_panel(nuevo_estado, id_rep):
    if not nuevo_estado or not id_rep:
        return no_update, no_update, no_update
    ok, toast = _aplicar_estado(id_rep, nuevo_estado)
    if not ok:
        return no_update, no_update, no_update
    return True, toast, f"panel-{time.time()}"


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
    ok, toast = _aplicar_estado(id_rep, nuevo_estado)
    if not ok:
        return no_update, no_update, no_update
    # `store_actualizado` fuerza el refresco de todas las figuras
    return True, toast, f"estado-{time.time()}"


# 5. Abrir/cerrar modal del formulario
@callback(
    Output("modal_form", "is_open", allow_duplicate=True),
    Input("btn_abrir_form", "n_clicks"),
    Input("btn_cancelar_form", "n_clicks"),
    Input("btn_enviar_form", "n_clicks"),
    State("store_punto", "data"),
    prevent_initial_call=True,
)
def toggle_modal_form(abrir, cancelar, enviar, punto):
    """Solo abre/cierra. El guardado lo hace la callback de notificación."""
    trig = ctx.triggered_id
    if trig == "btn_abrir_form":
        return True
    if trig == "btn_cancelar_form":
        return False
    # Si falta la ubicación el modal se queda abierto para no perder lo escrito
    if trig == "btn_enviar_form" and punto:
        return False
    return no_update


# 6. Guardar reporte en CSV
def guardar_reporte(tipo, comuna, lat, lon, canal, estado, desc, contenido,
                    barrio="", riesgo="Medio"):
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
    # Un reporte nuevo del mismo tipo y a menos de 150 m se marca como repetido
    vecinos = vecinos_cercanos(df, float(lat), float(lon), tipo)
    repetido = vecinos >= 2
    pts, prioridad = calcular_prioridad(tipo, riesgo or "Medio", repetido, vecinos, 0)
    nueva = pd.DataFrame([{
        "id_reporte": nuevo_id,
        "fecha_reporte": ahora,
        "latitud": round(float(lat), 6),
        "longitud": round(float(lon), 6),
        "comuna": comuna,
        "barrio": barrio or "",
        "tipo_dano": tipo,
        "canal_reporte": canal if canal else "App Ciudad Escucha",
        "estado_gestion": estado,
        "dependencia": DEPENDENCIA_POR_TIPO.get(tipo, "Gobierno/PQRSD"),
        "riesgo": riesgo or "Medio",
        "reporte_repetido": repetido,
        "fecha_resolucion": ahora if estado == "Resuelto" else pd.NaT,
        "dias_respuesta": 0 if estado == "Resuelto" else "",
        "puntaje_prioridad": pts,
        "prioridad": prioridad,
        "origen_datos": "SIMULADO_FORMULARIO_APP",
        "foto_url": foto_url,
        "descripcion": (desc or "").strip(),
    }])
    df = pd.concat([df, nueva], ignore_index=True)
    df = df.reindex(columns=ORDEN_COLUMNAS)
    guardar_csv(df)
    return nuevo_id


# 7. Ubicación del reporte: clic en el mapa, GPS del equipo o punto sugerido
def _comuna_cercana(df, lat, lon):
    """Comuna del reporte más próximo: sirve para preseleccionar la comuna."""
    d = ((df["latitud"] - lat) ** 2 +
         ((df["longitud"] - lon) * 0.998) ** 2)  # cos(4° lat) ≈ 0.998
    return df.loc[d.idxmin(), "comuna"]


@callback(
    Output("store_punto", "data"),
    Output("n_comuna", "value", allow_duplicate=True),
    Output("txt_geo", "children"),
    Input("store_click", "data"),
    Input("btn_sugerir_punto", "n_clicks"),
    Input("store_gps", "data"),
    State("n_comuna", "value"),
    prevent_initial_call=True,
)
def fijar_punto(clic_mapa, _sugerir, gps, comuna):
    trig = ctx.triggered_id
    df = cargar_df()

    if trig == "btn_sugerir_punto":
        comuna_sel = comuna or random.choice(sorted(df["comuna"].unique()))
        sub = df[df["comuna"] == comuna_sel]
        fuente = sub if len(sub) >= 5 else df
        idx = random.randrange(len(fuente))
        lat = round(float(fuente["latitud"].iloc[idx]) + random.uniform(-.0018, .0018), 6)
        lon = round(float(fuente["longitud"].iloc[idx]) + random.uniform(-.0018, .0018), 6)
        return ({"lat": lat, "lon": lon, "fuente": "sugerido"}, comuna_sel,
                f"Punto al azar dentro de {comuna_sel}.")

    if trig == "store_click":
        if not clic_mapa or clic_mapa.get("lat") is None:
            return no_update, no_update, no_update
        lat, lon = clic_mapa["lat"], clic_mapa["lon"]
        if not (3.5 < lat < 4.6 and -74.2 < lon < -73.0):
            return no_update, no_update, "⚠️ Ese punto está fuera de Villavicencio."
        return ({"lat": round(lat, 6), "lon": round(lon, 6), "fuente": "mapa"},
                _comuna_cercana(df, lat, lon), "Coordenada fijada en el mapa.")

    if trig == "store_gps":
        if not gps:
            return no_update, no_update, no_update
        if gps.get("error"):
            return (no_update, no_update,
                    f"⚠️ No se obtuvo la ubicación: {gps['error']}. "
                    "Revisa el permiso de ubicación del navegador o marca el punto en el mapa.")
        lat, lon = gps.get("lat"), gps.get("lon")
        if lat is None or lon is None:
            return no_update, no_update, no_update
        return ({"lat": round(lat, 6), "lon": round(lon, 6), "fuente": "gps"},
                _comuna_cercana(df, lat, lon), "Ubicación del dispositivo.")

    return no_update, no_update, no_update


# 8. Pintar el punto elegido en el mini-mapa
@callback(
    Output("mini_mapa", "figure"),
    Output("txt_coords", "children"),
    Input("store_punto", "data"),
    Input("store_tema", "data"),
    Input("n_comuna", "value"),
)
def pintar_punto(punto, tema, comuna):
    estilo = "carto-positron" if tema == "light" else "carto-darkmatter"
    if not punto:
        # Sin punto: se encuadra la comuna elegida para poder clicar en detalle
        centro, zoom = VILLAVICENCIO, 11.8
        df = cargar_df()
        if comuna and (df["comuna"] == comuna).any():
            sub = df[df["comuna"] == comuna]
            centro = {"lat": float(sub["latitud"].mean()), "lon": float(sub["longitud"].mean())}
            zoom = 13.2
        # Sin trazas Plotly no dibuja el mapa (quedarían unos ejes vacíos), así
        # que se añade un marcador invisible solo para forzar el basemap.
        fig = go.Figure(go.Scattermap(
            lat=[VILLAVICENCIO["lat"]], lon=[VILLAVICENCIO["lon"]], mode="markers",
            marker={"size": 1, "opacity": 0}, hoverinfo="skip", showlegend=False))
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=230,
                          paper_bgcolor=TRANS,
                          map={"style": estilo, "center": centro, "zoom": zoom})
        return fig, "sin punto seleccionado"

    lat, lon = punto["lat"], punto["lon"]
    color = {"gps": "#27ae60", "sugerido": "#E67E22"}.get(punto.get("fuente"), "#E74C3C")
    fig = go.Figure(go.Scattermap(lat=[lat], lon=[lon], mode="markers",
                                  marker={"size": 15, "color": color, "opacity": .95},
                                  hovertemplate=f"{lat:.6f}, {lon:.6f}<extra></extra>"))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=230,
                      paper_bgcolor=TRANS, showlegend=False,
                      map={"style": estilo, "center": {"lat": lat, "lon": lon},
                           "zoom": 13.4})
    return fig, f"{lat:.6f}, {lon:.6f}  ·  {punto.get('fuente', 'manual')}"


# 8b. Barrios de la comuna elegida
@callback(
    Output("n_barrio", "options"),
    Output("n_barrio", "value"),
    Input("n_comuna", "value"),
)
def barrios_comuna(comuna):
    df = cargar_df()
    if comuna and comuna != "—":
        opciones = sorted(df.loc[df["comuna"] == comuna, "barrio"].unique())
    else:
        opciones = sorted(df["barrio"].unique())
    if not opciones:
        return [], None
    return [{"label": b, "value": b} for b in opciones], opciones[0]


# 8c. Prioridad y dependencia calculadas mientras se llena el formulario
@callback(
    Output("n_prioridad", "children"),
    Output("n_dependencia", "children"),
    Input("n_tipo", "value"), Input("n_riesgo", "value"), Input("store_punto", "data"),
)
def prioridad_formulario(tipo, riesgo, punto):
    if not tipo:
        return "", "—"
    dependencia = DEPENDENCIA_POR_TIPO.get(tipo, "Gobierno/PQRSD")
    nivel = riesgo or "Medio"
    vecinos = 1
    if punto:
        vecinos = vecinos_cercanos(cargar_df(), punto["lat"], punto["lon"], tipo)
    repetido = vecinos >= 2
    detalle = detalle_puntaje(tipo, nivel, repetido, vecinos, 0)
    prioridad = ("Alta" if detalle["total"] >= 65
                 else "Media" if detalle["total"] >= 40 else "Baja")
    insignia = dbc.Badge(f"{prioridad} · {detalle['total']} pts", style={
        "background": COLOR_PRIORIDAD[prioridad], "fontSize": ".76rem"})
    desglose = html.Span(
        f"riesgo {detalle['riesgo']} + reincidencia {detalle['reincidencia']}"
        + (" · repetido" if repetido else ""),
        className="text-muted ms-2", style={"fontSize": ".66rem"})
    return [insignia, desglose], dependencia


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


# 10. Reset del formulario al abrirlo de nuevo (limpia campos y el punto)
@callback(
    Output("n_tipo", "value"), Output("n_desc", "value"),
    Output("upload_foto", "contents"), Output("preview_foto", "src"),
    Output("preview_foto", "style"), Output("preview_texto", "children"),
    Output("store_punto", "data", allow_duplicate=True),
    Output("txt_geo", "children", allow_duplicate=True),
    Output("n_riesgo", "value", allow_duplicate=True),
    Input("btn_abrir_form", "n_clicks"),
    State("n_tipo", "options"),
    prevent_initial_call=True,
)
def reset_formulario(n, opts_tipo):
    vacio = (no_update,) * 9
    if n:
        tipo_def = (opts_tipo[1]["value"] if opts_tipo and len(opts_tipo) > 1 else None)
        return (tipo_def, "", None, "", {"display": "none"}, "", None, "", "Medio")
    return vacio


# 11. Notificación Toast (cierra sola)
@callback(
    Output("toast_nuevo", "is_open", allow_duplicate=True),
    Output("toast_nuevo", "children", allow_duplicate=True),
    Output("store_actualizado", "data"),
    Input("btn_enviar_form", "n_clicks"),
    State("n_tipo", "value"), State("n_comuna", "value"),
    State("store_punto", "data"),
    State("n_canal", "value"), State("n_estado", "value"),
    State("n_desc", "value"), State("upload_foto", "contents"),
    State("n_barrio", "value"), State("n_riesgo", "value"),
    prevent_initial_call=True,
)
def notificar_guardado(n, tipo, comuna, punto, canal, estado, desc, contenido,
                       barrio, riesgo):
    if not n or tipo is None or not punto:
        return (True, html.Div([html.I(className="fa-solid fa-triangle-exclamation "
                                       "text-warning me-2"),
                                "Marca la ubicación en el mapa antes de enviar."]), no_update)
    nuevo = guardar_reporte(tipo, comuna, punto["lat"], punto["lon"],
                            canal, estado, desc, contenido, barrio, riesgo)
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
