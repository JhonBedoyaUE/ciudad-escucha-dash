# Reglas de priorización — Ciudad Escucha (datos simulados)

Generado por `scripts/generar_dataset.py` el 2026-10-30 10:15.
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

- Alta: 351 · Media: 451 · Baja: 198
- Repetidos: 94 · Resueltos: 141
- Canales: App Ciudad Escucha 354, WhatsApp 286, Presencial 150, Portal Web 128, PQRSD 82

### Ranking

| puesto | comuna | reportes | prioridad_alta | pct_alta | pendientes | pct_pendientes | dias_abiertos_medios | indice_prioridad |
|---|---|---|---|---|---|---|---|---|
| 1 | Comuna 3 | 42 | 21 | 50.0 | 39 | 92.9 | 53.3 | 65.6 |
| 2 | Comuna 5 | 224 | 82 | 36.6 | 203 | 90.6 | 60.2 | 58.6 |
| 3 | Comuna 8 | 116 | 45 | 38.8 | 99 | 85.3 | 58.8 | 58.3 |
| 4 | Comuna 10 | 69 | 22 | 31.9 | 61 | 88.4 | 64.4 | 56.2 |
| 5 | Comuna 4 | 160 | 57 | 35.6 | 128 | 80.0 | 61.1 | 55.6 |
| 6 | Comuna 6 | 41 | 13 | 31.7 | 37 | 90.2 | 59.8 | 55.5 |
| 7 | Comuna 9 | 108 | 35 | 32.4 | 94 | 87.0 | 58.6 | 54.8 |
| 8 | Comuna 1 | 52 | 17 | 32.7 | 43 | 82.7 | 61.6 | 54.6 |
| 9 | Comuna 2 | 42 | 14 | 33.3 | 34 | 81.0 | 61.1 | 54.5 |
| 10 | Comuna 7 | 146 | 45 | 30.8 | 121 | 82.9 | 59.4 | 53.0 |
