# SciTools Radar

**Plataforma de monitoreo automatizado de herramientas de investigacion cientifica** impulsada por un pipeline de agentes de IA.

Desarrollado por [Smart Centrum](https://smartcentrum.edu.pe).

---

## Descripcion

SciTools Radar rastrea, clasifica y reporta herramientas digitales para la investigacion academica y cientifica. Combina un pipeline de 5 agentes de IA con curaduria humana para:

- **Descubrir** nuevas herramientas via busqueda automatizada (Tavily API)
- **Clasificar** herramientas por campo cientifico y categoria
- **Redactar** entradas de blog editoriales de calidad profesional
- **Evaluar** la calidad del contenido generado con metricas cuantitativas
- **Publicar** automaticamente 2 veces por semana (martes y jueves)

## Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Backend | Flask 3.1, SQLAlchemy, Flask-Migrate |
| Base de datos | PostgreSQL (produccion) / SQLite (desarrollo) |
| LLM Gateway | CometAPI (OpenAI SDK compatible, 500+ modelos) |
| Modelos IA | GPT-5.3, Gemini 3.1 Flash Lite, GPT-5 Nano, DeepSeek v3.2 |
| Busqueda web | Tavily API |
| Scheduler | APScheduler (martes y jueves, 07:00 UTC) |
| Chat | SciBot (asistente conversacional integrado) |
| Deploy | Railway con Nixpacks |
| Frontend | Jinja2 + Font Awesome 6.5 + Chart.js 4 |

## Estructura del Proyecto

```
scitools-flask/
├── app/
│   ├── __init__.py            # Factory Flask + extensiones
│   ├── models.py              # SQLAlchemy models (Tool, Entry, Update, AgentRun, User)
│   ├── routes/
│   │   ├── main.py            # Rutas publicas (blog, inventario, estadisticas)
│   │   ├── admin.py           # Panel de administracion
│   │   └── api.py             # API REST v1 + chat endpoint
│   ├── services/
│   │   ├── llm_service.py     # Cliente CometAPI unificado
│   │   ├── search_service.py  # Full-text search + filtros
│   │   └── stats_service.py   # Analytics y metricas
│   ├── agent/
│   │   ├── researcher.py      # Agente investigador (GPT-5.3 + Tavily)
│   │   ├── classifier.py      # Agente clasificador (Gemini 3.1 Flash Lite)
│   │   ├── writer.py          # Agente redactor (GPT-5.3, JSON mode)
│   │   ├── evaluator.py       # Evaluador de calidad (GPT-5 Nano)
│   │   └── scheduler.py       # Orquestador del pipeline + APScheduler
│   └── templates/
│       ├── base.html           # Layout maestro + SciBot chat widget
│       ├── index.html          # Blog principal con hero y tarjetas
│       ├── inventario.html     # Grid de herramientas con busqueda
│       ├── herramienta_detalle.html  # Detalle de herramienta
│       ├── entrada_detalle.html      # Detalle de entrada del blog
│       ├── estadisticas.html   # Dashboard con Chart.js
│       ├── about.html          # Acerca de / pipeline IA
│       └── admin/              # 6 templates del panel admin
├── scripts/
│   ├── seed_data_windows.py   # Migrar datos del HTML original
│   └── check_db.py            # Verificar contenido de la BD
├── docs/
│   └── WORKFLOW.md            # Documentacion detallada del pipeline
├── migrations/                # Flask-Migrate (Alembic)
├── config.py                  # Configuracion dev/prod/test
├── wsgi.py                    # Entry point Flask
├── requirements.txt
├── .env / .env.example
├── Procfile                   # Railway
└── railway.toml
```

## Setup Local

```powershell
# 1. Clonar y crear virtual environment
cd scitools-flask
python -m venv venv
.\venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
copy .env.example .env
# Editar .env con tus API keys (COMETAPI_KEY, TAVILY_API_KEY)

# 4. Inicializar y migrar base de datos
flask db upgrade

# 5. Cargar datos iniciales desde HTML original
python scripts\seed_data_windows.py

# 6. Ejecutar servidor
flask run --port 5000
```

Abrir http://localhost:5000

## API Endpoints

### Publicos (sin autenticacion)
| Metodo | Ruta | Descripcion |
|---|---|---|
| GET | `/` | Blog principal con entradas |
| GET | `/inventario` | Grid de herramientas con busqueda/filtros |
| GET | `/herramienta/<slug>` | Detalle de herramienta |
| GET | `/entrada/<YYYY-MM-DD>` | Detalle de entrada por fecha |
| GET | `/estadisticas` | Dashboard de metricas |
| GET | `/about` | Informacion del proyecto |

### API REST v1
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

### Admin (requiere login)
| Ruta | Descripcion |
|---|---|
| `/admin` | Dashboard administrativo |
| `/admin/agent` | Agent Control Center |
| `/admin/quality` | Metricas de calidad |
| `/admin/tools` | Gestion de herramientas |
| `/admin/entries` | Gestion de entradas |

**Credenciales por defecto:** `admin@smartcentrum.edu.pe` / `changeme123`

## Pipeline de Agentes IA

El sistema utiliza un pipeline de 5 etapas que se ejecuta automaticamente martes y jueves a las 07:00 UTC:

```
[1. Investigador] → [2. Clasificador] → [3. Redactor] → [4. Creador BD] → [5. Evaluador]
   GPT-5.3           Gemini Flash         GPT-5.3         SQLAlchemy        GPT-5 Nano
   + Tavily                                JSON mode
```

Para documentacion detallada del flujo, ver [docs/WORKFLOW.md](docs/WORKFLOW.md).

## SciBot - Asistente Conversacional

SciBot es un asistente integrado en la interfaz (widget flotante con animatronic animado) que:

- Responde consultas sobre herramientas de investigacion
- Conoce el inventario completo de la plataforma
- Sugiere herramientas segun necesidades del usuario
- Usa GPT-5.3 via CometAPI

## Configuracion CometAPI

Los modelos se configuran en `config.py`:

```python
MODELS = {
    'research':   'gpt-5.3-chat-latest',     # Investigacion + Tavily
    'classifier': 'gemini-3.1-flash-lite',   # Clasificacion rapida
    'writer':     'gpt-5.3-chat-latest',     # Redaccion editorial
    'evaluator':  'gpt-5-nano',              # Evaluacion de calidad
    'chat':       'gpt-5.3-chat-latest',     # SciBot conversacional
    'fallback':   'deepseek-v3.2',           # Modelo de respaldo
}
```

## Deploy en Railway

```bash
railway login
railway init
railway add postgresql
railway up
```

Variables de entorno requeridas en Railway:
- `COMETAPI_KEY`
- `TAVILY_API_KEY`
- `SECRET_KEY`
- `DATABASE_URL` (auto-configurada por Railway)

## Licencia

Proyecto interno Smart Centrum - CENTRUM PUCP
