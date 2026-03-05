# SciTools Radar

**Plataforma de monitoreo automatizado de herramientas de investigacion cientifica** impulsada por un pipeline de agentes de IA con panel de administracion en tiempo real.

Desarrollado por [Smart Centrum](https://smartcentrum.edu.pe) — CENTRUM PUCP.

---

## Descripcion

SciTools Radar rastrea, clasifica y reporta herramientas digitales para la investigacion academica y cientifica. Combina un pipeline de 6 agentes de IA con curaduria humana para:

- **Descubrir** nuevas herramientas via busqueda automatizada (Tavily API) con pricing, plataforma y features
- **Clasificar** herramientas por campo cientifico y categoria (18 categorias descriptivas)
- **Actualizar** herramientas existentes: pricing, funcionalidades, novedades recientes
- **Redactar** entradas de blog editoriales extensas (800-1500 palabras) con analisis profesional
- **Evaluar** la calidad del contenido generado con metricas cuantitativas + auto-repair de imagenes
- **Publicar** con flujo editorial: borrador -> aprobacion -> publicacion
- **Monitorear** ejecuciones del agente en tiempo real desde el panel admin
- **Refrescar** calidad del inventario con pipeline independiente (Quality Reviewer + Research + Writer)

## Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Backend | Flask 3.1, SQLAlchemy, Flask-Migrate |
| Base de datos | PostgreSQL (produccion) / SQLite (desarrollo) |
| LLM Gateway | CometAPI (OpenAI SDK compatible, 500+ modelos) |
| Modelos IA | Claude Opus 4, Claude Sonnet 4, Gemini 2.5 Flash, DALL-E 3 |
| Busqueda web | Tavily API |
| Scheduler | APScheduler (configurable desde admin) |
| Chat | SciBot (asistente conversacional integrado) |
| Deploy | Railway con Gunicorn |
| Frontend | Jinja2 + Font Awesome 6.5 + Chart.js 4 |

## Estructura del Proyecto

```
scitools-flask/
├── app/
│   ├── __init__.py            # Factory Flask + extensiones
│   ├── models.py              # SQLAlchemy models (Tool, Entry, Update, AgentRun, User)
│   ├── routes/
│   │   ├── main.py            # Rutas publicas (blog, inventario, estadisticas)
│   │   ├── admin.py           # Panel admin completo (~460 lineas)
│   │   └── api.py             # API REST v1 + chat endpoint
│   ├── services/
│   │   ├── llm_service.py     # Cliente CometAPI unificado
│   │   ├── search_service.py  # Full-text search + filtros
│   │   └── stats_service.py   # Analytics y metricas
│   ├── agent/
│   │   ├── researcher.py      # Agente investigador (Claude Sonnet 4 + Tavily)
│   │   ├── classifier.py      # Agente clasificador (Claude Sonnet 4)
│   │   ├── updater.py         # Actualizador de herramientas existentes
│   │   ├── writer.py          # Agente redactor (Claude Opus 4, 800-1500 palabras)
│   │   ├── evaluator.py       # Evaluador de calidad + auto-repair imagenes
│   │   ├── refresh_pipeline.py # Pipeline de calidad (Quality Reviewer + Research + Writer)
│   │   └── scheduler.py       # Orquestador del pipeline + APScheduler
│   └── templates/
│       ├── base.html           # Layout maestro + SciBot chat widget
│       ├── index.html          # Blog principal con hero y tarjetas
│       ├── inventario.html     # Grid de herramientas con busqueda
│       ├── herramienta_detalle.html  # Detalle de herramienta
│       ├── entrada_detalle.html      # Detalle de entrada del blog
│       ├── estadisticas.html   # Dashboard con Chart.js
│       ├── about.html          # Acerca de / pipeline IA
│       └── admin/
│           ├── login.html      # Login con username (standalone)
│           ├── dashboard.html  # KPIs, monitor en vivo, acciones
│           ├── agent_control.html  # Triggers, schedule, log en vivo
│           ├── entries.html    # Flujo editorial (borrador/aprobar/rechazar)
│           ├── tools.html      # Gestion de herramientas
│           └── quality.html    # Metricas de calidad + costos
├── scripts/
│   ├── seed_data_windows.py   # Migrar datos del HTML original
│   ├── check_db.py            # Verificar contenido de la BD
│   └── test_routes.py         # Test automatizado de rutas
├── docs/
│   └── WORKFLOW.md            # Documentacion detallada del pipeline
├── migrations/                # Flask-Migrate (Alembic)
├── config.py                  # Configuracion dev/prod/test
├── wsgi.py                    # Entry point (Gunicorn / desarrollo)
├── requirements.txt
├── .env.example               # Template de variables de entorno
├── Procfile                   # Railway / Heroku
├── railway.toml               # Configuracion Railway
└── .gitignore
```

## Setup Local

```powershell
# 1. Clonar y crear virtual environment
git clone https://github.com/jzegarrag-centrum/scitools-radar.git
cd scitools-radar
python -m venv venv
.\venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
copy .env.example .env
# Editar .env con tus API keys

# 4. Inicializar y migrar base de datos
set FLASK_APP=wsgi.py
flask db upgrade

# 5. Cargar datos iniciales desde HTML original
python scripts\seed_data_windows.py

# 6. Ejecutar servidor
python wsgi.py
```

Abrir http://localhost:5000

## Panel de Administracion

Acceder a `/admin/login` con las credenciales configuradas.

**Credenciales por defecto:** `admin` / `admin1234`

### Funcionalidades del Admin

| Seccion | Descripcion |
|---|---|
| **Dashboard** | KPIs en vivo, monitor del agente, acciones rapidas, entradas recientes |
| **Agent Control** | 3 disparadores manuales (pipeline completo, buscar herramientas, generar borrador), configuracion de schedule (dias, hora, activar/desactivar), log en tiempo real con polling AJAX |
| **Entries** | Flujo editorial completo: generar borrador -> aprobar -> publicar. Filtros por estado, acciones inline (aprobar/rechazar/revertir) |
| **Tools** | Busqueda y gestion del inventario de herramientas |
| **Quality** | Metricas de calidad (completeness, diversity, coverage, hallucination risk), costos acumulados, tendencias con graficos |

### Flujo Editorial

```
[Agente genera borrador] → [Admin revisa] → [Aprobar] → [Visible en blog]
                                           → [Rechazar] → [No se publica]
```

Las entradas generadas por el agente entran con `status=draft` y no son visibles en el blog publico hasta que el admin las aprueba.

## Rutas Publicas

| Metodo | Ruta | Descripcion |
|---|---|---|
| GET | `/` | Blog principal con entradas publicadas |
| GET | `/inventario` | Grid de herramientas con busqueda/filtros |
| GET | `/herramienta/<slug>` | Detalle de herramienta |
| GET | `/entrada/<YYYY-MM-DD>` | Detalle de entrada por fecha |
| GET | `/estadisticas` | Dashboard de metricas |
| GET | `/about` | Informacion del proyecto |

## API REST v1

| Metodo | Ruta | Auth | Descripcion |
|---|---|---|---|
| GET | `/api/v1/tools` | No | Lista herramientas (paginado, filtros) |
| GET | `/api/v1/tools/<slug>` | No | Detalle herramienta |
| GET | `/api/v1/entries` | No | Lista entradas |
| GET | `/api/v1/entries/<date>` | No | Detalle entrada |
| GET | `/api/v1/stats` | No | Estadisticas generales |
| POST | `/api/v1/chat` | No | Chat con SciBot |
| POST | `/api/v1/agent/run` | API Key | Trigger manual del agente |
| GET | `/api/v1/agent/runs` | API Key | Historial de ejecuciones |

## Rutas Admin (requiere login)

| Ruta | Descripcion |
|---|---|
| `/admin/login` | Login con username/password |
| `/admin/` | Dashboard con KPIs y monitor en vivo |
| `/admin/agent` | Centro de control del agente |
| `/admin/agent/run` | POST - Ejecutar pipeline completo |
| `/admin/agent/search` | POST - Solo buscar herramientas nuevas |
| `/admin/agent/schedule` | POST - Actualizar frecuencia del scheduler |
| `/admin/agent/status` | GET - Estado en tiempo real (JSON) |
| `/admin/entries` | Gestion de entradas con aprobacion |
| `/admin/entries/generate` | POST - Generar borrador con IA |
| `/admin/entries/<id>/approve` | POST - Aprobar entrada |
| `/admin/entries/<id>/reject` | POST - Rechazar entrada |
| `/admin/entries/<id>/draft` | POST - Revertir a borrador |
| `/admin/tools` | Gestion de herramientas |
| `/admin/quality` | Metricas de calidad detalladas |
| `/admin/refresh` | Pipeline de calidad: escaneo + actualizacion automatica |

## Pipeline de Agentes IA

El sistema utiliza un pipeline de 6 etapas configurable desde el panel admin:

```
[1. Investigador] → [2. Clasificador] → [2B. Actualizador] → [3. Redactor] → [4. Media] → [5. Evaluador]
   Sonnet 4          Sonnet 4              Sonnet 4            Opus 4         DALL-E 3     Sonnet 4
   + Tavily                                                    800-1500 pal.  + Favicon    + auto-repair
```

Adicionalmente, existe un **Pipeline de Calidad** independiente (activable desde Admin > Refresh Pipeline):
1. **Quality Reviewer** — escanea todo el inventario y asigna score 0-100 (descripcion, pricing, features, logo, plataforma)
2. **Research Agent** — investiga informacion faltante para herramientas con score bajo
3. **Content Writer** — genera contenido mejorado y auto-corrige logos, pricing y features

**Schedule por defecto:** Martes y Jueves a las 07:00 UTC (configurable desde Admin > Agent Control).

Para documentacion detallada del flujo, ver [docs/WORKFLOW.md](docs/WORKFLOW.md).

## SciBot - Asistente Conversacional

SciBot es un asistente integrado en la interfaz (widget flotante animado) que:

- Responde consultas sobre herramientas de investigacion
- Conoce el inventario completo de la plataforma
- Sugiere herramientas segun necesidades del usuario
- Usa Claude Sonnet 4 via CometAPI

## Configuracion CometAPI

Los modelos se configuran en `config.py`:

```python
MODELS = {
    'research':   'claude-sonnet-4-20250514',       # Investigacion + Tavily
    'classifier': 'claude-sonnet-4-20250514',       # Clasificacion rapida
    'writer':     'claude-opus-4-20250514',         # Redaccion editorial
    'evaluator':  'claude-sonnet-4-20250514',       # Evaluacion de calidad
    'chat':       'claude-sonnet-4-20250514',       # SciBot conversacional
    'fallback':   'gemini-2.5-flash-preview-04-17', # Modelo de respaldo
}
```

## Deploy en Railway

### Opcion 1: Desde GitHub (recomendado)

1. Ir a [railway.app](https://railway.app) y crear cuenta
2. **New Project** > **Deploy from GitHub repo**
3. Seleccionar `jzegarrag-centrum/scitools-radar`
4. Railway detecta automaticamente Python + Gunicorn
5. Agregar servicio **PostgreSQL** (Add New > Database > PostgreSQL)
6. Configurar variables de entorno en Settings > Variables:

| Variable | Valor | Descripcion |
|---|---|---|
| `COMETAPI_KEY` | `sk-...` | API key de CometAPI |
| `TAVILY_API_KEY` | `tvly-...` | API key de Tavily |
| `SECRET_KEY` | (generar) | Clave secreta Flask |
| `FLASK_ENV` | `production` | Modo produccion |
| `ADMIN_USERNAME` | `admin` | Usuario admin |
| `ADMIN_PASSWORD` | (elegir) | Password admin |
| `DATABASE_URL` | (auto) | Provista por Railway al agregar PostgreSQL |

7. En Settings > Deploy, verificar que el Start Command sea:
   ```
   gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
   ```

8. Railway hace deploy automatico en cada push a `master`

### Opcion 2: Railway CLI

```bash
# Instalar CLI
npm install -g @railway/cli

# Login y crear proyecto
railway login
railway init

# Agregar PostgreSQL
railway add --plugin postgresql

# Configurar variables
railway variables set COMETAPI_KEY=sk-...
railway variables set TAVILY_API_KEY=tvly-...
railway variables set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
railway variables set FLASK_ENV=production
railway variables set ADMIN_USERNAME=admin
railway variables set ADMIN_PASSWORD=TuPasswordSeguro

# Deploy
railway up
```

### Post-Deploy

Despues del primer deploy, ejecutar las migraciones:

```bash
# Opcion A: Desde Railway CLI
railway run flask db upgrade

# Opcion B: Las migraciones se ejecutan automaticamente si usas el Procfile con release command
```

Para cargar datos iniciales:
```bash
railway run python scripts/seed_data_windows.py
```

## Variables de Entorno

| Variable | Requerida | Default | Descripcion |
|---|---|---|---|
| `SECRET_KEY` | Si (prod) | `dev-secret-key...` | Clave secreta Flask |
| `DATABASE_URL` | Si (prod) | SQLite local | URI de PostgreSQL |
| `COMETAPI_KEY` | Si | - | API key CometAPI |
| `COMETAPI_BASE_URL` | No | `https://api.cometapi.com/v1` | Base URL del gateway |
| `TAVILY_API_KEY` | Si | - | API key Tavily Search |
| `FLASK_ENV` | No | `development` | `development` / `production` |
| `ADMIN_USERNAME` | No | `admin` | Username del admin |
| `ADMIN_PASSWORD` | No | `admin1234` | Password del admin |
| `ADMIN_EMAIL` | No | `admin@smartcentrum.edu.pe` | Email del admin |
| `AGENT_SCHEDULE_HOUR` | No | `7` | Hora UTC de ejecucion |
| `AGENT_SCHEDULE_DAYS` | No | `tue,thu` | Dias de ejecucion |
| `AGENT_ENABLED` | No | `True` | Activar scheduler |
| `AGENT_MAX_NEW_TOOLS` | No | `6` | Max herramientas nuevas por ejecucion |
| `AGENT_MAX_UPDATES` | No | `5` | Max actualizaciones por ejecucion |
| `API_KEY` | No | - | API key para endpoints protegidos |
| `REDIS_URL` | No | - | Redis para cache (opcional, usa SimpleCache) |
| `PORT` | No | `5000` | Puerto (Railway lo asigna automaticamente) |

## Licencia

Proyecto interno Smart Centrum - CENTRUM PUCP
