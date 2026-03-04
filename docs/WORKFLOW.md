# SciTools Radar - Documentacion del Pipeline de Agentes

Documentacion tecnica detallada del proceso automatizado de busqueda, actualizacion y generacion de contenido.

---

## Indice

1. [Vision General](#1-vision-general)
2. [Busqueda de Nuevas Herramientas](#2-busqueda-de-nuevas-herramientas)
3. [Deteccion de Actualizaciones](#3-deteccion-de-actualizaciones)
4. [Generacion de Entradas del Blog](#4-generacion-de-entradas-del-blog)
5. [Evaluacion de Calidad](#5-evaluacion-de-calidad)
6. [Automatizacion Periodica](#6-automatizacion-periodica)
7. [Modelos y Costos](#7-modelos-y-costos)
8. [Flujo de Datos](#8-flujo-de-datos)
9. [Manejo de Errores](#9-manejo-de-errores)
10. [Configuracion](#10-configuracion)

---

## 1. Vision General

El sistema opera mediante un **pipeline de 5 etapas secuenciales**, cada una ejecutada por un agente especializado con un modelo de IA optimizado para su tarea:

```
┌──────────────────────────────────────────────────────────────────┐
│                    PIPELINE SCITOOLS RADAR                       │
│                                                                  │
│  [Inventario]  →  [Investigador]  →  [Clasificador]             │
│     Check DB       Sonnet 4 +         Sonnet 4                  │
│                    Tavily API                                    │
│                       │                    │                     │
│                       ▼                    ▼                     │
│               [Redactor]  →  [Creador BD]  →  [Evaluador]       │
│               Opus 4           SQLAlchemy     Sonnet 4           │
│               JSON mode                                          │
└──────────────────────────────────────────────────────────────────┘
```

**Frecuencia:** Martes y Jueves a las 07:00 UTC
**Resultado por ejecucion:** 1 entrada de blog con hasta 6 herramientas nuevas y 5 actualizaciones

---

## 2. Busqueda de Nuevas Herramientas

### Archivo: `app/agent/researcher.py`
### Modelo: `claude-sonnet-4-20250514` + Tavily Search API

### Proceso

1. **Consulta del inventario actual**: Se obtienen todas las herramientas existentes en la BD para evitar duplicados.

2. **Generacion de queries de busqueda**: Claude Sonnet 4 genera queries de busqueda optimizadas basadas en:
   - Tendencias actuales en herramientas de investigacion
   - Gaps en el inventario actual (campos sin cobertura)
   - Categorias con pocas herramientas

3. **Busqueda web via Tavily API**: Cada query se ejecuta contra Tavily API para obtener resultados web actualizados:
   - Maximo 10 resultados por query
   - Filtro de dominio para fuentes confiables (.edu, .org, repositorios oficiales)
   - Busqueda en modo "search" con extractos

4. **Analisis y extraccion**: Claude Sonnet 4 analiza los resultados y extrae:
   - Nombre de la herramienta
   - URL oficial
   - Resumen (1-2 oraciones)
   - Campo cientifico probable
   - Categoria probable

5. **Deduplicacion**: Se comparan con el inventario existente por nombre (fuzzy matching) y URL para evitar duplicados.

### Limites configurables
- `AGENT_MAX_NEW_TOOLS`: Maximo 6 herramientas nuevas por ejecucion (default)
- Busqueda multidisciplinar para asegurar diversidad de campos

### Output
```json
{
  "new_tools": [
    {
      "name": "Nombre de la herramienta",
      "url": "https://...",
      "summary": "Descripcion breve",
      "field_hint": "Campo cientifico sugerido",
      "category_hint": "Categoria sugerida"
    }
  ],
  "search_metadata": {
    "queries_used": 3,
    "results_analyzed": 28,
    "duplicates_filtered": 4
  }
}
```

---

## 3. Deteccion de Actualizaciones

### Archivo: `app/agent/researcher.py` (segunda fase)
### Modelo: `claude-sonnet-4-20250514` + Tavily Search API

### Proceso

1. **Seleccion de herramientas a verificar**: Se seleccionan herramientas del inventario priorizando:
   - Herramientas no actualizadas recientemente
   - Herramientas de alta prioridad (fuentes prioritarias)
   - Rotacion para cubrir todo el inventario gradualmente

2. **Busqueda de novedades**: Para cada herramienta seleccionada:
   - Busqueda en Tavily: `"{nombre_herramienta}" update OR new version OR release`
   - Analisis de la pagina oficial (si tiene URL)
   - Deteccion de cambios en funcionalidades, precios, plataformas

3. **Comparacion con registro actual**: Claude Sonnet 4 compara el estado actual en BD con la informacion encontrada, detectando:
   - Cambios en funcionalidad (`summary`)
   - Cambio de categoria
   - Nuevas integraciones
   - Cambios de precio/licencia
   - Cambios de URL

4. **Generacion de registros de actualizacion**: Para cada cambio detectado se crea un registro `Update` con:
   - `field_updated`: Campo que cambio
   - `old_value`: Valor anterior
   - `new_value`: Valor nuevo
   - `description`: Descripcion legible del cambio

### Limites configurables
- `AGENT_MAX_UPDATES`: Maximo 5 actualizaciones por ejecucion (default)

### Output
```json
{
  "updates": [
    {
      "tool_slug": "zotero",
      "field_updated": "summary",
      "old_value": "Gestor de referencias bibliograficas",
      "new_value": "Gestor de referencias con IA integrada para sugerencias",
      "description": "Zotero agrego funcionalidades de IA para sugerir referencias"
    }
  ]
}
```

---

## 4. Generacion de Entradas del Blog

### 4.1 Clasificacion

#### Archivo: `app/agent/classifier.py`
#### Modelo: `claude-sonnet-4-20250514`

Cada herramienta nueva pasa por el clasificador que asigna:

- **Campo cientifico** (field): Uno de los campos predefinidos (Multidisciplinar, Ciencias Sociales, Ciencias de la Salud, etc.)
- **Categoria** (category): Tipo de herramienta (IA/ML, Busqueda/Descubrimiento, Gestion de Referencias, etc.)

El clasificador usa Claude Sonnet 4 por su velocidad y precision, ideal para tareas de clasificacion categorica.

### 4.2 Redaccion Editorial

#### Archivo: `app/agent/writer.py`
#### Modelo: `claude-opus-4-20250514` (JSON mode)

El redactor genera el contenido editorial HTML de la entrada:

1. **Input**: Herramientas nuevas (ya clasificadas) + actualizaciones detectadas
2. **Prompt**: Instrucciones detalladas para generar un editorial profesional en espanol
3. **Formato**: JSON mode con estructura:

```json
{
  "editorial_html": "<h3>Titulo del Radar</h3><p>Texto editorial...</p>...",
  "tools_data": [
    {
      "name": "...",
      "slug": "...",
      "summary": "...",
      "url": "...",
      "field": "...",
      "category": "..."
    }
  ]
}
```

4. **Estilo editorial**: 
   - Tono profesional pero accesible
   - Estructura: introduccion, herramientas nuevas (con analisis), actualizaciones destacadas, conclusion
   - HTML semantico con headings, listas, enlaces
   - Enfoque en valor para el investigador

### 4.3 Persistencia en BD

#### Archivo: `app/agent/scheduler.py`
#### Tecnologia: SQLAlchemy

Tras la redaccion, el sistema:

1. Crea los objetos `Tool` para herramientas nuevas (o actualiza existentes)
2. Crea los objetos `Update` para cada actualizacion detectada
3. Crea el objeto `Entry` con:
   - `date`: Fecha del dia
   - `editorial`: HTML del editorial
   - `editorial_html`: HTML renderizado
   - `created_by`: `'agent'`
4. Asocia herramientas y actualizaciones con la entrada via relaciones many-to-many

---

## 5. Evaluacion de Calidad

### Archivo: `app/agent/evaluator.py`
### Modelo: `claude-sonnet-4-20250514`

Tras crear la entrada, el evaluador analiza la calidad del contenido generado:

### Metricas evaluadas (JSON mode)

| Metrica | Rango | Descripcion |
|---|---|---|
| `completeness` | 0.0 - 1.0 | Cobertura de la informacion (URLs, descripciones, campos) |
| `field_diversity` | 0.0 - 1.0 | Diversidad de campos cientificos representados |
| `social_coverage` | 0.0 - 1.0 | Inclusion de redes sociales academicas |
| `hallucination_risk` | 0.0 - 1.0 | Riesgo de informacion fabricada (menor = mejor) |
| `quality_score` | 0 - 10 | Puntuacion general de calidad |

### Criterios de calidad
- **Puntuacion >= 7**: Calidad aceptable, se publica automaticamente
- **Puntuacion 5-6**: Calidad media, publicada con flag de revision
- **Puntuacion < 5**: Calidad baja, se marca para revision manual

### Output del evaluador
```json
{
  "quality_score": 8.5,
  "completeness": 0.92,
  "field_diversity": 0.78,
  "social_coverage": 0.45,
  "hallucination_risk": 0.12,
  "feedback": "Editorial bien estructurado con buena cobertura..."
}
```

---

## 6. Automatizacion Periodica

### Archivo: `app/agent/scheduler.py`
### Tecnologia: APScheduler (BackgroundScheduler)

### Calendario de ejecucion

```
Lun   Mar   Mie   Jue   Vie   Sab   Dom
 -    07:00  -    07:00  -      -     -
      ▲           ▲
      │           │
  Ejecucion   Ejecucion
  automatica  automatica
```

### Configuracion en `config.py`

```python
AGENT_SCHEDULE_HOUR = 7               # Hora UTC
AGENT_SCHEDULE_DAYS = 'tue,thu'       # Dias de ejecucion
AGENT_MAX_NEW_TOOLS = 6               # Max herramientas nuevas por ejecucion
AGENT_MAX_UPDATES = 5                 # Max actualizaciones por ejecucion
```

### Flujo de una ejecucion automatica

```
07:00 UTC (mar/jue)
    │
    ▼
[1] Crear registro AgentRun (status='running')
    │
    ▼
[2] Verificar inventario actual (query BD)
    │
    ▼
[3] Investigador: buscar nuevas herramientas + actualizaciones
    │   └── Tavily API + Claude Sonnet 4
    │   └── Recibir: new_tools[] + updates[]
    │
    ▼
[4] Clasificador: categorizar herramientas nuevas
    │   └── Claude Sonnet 4
    │   └── Asignar: field + category a cada tool
    │
    ▼
[5] Redactor: generar editorial HTML
    │   └── Claude Opus 4 (JSON mode)
    │   └── Recibir: editorial_html + tools_data
    │
    ▼
[6] Creador: persistir en base de datos
    │   └── SQLAlchemy: crear Tool, Update, Entry
    │   └── Asociar relaciones many-to-many
    │
    ▼
[7] Evaluador: evaluar calidad
    │   └── Claude Sonnet 4 (JSON mode)
    │   └── Guardar metricas en AgentRun
    │
    ▼
[8] Actualizar AgentRun (status='success', metricas, costo)
    │
    ▼
[FIN] Entrada publicada automaticamente
```

### Trigger manual

Ademas de la automatizacion, se puede disparar manualmente:

- **Via API**: `POST /api/v1/agent/run` (requiere API key)
- **Via Admin**: Panel de control del agente en `/admin/agent`
- **Via CLI**: `python -m app.agent.scheduler`

---

## 7. Modelos y Costos

### Modelos configurados via CometAPI

| Etapa | Modelo | Temperatura | Tokens aprox. | Uso |
|---|---|---|---|---|
| Investigacion | `claude-sonnet-4-20250514` | 0.3 | ~4,000 | Busqueda + analisis |
| Clasificacion | `claude-sonnet-4-20250514` | 0.2 | ~800 | Categorizar herramientas |
| Redaccion | `claude-opus-4-20250514` | 0.4 | ~6,000 | Editorial HTML (JSON) |
| Evaluacion | `claude-sonnet-4-20250514` | 0.1 | ~1,000 | Metricas de calidad |
| Chat (SciBot) | `claude-sonnet-4-20250514` | 0.5 | ~1,500 | Consultas usuario |
| Fallback | `gemini-2.5-flash-preview-04-17` | 0.3 | variable | Modelo de respaldo |

### Reintentos y resiliencia

El servicio LLM (`llm_service.py`) utiliza `tenacity` para reintentos automaticos:
- Maximo 3 intentos
- Espera exponencial: 2s, 4s, 8s (max 10s)
- Si todos fallan, intenta con modelo fallback (Gemini 2.5 Flash)

---

## 8. Flujo de Datos

### Modelo de datos

```
Tool (herramienta)
├── id, slug, name, summary, description_html
├── url, logo_url, field, category
├── tags, pricing, platform, developer
├── priority_source, first_seen, last_updated, status
├── entries[]  (many-to-many via tool_entries)
└── updates[]  (one-to-many)

Entry (entrada del blog)
├── id, date, editorial, editorial_html
├── created_at, created_by
├── tools[]    (many-to-many via tool_entries)
└── updates[]  (one-to-many)

Update (actualizacion)
├── id, tool_id, entry_id
├── field_updated, old_value, new_value
├── description, created_at

AgentRun (ejecucion del agente)
├── id, started_at, finished_at, status
├── duration_seconds, tools_found, tools_new, updates_count
├── completeness, field_diversity, social_coverage
├── hallucination_risk, quality_score
├── total_tokens, total_cost_usd, models_used, error
```

---

## 9. Manejo de Errores

| Error | Comportamiento |
|---|---|
| Tavily API falla | Se omite la busqueda web, usa solo el inventario existente |
| Modelo LLM falla (3 reintentos) | Intenta con modelo fallback (Gemini 2.5 Flash) |
| Fallback tambien falla | AgentRun se marca con `status='error'`, se loguea el error |
| Error en persistencia BD | Rollback de la transaccion, AgentRun registra el error |
| Calidad < 5 | Entrada se publica pero se marca para revision manual |

---

## 10. Configuracion

### Variables de entorno requeridas

| Variable | Descripcion | Ejemplo |
|---|---|---|
| `COMETAPI_KEY` | API key de CometAPI | `sk-j2g...` |
| `TAVILY_API_KEY` | API key de Tavily Search | `tvly-...` |
| `SECRET_KEY` | Clave secreta Flask | Random string |
| `DATABASE_URL` | URL de PostgreSQL (produccion) | `postgresql://...` |
| `FLASK_ENV` | Entorno (development/production) | `development` |

### Parametros del agente en `config.py`

```python
AGENT_SCHEDULE_HOUR = 7           # Hora de ejecucion (UTC)
AGENT_SCHEDULE_DAYS = 'tue,thu'   # Dias (mon,tue,wed,thu,fri,sat,sun)
AGENT_MAX_NEW_TOOLS = 6           # Herramientas nuevas por ejecucion
AGENT_MAX_UPDATES = 5             # Actualizaciones por ejecucion
```

---

*Documentacion generada para SciTools Radar - Smart Centrum*
