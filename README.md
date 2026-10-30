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
| 📸 **Detalle con foto** | Clic en un punto del mapa → modal; clic en una fila de la tabla → el mismo detalle como **panel lateral** (imagen, comuna, tipo, canal, fechas, ubicación, descripción y cambio de estado) |
| 📝 **Formulario de reporte** | Modal con tipo, comuna, sugerencia de coordenadas 🎲, canal, estado, descripción y **subida de foto** (redimensionada con Pillow) |
| ✍️ **Cambio de estado** | Desde el modal de detalle: Reportado → En revisión → Programado → Resuelto (persiste en CSV y fija `resuelta_en`) |
| 🎚️ **Barra de filtros** | Comuna, tipo, canal, estado y rango de fechas en una barra horizontal con **flex-wrap** (se reparte el ancho y salta de línea en pantallas angostas) |
| 🖱️ **Filtros cruzados** | Clic en una barra/etapa (tipo, canal, comuna, tiempo de resolución) filtra todo el panel — chips, mapa, evolución y tabla; clic en una semana filtra ese rango de fechas. Un segundo clic en la misma categoría quita el filtro. El gráfico clicado conserva todas sus categorías (las demás atenuadas) para poder cambiar de selección |
| 🔢 **Resumen compacto** | Total de reportes, % resueltos, pendientes y comunas como *chips* (sin tarjetas KPI) |
| 📊 **Gráficas del panel** | Reportes por tipo de daño y Canal de reporte, apiladas a la derecha del mapa |
| 📈 **Evolución acumulada** | Reportes acumulados, resueltos acumulados y **pendientes (saldo)** calculados con la fecha `resuelta_en` de cada punto |
| 🧮 **Gestión** | Entradas y salidas por semana, reportes por comuna, tiempo medio por tipo de daño y **tiempo de respuesta por dependencia** |
| 🎯 **Indicador del Plan de Desarrollo** | Gauges de avance de las metas *300 km de vías* y *alumbrado LED al 90 %*, con el avance oficial + la evidencia ciudadana del periodo |
| 🚩 **Priorización** | Reglas Riesgo + Reincidencia + Antigüedad → `prioridad` Alta/Media/Baja y `puntaje_prioridad` (0–100) en cada reporte, aplicadas al dataset y al formulario |
| 🏆 **Ranking de comunas** | Índice de prioridad comunal (60 % altas + 25 % pendientes + 15 % antigüedad) con los tres primeros puestos resaltados |
| 📋 **Tabla paginada** | Todos los reportes filtrados, con paginación (10/25/50/100 por página), contador "Mostrando X–Y de Z", navegación anterior/siguiente y fila seleccionada resaltada |

## 🚀 Arranque local

```bash
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
# → http://localhost:8505
```

O con el servidor de producción (Waitress, el que usa el túnel):

```bash
./run.sh                     # PORT=8505 por defecto; PORT=xxxx ./run.sh para cambiarlo
```

`run.sh` abre **IPv4 e IPv6** a la vez porque Cloudflare Tunnel apunta a
`http://localhost:8505` y en Linux `localhost` resuelve primero a `::1`; con un
servidor escuchando solo en `0.0.0.0` el túnel devuelve **502**.

## 🐳 Docker (AWS / nube)

```bash
docker build -t ciudad-escucha-dash .
docker run -p 8050:8050 ciudad-escucha-dash
# → http://localhost:8050  (variable PORT configurable)
```

El `Dockerfile` usa **Waitress** (servidor WSGI de producción) y expone la
salud de la app en `/health`.

## 🧮 Reglas de priorización

Documentadas en [`priorizacion.py`](priorizacion.py) (fuente única que usan el
generador, el dashboard y el formulario) y en
`data/generated/reglas_priorizacion.md`:

