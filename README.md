# Ciudad Escucha — Dashboard Dash/Plotly

Dashboard interactivo para el **proyecto Ciudad Escucha** (asignatura Habilidades
Gerenciales, autor: **Jhon Bedoya — Analista**). Sistema de reporte de daños en
espacio público del municipio de Villavicencio, Meta, Colombia.

> 🚨 **DATOS SIMULADOS · PROYECTO ACADÉMICO**
> Los 1,000+ registros del dataset son sintéticos y están etiquetados
> explícitamente como `SIMULADO_ACADEMICO` en la columna `origen_datos`.

## ✨ Características

| Componente | Detalle |
|------------|---------|
| 🗺️ **Mapa interactivo** | MapLibre (Plotly `Scattermap`) con fondo CARTO/OpenStreetMap, sin tokens de API |
| ⭕ **Puntos-círculo** | Color por tipo de daño (Vías · Alumbrado · Basuras · Alcantarillado · Otro) |
| 🛑 **Capa de veredas** | Contornos del shapefile DANE 2024 (58 veredas de Villavicencio filtradas con **QGIS MCP**) |
| 📸 **Detalle con foto** | Clic en un punto → modal con imagen, comuna, canal, fecha, estado y descripción |
| 📝 **Formulario de reporte** | Modal con tipo, comuna, sugerencia de coordenadas 🎲, canal, estado, descripción y **subida de foto** (redimensionada con Pillow) |
| ✍️ **Cambio de estado** | Desde el modal de detalle: Reportado → En revisión → Programado → Resuelto (persiste en CSV y fija `resuelta_en`) |
| 🎚️ **Barra de filtros** | Comuna, tipo, canal, estado y rango de fechas en una barra horizontal con **flex-wrap** (se reparte el ancho y salta de línea en pantallas angostas) |
| 🔢 **Resumen compacto** | Total de reportes, % resueltos, pendientes y comunas como *chips* (sin tarjetas KPI) |
| 📊 **Gráficas del panel** | Reportes por tipo de daño y Canal de reporte, apiladas a la derecha del mapa |
| 📈 **Evolución acumulada** | Reportes acumulados, resueltos acumulados y **pendientes (saldo)** calculados con la fecha `resuelta_en` de cada punto |
| 🧮 **Gestión** | Entradas y salidas por semana, reportes por comuna y tiempo medio de resolución por tipo |

## 🚀 Arranque local

```bash
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
# → http://localhost:8505
```

## 🐳 Docker (AWS / nube)

```bash
docker build -t ciudad-escucha-dash .
docker run -p 8050:8050 ciudad-escucha-dash
# → http://localhost:8050  (variable PORT configurable)
```

El `Dockerfile` usa **Waitress** (servidor WSGI de producción) y expone la
salud de la app en `/health`.

## 📁 Estructura

```
├── app.py                       # aplicación Dash
├── requirements.txt
├── Dockerfile
├── run.sh                       # arranque con waitress
├── data/
│   ├── generated/dataset_simulado.csv   # 1000 registros sintéticos + nuevos del formulario
│   └── processed/veredas_villavicencio_simpl.geojson
├── assets/
│   ├── img/*.png                # imágenes sintéticas de tipos de daño (Z-image generadas)
│   ├── uploads/                 # fotos subidas desde el formulario
│   └── style.css                # tema oscuro compacto
└── scripts/
```

## 🗺️ Origen de la capa de veredas

GeoJSON derivado de `shp_CRVeredas_2024.zip` (DANE, Resolución Simple) filtrado
en QGIS con expresión `NOMB_MPIO = 'VILLAVICENCIO'` vía **QGIS MCP**, luego
simplificado a 0.2 MB con `geopandas.simplify`.

## 🔒 Ética de datos

El proyecto académico simula un sistema real de participación ciudadana.
Todos los registros se generan de manera sintética; ninguna información
corresponde a reportes reales de ciudadanos. La capa geográfica (veredas) sí es
oficial (DANE) y solo se usa como referencia cartográfica.

---

Desplegable en **Dash Enterprise**, **Render**, **Railway**, **Fly.io**,
**AWS ECS/App Runner** o cualquier host Python con el Dockerfile.
