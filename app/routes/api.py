"""
API REST v1
"""
from flask import Blueprint, jsonify, request, current_app
from functools import wraps
from app.models import Tool, Entry, Update, AgentRun
from app.services.search_service import SearchService
from app.services.stats_service import StatsService
from app import db

api_bp = Blueprint('api', __name__)


def require_api_key(f):
    """Decorator para requerir API key"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key or api_key != current_app.config['API_KEY']:
            return jsonify({'error': 'Invalid or missing API key'}), 401
        
        return f(*args, **kwargs)
    return decorated_function


@api_bp.route('/tools', methods=['GET'])
def get_tools():
    """GET /api/v1/tools - Lista de herramientas"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    query = request.args.get('q', '')
    field = request.args.get('field', '')
    category = request.args.get('category', '')
    
    if query or field or category:
        tools = SearchService.search_tools(
            query=query,
            field=field if field else None,
            category=category if category else None,
            limit=per_page * 10
        )
        # Paginación manual
        start = (page - 1) * per_page
        end = start + per_page
        tools_page = tools[start:end]
        total = len(tools)
    else:
        tools_query = Tool.query.filter_by(status='active').order_by(Tool.last_updated.desc())
        paginated = tools_query.paginate(page=page, per_page=per_page, error_out=False)
        tools_page = paginated.items
        total = paginated.total
    
    return jsonify({
        'tools': [tool_to_dict(t) for t in tools_page],
        'page': page,
        'per_page': per_page,
        'total': total
    })


@api_bp.route('/tools/<slug>', methods=['GET'])
def get_tool(slug):
    """GET /api/v1/tools/<slug> - Detalle de herramienta"""
    tool = Tool.query.filter_by(slug=slug).first_or_404()
    return jsonify(tool_to_dict(tool, detailed=True))


@api_bp.route('/entries', methods=['GET'])
def get_entries():
    """GET /api/v1/entries - Lista de entradas"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    entries = Entry.query.order_by(Entry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'entries': [entry_to_dict(e) for e in entries.items],
        'page': page,
        'per_page': per_page,
        'total': entries.total
    })


@api_bp.route('/entries/<date_str>', methods=['GET'])
def get_entry(date_str):
    """GET /api/v1/entries/<YYYY-MM-DD> - Detalle de entrada"""
    from datetime import datetime
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    entry = Entry.query.filter_by(date=date_obj).first_or_404()
    return jsonify(entry_to_dict(entry, detailed=True))


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    """GET /api/v1/stats - Estadísticas generales"""
    stats = StatsService.get_dashboard_stats()
    return jsonify(stats)


@api_bp.route('/agent/run', methods=['POST'])
@require_api_key
def trigger_agent():
    """POST /api/v1/agent/run - Trigger manual del agente (requiere API key)"""
    from app.agent.scheduler import run_daily_agent
    
    try:
        # TODO: Ejecutar async con RQ/Celery
        # Por ahora, solo crear un AgentRun con status='queued'
        run = AgentRun(status='queued')
        db.session.add(run)
        db.session.commit()
        
        return jsonify({
            'message': 'Agent run queued',
            'run_id': run.id
        }), 202
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/agent/runs', methods=['GET'])
@require_api_key
def get_agent_runs():
    """GET /api/v1/agent/runs - Historial de ejecuciones del agente"""
    limit = request.args.get('limit', 20, type=int)
    
    runs = AgentRun.query.order_by(AgentRun.started_at.desc()).limit(limit).all()
    
    return jsonify({
        'runs': [agent_run_to_dict(r) for r in runs]
    })


@api_bp.route('/chat', methods=['POST'])
def chat():
    """POST /api/v1/chat - Conversational agent endpoint"""
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'Field "message" is required'}), 400

    user_message = data['message'].strip()
    history = data.get('history', [])

    if not user_message:
        return jsonify({'error': 'Message cannot be empty'}), 400

    try:
        # Build context about the tools inventory
        tools = Tool.query.filter_by(status='active').order_by(Tool.name).all()
        tools_summary = ', '.join([f"{t.name} ({t.category or 'sin categoria'})" for t in tools[:50]])
        total_tools = Tool.query.count()
        total_entries = Entry.query.count()

        system_prompt = (
            "Eres SciBot, el asistente virtual de SciTools Radar, una plataforma de monitoreo "
            "de herramientas de investigacion cientifica de Smart Centrum. "
            "Respondes en espanol de forma amable, concisa y profesional. "
            "Puedes ayudar a los usuarios a encontrar herramientas, entender categorias "
            "y resolver dudas sobre la plataforma.\n\n"
            f"INVENTARIO ACTUAL: {total_tools} herramientas monitoreadas, {total_entries} entradas de blog.\n"
            f"HERRAMIENTAS (primeras 50): {tools_summary}\n\n"
            "Si te preguntan por una herramienta especifica, proporciona informacion relevante "
            "del inventario. Si no conoces la respuesta, indicalo honestamente."
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 8 messages)
        for msg in history[-8:]:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role in ('user', 'assistant') and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})

        from app.services.llm_service import get_llm_service
        llm = get_llm_service()
        response = llm.chat_call(messages=messages)
        reply = response.choices[0].message.content

        return jsonify({'reply': reply})

    except Exception as e:
        current_app.logger.error(f"Chat error: {e}")
        return jsonify({
            'reply': 'Lo siento, ocurrio un error al procesar tu consulta. Intenta de nuevo en unos segundos.'
        }), 200


# Serializers
def tool_to_dict(tool, detailed=False):
    """Serializa Tool a dict"""
    data = {
        'id': tool.id,
        'slug': tool.slug,
        'name': tool.name,
        'summary': tool.summary,
        'url': tool.url,
        'field': tool.field,
        'category': tool.category,
        'first_seen': tool.first_seen.isoformat(),
        'last_updated': tool.last_updated.isoformat(),
        'status': tool.status,
    }
    
    if detailed:
        data['entries_count'] = len(tool.entries)
        data['updates_count'] = len(tool.updates)
    
    return data


def entry_to_dict(entry, detailed=False):
    """Serializa Entry a dict"""
    data = {
        'id': entry.id,
        'date': entry.date.isoformat(),
        'editorial': entry.editorial,
        'created_at': entry.created_at.isoformat(),
        'created_by': entry.created_by,
        'tools_count': len(entry.tools),
        'updates_count': len(entry.updates),
    }
    
    if detailed:
        data['tools'] = [tool_to_dict(t) for t in entry.tools]
        data['updates'] = [update_to_dict(u) for u in entry.updates]
    
    return data


def update_to_dict(update):
    """Serializa Update a dict"""
    return {
        'id': update.id,
        'tool_slug': update.tool.slug,
        'field_updated': update.field_updated,
        'old_value': update.old_value,
        'new_value': update.new_value,
        'description': update.description,
        'created_at': update.created_at.isoformat(),
    }


def agent_run_to_dict(run):
    """Serializa AgentRun a dict"""
    return {
        'id': run.id,
        'started_at': run.started_at.isoformat(),
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
        'status': run.status,
        'duration_seconds': run.duration_seconds,
        'tools_found': run.tools_found,
        'tools_new': run.tools_new,
        'updates_count': run.updates_count,
        'completeness': run.completeness,
        'field_diversity': run.field_diversity,
        'social_coverage': run.social_coverage,
        'hallucination_risk': run.hallucination_risk,
        'total_tokens': run.total_tokens,
        'total_cost_usd': run.total_cost_usd,
        'models_used': run.models_used,
        'error': run.error,
    }
