"""
Rutas públicas - Blog, inventario, estadísticas
"""
from flask import Blueprint, render_template, request, abort
from app.models import Tool, Entry, Update, AgentRun, db
from app.services.search_service import SearchService
from app.services.stats_service import StatsService
from app import cache

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@cache.cached(timeout=300)
def index():
    """Blog principal - entradas ordenadas por fecha"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    entries = Entry.query.filter(
        db.or_(Entry.status == 'published', Entry.status.is_(None))
    ).order_by(Entry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    total_tools = Tool.query.count()
    total_entries = Entry.query.filter(
        db.or_(Entry.status == 'published', Entry.status.is_(None))
    ).count()
    
    return render_template(
        'index.html',
        entries=entries,
        total_tools=total_tools,
        total_entries=total_entries
    )


@main_bp.route('/inventario')
def inventario():
    """Grid de herramientas con búsqueda y filtros"""
    query = request.args.get('q', '')
    field = request.args.get('field', '')
    category = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Búsqueda
    if query or field or category:
        tools = SearchService.search_tools(
            query=query,
            field=field if field else None,
            category=category if category else None,
            limit=per_page * 10  # Pre-filter para paginación manual
        )
        # Paginación manual simple para resultados filtrados
        start = (page - 1) * per_page
        end = start + per_page
        tools_page = tools[start:end]
        has_next = len(tools) > end
        has_prev = page > 1
    else:
        # Sin filtros: query directo con paginación
        tools_query = Tool.query.filter_by(status='active').order_by(Tool.last_updated.desc())
        paginated = tools_query.paginate(page=page, per_page=per_page, error_out=False)
        tools_page = paginated.items
        has_next = paginated.has_next
        has_prev = paginated.has_prev
    
    # Opciones para filtros
    fields = SearchService.get_all_fields()
    categories = SearchService.get_all_categories()
    
    return render_template(
        'inventario.html',
        tools=tools_page,
        query=query,
        field=field,
        category=category,
        fields=fields,
        categories=categories,
        page=page,
        has_next=has_next,
        has_prev=has_prev
    )


@main_bp.route('/herramienta/<slug>')
@cache.cached(timeout=600, query_string=True)
def herramienta_detalle(slug):
    """Detalle de una herramienta"""
    tool = Tool.query.filter_by(slug=slug).first_or_404()
    
    # Entradas donde aparece (safe for both dynamic/lazy relationships)
    try:
        entries = tool.entries.order_by(Entry.date.desc()).limit(10).all()
    except Exception:
        entries = sorted(tool.entries, key=lambda e: e.date, reverse=True)[:10]
    
    # Actualizaciones
    try:
        updates = tool.updates.order_by(Update.created_at.desc()).limit(10).all()
    except Exception:
        updates = sorted(tool.updates, key=lambda u: u.created_at, reverse=True)[:10]
    
    return render_template(
        'herramienta_detalle.html',
        tool=tool,
        entries=entries,
        updates=updates
    )


@main_bp.route('/estadisticas')
@cache.cached(timeout=600)
def estadisticas():
    """Dashboard público de estadísticas"""
    stats = StatsService.get_dashboard_stats()
    timeline = StatsService.get_tools_timeline(months=12)
    
    return render_template(
        'estadisticas.html',
        stats=stats,
        timeline=timeline
    )


@main_bp.route('/entrada/<date_str>')
def entrada_detalle(date_str):
    """Detalle de una entrada del blog por fecha (YYYY-MM-DD)"""
    from datetime import datetime
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        abort(404)
    
    entry = Entry.query.filter(
        Entry.date == date_obj,
        db.or_(Entry.status == 'published', Entry.status.is_(None))
    ).first_or_404()
    
    # Tools and updates for this entry
    tools = list(entry.tools)
    updates = list(entry.updates)
    tools_count = len(tools)
    updates_count = len(updates)
    
    # Agent run (if any)
    agent_run = AgentRun.query.filter_by(entry_id=entry.id).first() if hasattr(AgentRun, 'entry_id') else None
    
    # Previous / Next entries for navigation
    prev_entry = Entry.query.filter(
        Entry.date < entry.date,
        db.or_(Entry.status == 'published', Entry.status.is_(None))
    ).order_by(Entry.date.desc()).first()
    next_entry = Entry.query.filter(
        Entry.date > entry.date,
        db.or_(Entry.status == 'published', Entry.status.is_(None))
    ).order_by(Entry.date.asc()).first()
    
    return render_template(
        'entrada_detalle.html',
        entry=entry,
        tools=tools,
        updates=updates,
        tools_count=tools_count,
        updates_count=updates_count,
        agent_run=agent_run,
        prev_entry=prev_entry,
        next_entry=next_entry
    )


@main_bp.route('/about')
def about():
    """Acerca de SciTools Radar"""
    return render_template('about.html')
