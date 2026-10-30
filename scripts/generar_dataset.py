#!/usr/bin/env python
"""Genera el dataset simulado de Ciudad Escucha con reglas de priorización.

Proyecto académico "Ciudad Escucha" — Habilidades Gerenciales.
Autor: Jhon Bedoya (Analista). Datos 100% simulados: SIMULADO_ACADEMICO.

Uso (desde la raíz del repo):
    ./venv/bin/python scripts/generar_dataset.py [--n 1000] [--semilla 42]

Salida:
    data/generated/dataset_simulado.csv     dataset completo
    data/generated/ranking_comunas.csv      ranking priorizado de comunas
    data/generated/reglas_priorizacion.md   reglas aplicadas y su origen

Las reglas viven en `priorizacion.py` (raíz del repo) y son las mismas que usa
el dashboard y el formulario de nuevos reportes.
"""
import argparse
import os
import random
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from priorizacion import (  # noqa: E402  (reglas compartidas con el dashboard)
    DEPENDENCIA_POR_TIPO, calcular_prioridad, distancia_m,
)

SALIDA_CSV = os.path.join(BASE, "data", "generated", "dataset_simulado.csv")
SALIDA_RANKING = os.path.join(BASE, "data", "generated", "ranking_comunas.csv")
SALIDA_REGLAS = os.path.join(BASE, "data", "generated", "reglas_priorizacion.md")

# ----------------------------------------------------------------------------
# Contexto espacial: bbox empíricos y pesos poblacionales por comuna
# ----------------------------------------------------------------------------
COMUNAS = {
    1: {"peso": 0.050, "lat": (4.1480, 4.1600), "lon": (-73.6450, -73.6300),
        "barrios": ["El Centro", "La Grama", "Villa Julia", "Barzal"]},
    2: {"peso": 0.040, "lat": (4.1380, 4.1500), "lon": (-73.6400, -73.6280),
        "barrios": ["La Esperanza", "San Benito", "Nueva Granada", "El Recreo"]},
    3: {"peso": 0.040, "lat": (4.1380, 4.1520), "lon": (-73.6280, -73.6100),
        "barrios": ["San Isidro", "El Estero", "Siete de Agosto", "La Campiña"]},
    4: {"peso": 0.154, "lat": (4.1150, 4.1400), "lon": (-73.6250, -73.6000),
        "barrios": ["Ciudad Porfía", "Alcalá", "San Antonio", "Villacentro"]},
    5: {"peso": 0.215, "lat": (4.1050, 4.1300), "lon": (-73.6550, -73.6250),
        "barrios": ["El Poblado", "Bosques de Abajo", "Las Camelias", "Villa Suárez"]},
    6: {"peso": 0.040, "lat": (4.1300, 4.1450), "lon": (-73.6600, -73.6400),
        "barrios": ["La Rosita", "Gaitán", "Comuneros", "El Manantial"]},
    7: {"peso": 0.141, "lat": (4.0950, 4.1250), "lon": (-73.6150, -73.5800),
        "barrios": ["La Reliquia", "Vista Hermosa", "Cantarrana", "Santa Helena"]},
    8: {"peso": 0.112, "lat": (4.0800, 4.1100), "lon": (-73.6650, -73.6350),
        "barrios": ["Guatapé", "Santa Inés", "Catumare", "El Diamante"]},
    9: {"peso": 0.105, "lat": (4.1500, 4.1750), "lon": (-73.6200, -73.5950),
        "barrios": ["Montecarlo", "Maizaro", "Rincón de las Américas", "El Buque"]},
    10: {"peso": 0.067, "lat": (4.1550, 4.1800), "lon": (-73.6700, -73.6400),
         "barrios": ["Cataluña", "Almondal", "El Porvenir", "La Madrid"]},
}

TIPOS = ["Vías", "Alumbrado público", "Basuras", "Alcantarillado", "Otro"]
PESOS_TIPO = [0.30, 0.25, 0.20, 0.15, 0.10]

# Canal presencial y WhatsApp agregados tras las entrevistas (exclusión digital)
CANALES = ["App Ciudad Escucha", "WhatsApp", "Portal Web", "Presencial", "PQRSD"]
PESOS_CANAL = [0.34, 0.28, 0.14, 0.16, 0.08]

ESTADOS = ["Reportado", "En revisión", "Programado", "Resuelto"]
PESOS_ESTADO = [0.32, 0.28, 0.24, 0.16]

