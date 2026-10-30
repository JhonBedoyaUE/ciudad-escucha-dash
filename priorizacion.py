"""Reglas de priorización de Ciudad Escucha (única fuente de verdad).

Las usan el generador del dataset (`scripts/generar_dataset.py`), el dashboard
(`app.py`) y el formulario de nuevos reportes, para que un reporte creado en la
app reciba exactamente el mismo puntaje que uno simulado.

    Riesgo       0–50   tipo de daño + nivel de riesgo declarado
    Reincidencia 0–30   reporte repetido (+20) y densidad cercana (+10)
    Antigüedad   0–20   días sin resolver

    Total 0–100 · Alta >= 65 · Media >= 40 · Baja < 40

Ajustes derivados de las entrevistas documentados en
`data/generated/reglas_priorizacion.md`.
"""
import math

# --- Riesgo ----------------------------------------------------------------
RIESGO_BASE = {
    "Vías": 40,
    "Alumbrado público": 45,   # la entrevista asocia fallas de luminarias con robos
    "Alcantarillado": 30,
    "Basuras": 20,
    "Otro": 10,
}
AJUSTE_RIESGO = {"Bajo": 0, "Medio": 5, "Alto": 10}
NIVELES_RIESGO = ["Bajo", "Medio", "Alto"]

# --- Dependencia responsable por tipo de daño ------------------------------
DEPENDENCIA_POR_TIPO = {
    "Vías": "Infraestructura",
    "Alumbrado público": "Alborada",
    "Basuras": "EMAB",
    "Alcantarillado": "EDESA",
    "Otro": "Gobierno/PQRSD",
}
DEPENDENCIAS = ["Infraestructura", "Alborada", "EMAB", "EDESA", "Gobierno/PQRSD"]

# --- Umbrales --------------------------------------------------------------
UMBRAL_ALTA = 65
UMBRAL_MEDIA = 40

PRIORIDADES = ["Alta", "Media", "Baja"]


def puntaje_riesgo(tipo, nivel_riesgo="Medio"):
    return min(50, RIESGO_BASE.get(tipo, 10) + AJUSTE_RIESGO.get(nivel_riesgo, 0))


def puntaje_reincidencia(repetido, vecinos=1):
    """+20 si el reporte es repetido; +10 si hay 3+ del mismo tipo en 150 m."""
    pts = 20 if repetido else 0
    if vecinos >= 3:
        pts += 10
    return min(30, pts)


def puntaje_antiguedad(dias):
    if dias > 60:
        return 20
    if dias > 30:
        return 17
    if dias > 15:
        return 12
    if dias > 7:
        return 8
    if dias > 2:
        return 4
    return 0


def calcular_prioridad(tipo, nivel_riesgo="Medio", repetido=False, vecinos=1, dias=0):
    """Devuelve (puntaje 0–100, prioridad Alta/Media/Baja)."""
    pts = int(min(100, puntaje_riesgo(tipo, nivel_riesgo)
                  + puntaje_reincidencia(repetido, vecinos)
                  + puntaje_antiguedad(dias)))
    if pts >= UMBRAL_ALTA:
        return pts, "Alta"
    if pts >= UMBRAL_MEDIA:
        return pts, "Media"
    return pts, "Baja"


def detalle_puntaje(tipo, nivel_riesgo="Medio", repetido=False, vecinos=1, dias=0):
    """Desglose de los puntos, para mostrarlo en el formulario."""
    return {
        "riesgo": puntaje_riesgo(tipo, nivel_riesgo),
        "reincidencia": puntaje_reincidencia(repetido, vecinos),
        "antiguedad": puntaje_antiguedad(dias),
        "total": calcular_prioridad(tipo, nivel_riesgo, repetido, vecinos, dias)[0],
    }


def distancia_m(lat1, lon1, lat2, lon2):
    """Distancia aproximada en metros (haversine simplificada)."""
    dy = (lat1 - lat2) * 111_320
    dx = (lon1 - lon2) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def vecinos_cercanos(df, lat, lon, tipo, radio=150):
    """Nº de reportes del mismo tipo a menos de `radio` metros del punto."""
    if df is None or len(df) == 0:
        return 1
    dy = (df["latitud"] - lat) * 111_320
    dx = (df["longitud"] - lon) * 111_320 * math.cos(math.radians(lat))
    cerca = (df["tipo_dano"] == tipo) & ((dx ** 2 + dy ** 2) ** 0.5 <= radio)
    return int(cerca.sum()) + 1


def indice_prioridad_comunal(grupo, hoy):
    """Índice 0–100 por comuna: 60 % altas + 25 % pendientes + 15 % antigüedad."""
    import pandas as pd

    total = len(grupo)
    if not total:
        return 0.0, 0.0, 0.0, 0.0
    altas = float((grupo["prioridad"] == "Alta").mean() * 100)
    pendientes = grupo[grupo["fecha_resolucion"].isna()]
    pct_pend = len(pendientes) / total * 100
    dias = (((pd.Timestamp(hoy) - pendientes["fecha_reporte"]).dt.days).clip(lower=0).mean()
            if len(pendientes) else 0.0)
    return altas, pct_pend, float(dias), total