| Criterio | Puntos | Cálculo |
|----------|-------:|---------|
| **Riesgo** | 0–50 | Base por tipo (Alumbrado 45 · Vías 40 · Alcantarillado 30 · Basuras 20 · Otro 10) + nivel declarado (Alto +10 · Medio +5) |
| **Reincidencia** | 0–30 | +20 si es repetido (mismo tipo a ≤120 m) · +10 si hay 3+ en 150 m |
| **Antigüedad** | 0–20 | Días sin resolver (>60 → 20 · 31–60 → 17 · 16–30 → 12 · 8–15 → 8 · 3–7 → 4) |

Alta ≥ 65 · Media 40–64 · Baja < 40.

**Ajustes por las entrevistas:** el alumbrado pesa más que las vías por la
inseguridad asociada; se agregaron los canales `WhatsApp` y `Presencial` para no
excluir digitalmente; el riesgo percibido entra al puntaje; cada tipo de daño se
enruta a su dependencia (Infraestructura, Alborada, EMAB, EDESA, Gobierno/PQRSD).

### Regenerar el dataset

```bash
./venv/bin/python scripts/generar_dataset.py --n 1000 --semilla 42
```

Es reproducible (semilla fija) y escribe `dataset_simulado.csv`,
`ranking_comunas.csv` y `reglas_priorizacion.md`.

## ☁️ Despliegue en AWS (producción)

El dashboard público se sirve desde el servidor **`aws-sia`** (Ubuntu 26.04):

| Pieza | Detalle |
|-------|---------|
| URL | https://c-escucha.jhonb.dev |
| Código | `/opt/ciudad-escucha` (clon de `master`) + `venv` |
| Servicio | `ciudad-escucha.service` — `run.sh` con Waitress en el puerto 8505 (IPv4 + IPv6) |
| Túnel | `ciudad-escucha-aws` (`4f9b06df-0411-4c65-97a6-8c2db5ddff88`), servicio `cloudflared-ciudad-escucha.service`, ingress `c-escucha.jhonb.dev → http://localhost:8505` |
| DNS | CNAME `c-escucha.jhonb.dev` apuntando a ese túnel |

Actualizar la versión publicada (desde el portátil, con `master` ya subido):

```bash
./deploy/actualizar-aws.sh        # git pull + restart + comprobación del dominio
```

Primera instalación en un servidor nuevo:

```bash
sudo apt install -y python3-venv
sudo git clone https://github.com/JhonBedoyaUE/ciudad-escucha-dash.git /opt/ciudad-escucha
sudo chown -R $USER:$USER /opt/ciudad-escucha
cd /opt/ciudad-escucha && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
# servicio systemd con Environment=PORT=8505 y ExecStart=/opt/ciudad-escucha/run.sh
# túnel: cloudflared tunnel create ciudad-escucha-aws
#        cloudflared tunnel route dns --overwrite-dns ciudad-escucha-aws c-escucha.jhonb.dev
```

Los datos viven en `/opt/ciudad-escucha/data/generated/dataset_simulado.csv`: los
reportes creados desde el formulario y los cambios de estado se guardan ahí.

Para volver a servir el dominio desde el portátil basta con reapuntar el DNS al
túnel local (`c-escucha`, `ee01174c-1d9a-4d6c-84c1-a0d2ecb8a55b`) y levantar
`./run.sh` en el puerto 8505.

## 📁 Estructura

```
├── app.py                       # aplicación Dash
├── requirements.txt
├── Dockerfile
├── run.sh                       # arranque con waitress
├── data/
│   ├── generated/dataset_simulado.csv   # 1000 registros sintéticos + nuevos del formulario
│   ├── generated/ranking_comunas.csv    # ranking de comunas por prioridad
│   ├── generated/reglas_priorizacion.md # reglas aplicadas y ajustes de entrevistas
│   └── processed/veredas_villavicencio_simpl.geojson
├── assets/
│   ├── img/*.png                # 4 fotos sintéticas por tipo de daño (20 en total, Z-image)
│   ├── uploads/                 # fotos subidas desde el formulario
│   └── style.css                # tema oscuro compacto
├── priorizacion.py              # reglas de priorización (generador + dashboard)
└── scripts/
    └── generar_dataset.py       # generador del dataset simulado
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