# Probabilidad de declarar cada nivel de riesgo, por tipo de daño
PESOS_RIESGO = {
    "Vías": [0.15, 0.45, 0.40],
    "Alumbrado público": [0.15, 0.35, 0.50],
    "Alcantarillado": [0.40, 0.45, 0.15],
    "Basuras": [0.55, 0.35, 0.10],
    "Otro": [0.70, 0.25, 0.05],
}

# Días de respuesta simulados por tipo (media, desviación) para los resueltos
DIAS_RESPUESTA = {"Vías": (34, 14), "Alumbrado público": (18, 8),
                  "Basuras": (12, 6), "Alcantarillado": (26, 11), "Otro": (22, 10)}

FOTO = {"Vías": "assets/img/vias.png",
        "Alumbrado público": "assets/img/alumbrado.png",
        "Basuras": "assets/img/basuras.png",
        "Alcantarillado": "assets/img/alcantarillado.png",
        "Otro": "assets/img/otro.png"}

DESCRIPCION = {
    "Vías": "Hueco en la calzada que afecta el paso vehicular",
    "Alumbrado público": "Luminaria apagada o intermitente; el sector queda a oscuras",
    "Basuras": "Acumulación de residuos en el espacio público",
    "Alcantarillado": "Rebosamiento o hundimiento en la red de alcantarillado",
    "Otro": "Daño en el espacio público reportado por la comunidad",
}


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def vecinos_cercanos(puntos, i, radio=150):
    """Nº de reportes del mismo tipo en `radio` metros (incluye el actual)."""
    lat, lon, tipo = puntos[i]["latitud"], puntos[i]["longitud"], puntos[i]["tipo_dano"]
    return sum(1 for o in puntos
               if o["tipo_dano"] == tipo
               and distancia_m(lat, lon, o["latitud"], o["longitud"]) <= radio)


def marcar_repetidos(puntos, radio=120):
    """Un reporte es repetido si existe otro anterior del mismo tipo muy cerca."""
    previos = []
    for p in sorted(puntos, key=lambda x: x["fecha_reporte"]):
        p["reporte_repetido"] = any(
            q["tipo_dano"] == p["tipo_dano"]
            and distancia_m(p["latitud"], p["longitud"], q["latitud"], q["longitud"]) <= radio
            for q in previos)
        previos.append(p)


def tabla_markdown(df):
    """Tabla markdown sin depender de `tabulate`."""
    cols = list(df.columns)
    lineas = ["| " + " | ".join(cols) + " |",
              "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, fila in df.iterrows():
        lineas.append("| " + " | ".join(str(v) for v in fila.values) + " |")
    return "\n".join(lineas)


# ----------------------------------------------------------------------------
# Generación
# ----------------------------------------------------------------------------
def generar(num_reportes=1000, semilla=42, ahora=None):
    np.random.seed(semilla)
    random.seed(semilla)
    ahora = pd.Timestamp.now() if ahora is None else pd.Timestamp(ahora)

    # Reparto proporcional por peso poblacional (con corrección de redondeo)
    pesos = np.array([COMUNAS[c]["peso"] for c in COMUNAS])
    pesos = pesos / pesos.sum()
    reparto = [int(num_reportes * p) for p in pesos]
    for i in range(num_reportes - sum(reparto)):
        reparto[i % len(reparto)] += 1

    inicio = ahora - pd.Timedelta(days=120)   # ventana analítica de 4 meses
    puntos = []

    for idx, comuna in enumerate(sorted(COMUNAS)):
        info = COMUNAS[comuna]
        for _ in range(reparto[idx]):
            tipo = np.random.choice(TIPOS, p=PESOS_TIPO)
            puntos.append({
                "comuna": comuna,
                "barrio": random.choice(info["barrios"]),
                "tipo_dano": tipo,
                "canal_reporte": np.random.choice(CANALES, p=PESOS_CANAL),
                "estado_gestion": np.random.choice(ESTADOS, p=PESOS_ESTADO),
                "riesgo": np.random.choice(["Bajo", "Medio", "Alto"], p=PESOS_RIESGO[tipo]),
                "latitud": round(float(np.random.uniform(*info["lat"])), 6),
                "longitud": round(float(np.random.uniform(*info["lon"])), 6),
                "fecha_reporte": inicio + pd.Timedelta(
                    days=random.randint(0, 119), minutes=random.randint(0, 1439)),
            })

    # Reincidencia: ~12 % de los reportes se duplican a pocos metros
    for p in list(puntos):
        if random.random() < 0.12:
            gemelo = dict(p)
            gemelo["latitud"] = round(p["latitud"] + np.random.uniform(-6e-4, 6e-4), 6)
            gemelo["longitud"] = round(p["longitud"] + np.random.uniform(-6e-4, 6e-4), 6)
            gemelo["fecha_reporte"] = p["fecha_reporte"] + pd.Timedelta(
                days=random.randint(1, 20), minutes=random.randint(0, 1439))
            puntos.append(gemelo)

    puntos = puntos[:num_reportes]
    marcar_repetidos(puntos)

    filas = []
    for i, p in enumerate(puntos):
        # Resoluciones coherentes: solo resueltos y nunca en el futuro
        fecha_res = pd.NaT
        dias_resp = ""
        dias_abierto = max(0, (ahora - p["fecha_reporte"]).days)
        if p["estado_gestion"] == "Resuelto":
            media, sd = DIAS_RESPUESTA[p["tipo_dano"]]
            res = p["fecha_reporte"] + pd.Timedelta(days=int(max(1, np.random.normal(media, sd))))
            if res > ahora:
                res = ahora - pd.Timedelta(hours=random.randint(1, 20))
            fecha_res = res
            dias_resp = max(1, (res - p["fecha_reporte"]).days)
            dias_abierto = dias_resp

        pts, prioridad = calcular_prioridad(
            p["tipo_dano"], p["riesgo"], p["reporte_repetido"],
            vecinos_cercanos(puntos, i), dias_abierto)

        filas.append({
            "id_reporte": f"CE-2026-{1000 + i}",
            "fecha_reporte": p["fecha_reporte"].strftime("%Y-%m-%d %H:%M:%S"),
            "latitud": p["latitud"],
            "longitud": p["longitud"],
            "comuna": f"Comuna {p['comuna']}",
            "barrio": p["barrio"],
            "tipo_dano": p["tipo_dano"],
            "canal_reporte": p["canal_reporte"],
            "estado_gestion": p["estado_gestion"],
            "dependencia": DEPENDENCIA_POR_TIPO[p["tipo_dano"]],
            "riesgo": p["riesgo"],
            "reporte_repetido": bool(p["reporte_repetido"]),
            "fecha_resolucion": (fecha_res.strftime("%Y-%m-%d %H:%M:%S")
                                 if pd.notna(fecha_res) else ""),
            "dias_respuesta": dias_resp,
            "puntaje_prioridad": pts,
            "prioridad": prioridad,
            "origen_datos": "SIMULADO_ACADEMICO",
            "foto_url": FOTO[p["tipo_dano"]],
            "descripcion": f"{DESCRIPCION[p['tipo_dano']]} ({p['barrio']}, "
                           f"Comuna {p['comuna']})",
        })

    df = pd.DataFrame(filas)
    return df.sort_values("fecha_reporte", ascending=False).reset_index(drop=True)


def ranking_comunas(df):
    """Índice de prioridad comunal (0–100) y orden de atención.

    60 % reportes de prioridad Alta · 25 % pendientes ·
    15 % antigüedad media de los pendientes (normalizada al máximo).
    """
    ahora = pd.Timestamp.now()
    filas = []
    for comuna, g in df.groupby("comuna"):
        total = len(g)
        altas = int((g["prioridad"] == "Alta").sum())
        pendientes = g[g["fecha_resolucion"].fillna("").astype(str) == ""]
        dias = (((ahora - pd.to_datetime(pendientes["fecha_reporte"])).dt.days
                 .clip(lower=0).mean()) if len(pendientes) else 0.0)
        filas.append({
            "comuna": comuna,
            "reportes": total,
            "prioridad_alta": altas,
            "pct_alta": round(altas / total * 100, 1),
            "pendientes": len(pendientes),
            "pct_pendientes": round(len(pendientes) / total * 100, 1),
            "dias_abiertos_medios": round(float(dias), 1),
        })

    rk = pd.DataFrame(filas)
    max_dias = max(1.0, rk["dias_abiertos_medios"].max())
    rk["indice_prioridad"] = (
        0.60 * rk["pct_alta"]
        + 0.25 * rk["pct_pendientes"]
        + 0.15 * (rk["dias_abiertos_medios"] / max_dias * 100)
    ).round(1)
    rk = rk.sort_values("indice_prioridad", ascending=False).reset_index(drop=True)
    rk.insert(0, "puesto", range(1, len(rk) + 1))
    return rk


def escribir_reglas(df, rk):
    conteo = df["prioridad"].value_counts()
    md = f"""# Reglas de priorización — Ciudad Escucha (datos simulados)

Generado por `scripts/generar_dataset.py` el {pd.Timestamp.now():%Y-%m-%d %H:%M}.
Todos los registros son **SIMULADO_ACADEMICO**.

## Fórmula (0–100 puntos por reporte)

| Criterio | Puntos | Cómo se calcula |
|----------|-------:|-----------------|
| **Riesgo** | 0–50 | Base por tipo: Alumbrado 45 · Vías 40 · Alcantarillado 30 · Basuras 20 · Otro 10. Se suma el nivel declarado: Alto +10 · Medio +5 · Bajo +0 (tope 50). |
| **Reincidencia** | 0–30 | +20 si `reporte_repetido` (mismo tipo a ≤120 m de un reporte previo). +10 si hay 3 o más reportes del mismo tipo en 150 m. |
| **Antigüedad** | 0–20 | Días sin resolver: >60 → 20 · 31–60 → 17 · 16–30 → 12 · 8–15 → 8 · 3–7 → 4 · <3 → 0. |

**Clasificación:** Alta ≥ 65 · Media 40–64 · Baja < 40.

## Ajustes derivados de las entrevistas

1. **Alumbrado = mayor riesgo (45 pts).** La entrevista al ciudadano asocia las
   fallas de luminarias con robos e inseguridad, por eso pesa más que las vías.
2. **Canal presencial y WhatsApp.** La administración advirtió que el mayor
   riesgo es la exclusión digital de personas mayores: se agregaron `Presencial`
   y `WhatsApp` como canales válidos y el seguimiento puede ir por mensajería.
   El canal **no** modifica el puntaje (no debe castigar a quien reporta sin app).
3. **Nivel de riesgo declarado.** El formulario pregunta el riesgo percibido y
   ajusta el puntaje (Alto +10), recogiendo el criterio de inseguridad.
4. **Dependencia responsable.** Cada tipo de daño se enruta a su dependencia:
   Infraestructura (vías), Alborada (alumbrado), EMAB (basuras), EDESA
   (alcantarillado) y Gobierno/PQRSD (otros), que es lo que pedía la entrevista
   a la administración ("un responsable claro").

## Ranking de comunas

Índice 0–100 = 60 % reportes de prioridad Alta + 25 % pendientes + 15 % días
abiertos medios normalizados. Es el entregable de gestión del rol de Analista.

## Distribución obtenida

- Alta: {conteo.get('Alta', 0)} · Media: {conteo.get('Media', 0)} · Baja: {conteo.get('Baja', 0)}
- Repetidos: {int(df['reporte_repetido'].sum())} · Resueltos: {int((df['estado_gestion'] == 'Resuelto').sum())}
- Canales: {', '.join(f'{k} {v}' for k, v in df['canal_reporte'].value_counts().items())}

### Ranking

{tabla_markdown(rk)}
"""
    with open(SALIDA_REGLAS, "w", encoding="utf-8") as f:
        f.write(md)


def main():
    ap = argparse.ArgumentParser(description="Genera el dataset simulado de Ciudad Escucha")
    ap.add_argument("--n", type=int, default=1000, help="número de reportes")
    ap.add_argument("--semilla", type=int, default=42)
    args = ap.parse_args()

    df = generar(args.n, args.semilla)
    os.makedirs(os.path.dirname(SALIDA_CSV), exist_ok=True)
    df.to_csv(SALIDA_CSV, index=False, encoding="utf-8")

    rk = ranking_comunas(df)
    rk.to_csv(SALIDA_RANKING, index=False, encoding="utf-8")
    escribir_reglas(df, rk)

    print(f"✅ {len(df)} registros → {SALIDA_CSV}")
    print(f"✅ ranking de comunas → {SALIDA_RANKING}")
    print(f"✅ reglas documentadas → {SALIDA_REGLAS}")
    print("\nPrioridad:", df["prioridad"].value_counts().to_dict())
    print("Riesgo    :", df["riesgo"].value_counts().to_dict())
    print("Canales   :", df["canal_reporte"].value_counts().to_dict())
    print("Repetidos :", int(df["reporte_repetido"].sum()),
          "| Resueltos:", int((df["estado_gestion"] == "Resuelto").sum()))
    print("Dependencias:", df["dependencia"].value_counts().to_dict())
    print(rk[["puesto", "comuna", "indice_prioridad"]].to_string(index=False))


if __name__ == "__main__":
    main()
