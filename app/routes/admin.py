"""
Panel de administracion - SciTools Radar
Incluye: login, dashboard, control de agente, gestion de entradas,
         busqueda de herramientas, gestion de frecuencia y activacion manual.
"""
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Tool, Entry, AgentRun, Update
from app.services.stats_service import StatsService
from datetime import datetime, date
import threading
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)

# ---------- Estado global de ejecucion (in-memory, para monitoreo) ----------
_agent_status = {
    'running': False,
    'step': '',
    'progress': 0,
    'log': [],
    'started_at': None,
    'run_id': None,
}


def _reset_status():
    _agent_status.update({
        'running': False,
        'step': '',
        'progress': 0,
        'log': [],
        'started_at': None,
        'run_id': None,
    })


# ==================== AUTH ====================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login de administrador (acepta username o email)"""
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Buscar por username o email
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()

        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin.dashboard'))
        else:
            flash('Usuario o contrasena incorrectos', 'danger')

    return render_template('admin/login.html')


@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))


# ==================== DASHBOARD ====================

@admin_bp.route('/')
@login_required
def dashboard():
    """Dashboard principal"""
    stats = StatsService.get_dashboard_stats()
    recent_entries = Entry.query.order_by(Entry.date.desc()).limit(5).all()
    recent_runs = AgentRun.query.order_by(AgentRun.started_at.desc()).limit(10).all()
    draft_count = Entry.query.filter_by(status='draft').count()

    # Configuracion actual del scheduler
    schedule_config = {
        'days': current_app.config.get('AGENT_SCHEDULE_DAYS', 'tue,thu'),
        'hour': current_app.config.get('AGENT_SCHEDULE_HOUR', 7),
        'enabled': current_app.config.get('AGENT_ENABLED', True),
    }

    return render_template(
        'admin/dashboard.html',
        stats=stats,
        recent_entries=recent_entries,
        recent_runs=recent_runs,
        draft_count=draft_count,
        schedule_config=schedule_config,
        agent_status=_agent_status,
    )


# ==================== HERRAMIENTAS ====================

@admin_bp.route('/tools')
@login_required
def tools():
    """Gestion de herramientas"""
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q', '', type=str)
    per_page = 50

    tools_query = Tool.query

    if query:
        tools_query = tools_query.filter(
            Tool.name.ilike(f'%{query}%') | Tool.summary.ilike(f'%{query}%')
        )

    tools_list = tools_query.order_by(Tool.last_updated.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('admin/tools.html', tools=tools_list, query=query)


# ==================== ENTRADAS ====================

@admin_bp.route('/entries')
@login_required
def entries():
    """Gestion de entradas con estado draft/approved/published"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    per_page = 20

    entries_query = Entry.query
    if status_filter:
        entries_query = entries_query.filter_by(status=status_filter)

    entries_list = entries_query.order_by(Entry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    draft_count = Entry.query.filter_by(status='draft').count()

    return render_template(
        'admin/entries.html',
        entries=entries_list,
        status_filter=status_filter,
        draft_count=draft_count,
    )


@admin_bp.route('/entries/<int:entry_id>/approve', methods=['POST'])
@login_required
def approve_entry(entry_id):
    """Aprobar una entrada (draft -> published)"""
    entry = Entry.query.get_or_404(entry_id)
    entry.status = 'published'
    db.session.commit()
    flash(f'Entrada del {entry.date} aprobada y publicada', 'success')
    return redirect(url_for('admin.entries'))


@admin_bp.route('/entries/<int:entry_id>/reject', methods=['POST'])
@login_required
def reject_entry(entry_id):
    """Rechazar una entrada (marcar como rechazada, no se elimina)"""
    entry = Entry.query.get_or_404(entry_id)
    entry.status = 'rejected'
    db.session.commit()
    flash(f'Entrada del {entry.date} rechazada', 'warning')
    return redirect(url_for('admin.entries'))


@admin_bp.route('/entries/<int:entry_id>/draft', methods=['POST'])
@login_required
def revert_entry(entry_id):
    """Mover una entrada de vuelta a borrador"""
    entry = Entry.query.get_or_404(entry_id)
    entry.status = 'draft'
    db.session.commit()
    flash(f'Entrada del {entry.date} movida a borrador', 'info')
    return redirect(url_for('admin.entries'))


@admin_bp.route('/entries/generate', methods=['POST'])
@login_required
def generate_entry():
    """Generar una nueva entrada del blog usando el pipeline completo"""
    if _agent_status['running']:
        flash('Ya hay un proceso en ejecucion. Espera a que termine.', 'warning')
        return redirect(url_for('admin.entries'))

    def _generate(app):
        with app.app_context():
            _agent_status.update({
                'running': True,
                'step': 'Generando entrada del blog...',
                'progress': 5,
                'log': ['Iniciando generacion de entrada...'],
                'started_at': datetime.utcnow().isoformat(),
            })

            run = AgentRun(started_at=datetime.utcnow(), status='running')
            db.session.add(run)
            db.session.commit()
            _agent_status['run_id'] = run.id

            try:
                # Step 1: Research
                _agent_status['step'] = 'Paso 1/8: Investigando nuevas herramientas...'
                _agent_status['progress'] = 10
                _agent_status['log'].append('[STEP 1] Research Agent (LLM + Tavily)')

                existing_tools = Tool.query.filter_by(status='active').all()
                existing_slugs = [t.slug for t in existing_tools]

                from app.agent.researcher import research_daily_tools
                findings = research_daily_tools(existing_slugs)
                run.tools_found = len(findings)
                db.session.commit()

                _agent_status['log'].append(f'  Encontradas {len(findings)} herramientas potenciales')

                # Step 2: Classify
                _agent_status['step'] = 'Paso 2/8: Clasificando hallazgos...'
                _agent_status['progress'] = 25
                _agent_status['log'].append('[STEP 2] Classifier Agent')

                if findings:
                    from app.agent.classifier import classify_findings
                    classified = classify_findings(findings, existing_tools)
                else:
                    classified = {'new_tools': [], 'updates': []}

                new_tools_data = classified.get('new_tools', [])[:current_app.config.get('AGENT_MAX_NEW_TOOLS', 6)]
                updates_from_classifier = classified.get('updates', [])[:current_app.config.get('AGENT_MAX_UPDATES', 5)]

                run.tools_new = len(new_tools_data)
                db.session.commit()

                _agent_status['log'].append(f'  {len(new_tools_data)} nuevas, {len(updates_from_classifier)} updates del clasificador')

                # Step 2B: Tool Updater — refrescar herramientas existentes
                _agent_status['step'] = 'Paso 3/8: Actualizando herramientas existentes...'
                _agent_status['progress'] = 40
                _agent_status['log'].append('[STEP 2B] Tool Updater')

                from app.agent.updater import refresh_existing_tools, apply_tool_updates
                from app.agent.scheduler import _select_tools_for_refresh
                max_refresh = current_app.config.get('AGENT_MAX_REFRESH', 10)
                tools_to_refresh = _select_tools_for_refresh(existing_tools, max_refresh)

                updater_results = []
                if tools_to_refresh:
                    updater_results = refresh_existing_tools(tools_to_refresh)
                    update_stats = apply_tool_updates(updater_results)
                    _agent_status['log'].append(f'  {update_stats["updated"]} herramientas actualizadas')
                else:
                    _agent_status['log'].append('  Sin herramientas para refrescar')

                # Combinar updates para el writer
                all_updates = list(updates_from_classifier)
                for ur in updater_results:
                    for change in ur.get('changes', []):
                        all_updates.append({
                            'tool_slug': ur['tool_slug'],
                            'field_updated': change.get('field', 'summary'),
                            'new_value': change.get('new_value', ''),
                            'description': f"{ur.get('tool_name', ur['tool_slug'])}: {change.get('reason', 'actualizacion')}"
                        })

                run.updates_count = len(all_updates)
                db.session.commit()

                # Si no hay nada, terminar
                if not new_tools_data and not all_updates:
                    _agent_status['log'].append('Sin resultados nuevos ni actualizaciones')
                    run.status = 'success'
                    run.finished_at = datetime.utcnow()
                    db.session.commit()
                    _agent_status.update({'running': False, 'step': 'Completado (sin novedades)', 'progress': 100})
                    return

                # Step 3: Write
                _agent_status['step'] = 'Paso 4/8: Redactando entrada...'
                _agent_status['progress'] = 55
                _agent_status['log'].append('[STEP 3] Writer Agent')

                from app.agent.writer import write_daily_entry
                from datetime import timedelta
                target_date = date.today()
                if Entry.query.filter_by(date=target_date).first():
                    for offset in range(1, 30):
                        candidate = target_date + timedelta(days=offset)
                        if not Entry.query.filter_by(date=candidate).first():
                            target_date = candidate
                            _agent_status['log'].append(f'  Usando fecha: {target_date}')
                            break
                entry_data = write_daily_entry(
                    {'new_tools': new_tools_data, 'updates': all_updates},
                    target_date
                )

                # Step 4: Create in DB (as draft)
                _agent_status['step'] = 'Paso 5/8: Creando entrada en BD...'
                _agent_status['progress'] = 70
                _agent_status['log'].append('[STEP 4] Entry Creator')

                from app.agent.scheduler import create_entry_from_data
                entry = create_entry_from_data(entry_data, force=True)
                entry.status = 'draft'  # Como borrador para aprobacion
                run.entry_id = entry.id
                db.session.commit()

                _agent_status['log'].append(f'  Entrada creada: ID={entry.id}, date={entry.date}')

                # Step 4B: Cover Image
                _agent_status['step'] = 'Paso 6/8: Generando imagen de portada...'
                _agent_status['progress'] = 82
                _agent_status['log'].append('[STEP 4B] Cover Image Generation')

                from app.agent.scheduler import generate_cover_image, fetch_tool_logos
                generate_cover_image(entry)

                # Step 4C: Tool Logos
                _agent_status['step'] = 'Paso 7/8: Obteniendo logos de herramientas...'
                _agent_status['progress'] = 86
                _agent_status['log'].append('[STEP 4C] Tool Logo Fetching')
                fetch_tool_logos(entry)

                # Step 5: Evaluate quality
                _agent_status['step'] = 'Paso 8/8: Evaluando calidad...'
                _agent_status['progress'] = 90
                _agent_status['log'].append('[STEP 5] Quality Evaluator')

                from app.agent.evaluator import evaluate_entry_quality
                scores = evaluate_entry_quality(entry)

                run.completeness = scores.get('completeness')
                run.field_diversity = scores.get('field_diversity')
                run.social_coverage = scores.get('social_coverage')
                run.hallucination_risk = scores.get('hallucination_risk')
                run.models_used = {
                    'research': current_app.config['MODELS']['research'],
                    'classifier': current_app.config['MODELS']['classifier'],
                    'writer': current_app.config['MODELS']['writer'],
                    'evaluator': current_app.config['MODELS']['evaluator'],
                }
                run.status = 'success'
                run.finished_at = datetime.utcnow()
                db.session.commit()

                _agent_status['log'].append(f'Completado exitosamente en {run.duration_seconds:.1f}s')
                _agent_status['log'].append(f'  Nuevas: {len(new_tools_data)}, Actualizaciones: {len(all_updates)}')
                _agent_status.update({'running': False, 'step': 'Completado', 'progress': 100})

            except Exception as e:
                logger.error(f'Generate entry failed: {e}', exc_info=True)
                run.status = 'failed'
                run.error = str(e)
                run.finished_at = datetime.utcnow()
                db.session.commit()
                _agent_status['log'].append(f'ERROR: {str(e)}')
                _agent_status.update({'running': False, 'step': f'Error: {str(e)[:80]}', 'progress': 0})

    app = current_app._get_current_object()
    t = threading.Thread(target=_generate, args=(app,), daemon=True)
    t.start()

    flash('Generacion de entrada iniciada. Revisa el progreso en tiempo real.', 'info')
    return redirect(url_for('admin.agent_control'))


# ==================== AGENTE ====================

@admin_bp.route('/agent')
@login_required
def agent_control():
    """Centro de control del agente"""
    runs = AgentRun.query.order_by(AgentRun.started_at.desc()).limit(30).all()

    # Config del scheduler
    schedule_config = {
        'days': current_app.config.get('AGENT_SCHEDULE_DAYS', 'tue,thu'),
        'hour': current_app.config.get('AGENT_SCHEDULE_HOUR', 7),
        'enabled': current_app.config.get('AGENT_ENABLED', True),
        'max_new_tools': current_app.config.get('AGENT_MAX_NEW_TOOLS', 6),
        'max_updates': current_app.config.get('AGENT_MAX_UPDATES', 5),
    }

    quality_trends = StatsService.get_agent_quality_trends(days=30)
    cost_summary = StatsService.get_agent_cost_summary(days=30)

    return render_template(
        'admin/agent_control.html',
        runs=runs,
        schedule_config=schedule_config,
        quality_trends=quality_trends,
        cost_summary=cost_summary,
        agent_status=_agent_status,
    )


@admin_bp.route('/agent/run', methods=['POST'])
@login_required
def run_agent():
    """Trigger manual del pipeline completo del agente (en background thread)"""
    if _agent_status['running']:
        flash('El agente ya esta en ejecucion.', 'warning')
        return redirect(url_for('admin.agent_control'))

    def _run_full_pipeline(app):
        with app.app_context():
            _agent_status.update({
                'running': True,
                'step': 'Iniciando pipeline completo...',
                'progress': 5,
                'log': ['Pipeline completo iniciado por admin'],
                'started_at': datetime.utcnow().isoformat(),
            })
            try:
                from app.agent.scheduler import run_daily_agent
                run_daily_agent(force=True)
                _agent_status['log'].append('Pipeline completado exitosamente')
                _agent_status.update({'running': False, 'step': 'Completado', 'progress': 100})
            except Exception as e:
                logger.error(f'Manual agent run failed: {e}', exc_info=True)
                _agent_status['log'].append(f'ERROR: {str(e)}')
                _agent_status.update({'running': False, 'step': f'Error: {str(e)[:80]}', 'progress': 0})

    app = current_app._get_current_object()
    t = threading.Thread(target=_run_full_pipeline, args=(app,), daemon=True)
    t.start()

    flash('Agente ejecutandose en background. Monitorea el progreso abajo.', 'info')
    return redirect(url_for('admin.agent_control'))


@admin_bp.route('/agent/search', methods=['POST'])
@login_required
def search_new_tools():
    """Buscar nuevas herramientas (solo paso 1: Research + Classify)"""
    if _agent_status['running']:
        flash('Ya hay un proceso en ejecucion.', 'warning')
        return redirect(url_for('admin.agent_control'))

    def _search(app):
        with app.app_context():
            _agent_status.update({
                'running': True,
                'step': 'Buscando nuevas herramientas...',
                'progress': 5,
                'log': ['Busqueda de herramientas iniciada'],
                'started_at': datetime.utcnow().isoformat(),
            })

            try:
                existing_tools = Tool.query.filter_by(status='active').all()
                existing_slugs = [t.slug for t in existing_tools]

                # Paso 1: Investigar nuevas herramientas
                _agent_status['step'] = 'Investigando fuentes (LLM + Tavily)...'
                _agent_status['progress'] = 20

                from app.agent.researcher import research_daily_tools
                findings = research_daily_tools(existing_slugs)

                _agent_status['log'].append(f'Encontradas {len(findings)} herramientas potenciales')

                # Paso 2: Clasificar
                _agent_status['step'] = 'Clasificando resultados...'
                _agent_status['progress'] = 40

                if findings:
                    from app.agent.classifier import classify_findings
                    classified = classify_findings(findings, existing_tools)
                else:
                    classified = {'new_tools': [], 'updates': []}

                new_count = len(classified.get('new_tools', []))
                upd_count = len(classified.get('updates', []))
                _agent_status['log'].append(f'Clasificacion: {new_count} nuevas, {upd_count} actualizaciones')

                # Paso 2B: Refrescar herramientas existentes
                _agent_status['step'] = 'Actualizando herramientas existentes...'
                _agent_status['progress'] = 60

                from app.agent.updater import refresh_existing_tools, apply_tool_updates
                from app.agent.scheduler import _select_tools_for_refresh
                max_refresh = current_app.config.get('AGENT_MAX_REFRESH', 10)
                tools_to_refresh = _select_tools_for_refresh(existing_tools, max_refresh)

                refresh_count = 0
                if tools_to_refresh:
                    updater_results = refresh_existing_tools(tools_to_refresh)
                    if updater_results:
                        update_stats = apply_tool_updates(updater_results)
                        refresh_count = update_stats['updated']
                        _agent_status['log'].append(f'  {refresh_count} herramientas actualizadas')
                        for detail in update_stats.get('details', [])[:10]:
                            _agent_status['log'].append(f'    - {detail["tool"]}: {detail["reason"][:60]}')

                # Insertar nuevas herramientas directamente
                _agent_status['step'] = 'Insertando nuevas herramientas...'
                _agent_status['progress'] = 80

                added = 0
                for tool_data in classified.get('new_tools', [])[:current_app.config.get('AGENT_MAX_NEW_TOOLS', 6)]:
                    existing = Tool.query.filter_by(slug=tool_data.get('slug', '')).first()
                    if not existing and tool_data.get('slug'):
                        new_tool = Tool(
                            slug=tool_data['slug'],
                            name=tool_data.get('name', tool_data['slug']),
                            summary=tool_data.get('summary'),
                            url=tool_data.get('url'),
                            field=tool_data.get('field'),
                            category=tool_data.get('category'),
                            pricing=tool_data.get('pricing'),
                            platform=tool_data.get('platform'),
                            status='active',
                        )
                        db.session.add(new_tool)
                        _agent_status['log'].append(f'  + Nueva: {new_tool.name}')
                        added += 1

                db.session.commit()

                _agent_status['log'].append(f'Completado: {added} nuevas, {refresh_count} actualizadas')
                _agent_status.update({
                    'running': False,
                    'step': f'Completado: {added} nuevas, {refresh_count} actualizadas',
                    'progress': 100,
                })

            except Exception as e:
                logger.error(f'Tool search failed: {e}', exc_info=True)
                _agent_status['log'].append(f'ERROR: {str(e)}')
                _agent_status.update({'running': False, 'step': f'Error: {str(e)[:80]}', 'progress': 0})

    app = current_app._get_current_object()
    t = threading.Thread(target=_search, args=(app,), daemon=True)
    t.start()

    flash('Busqueda de herramientas iniciada en background.', 'info')
    return redirect(url_for('admin.agent_control'))


@admin_bp.route('/agent/schedule', methods=['POST'])
@login_required
def update_schedule():
    """Actualizar la configuracion de frecuencia del agente"""
    days = request.form.get('days', 'tue,thu').strip()
    hour = request.form.get('hour', 7, type=int)
    enabled = request.form.get('enabled') == 'on'

    # Actualizar config en runtime
    current_app.config['AGENT_SCHEDULE_DAYS'] = days
    current_app.config['AGENT_SCHEDULE_HOUR'] = hour
    current_app.config['AGENT_ENABLED'] = enabled

    # Reconfigurar scheduler si existe
    from app.agent.scheduler import scheduler
    if scheduler:
        try:
            scheduler.remove_job('daily_research_agent')
        except Exception:
            pass

        if enabled:
            from apscheduler.triggers.cron import CronTrigger
            from app.agent.scheduler import run_daily_agent_with_context

            app_obj = current_app._get_current_object()
            scheduler.add_job(
                func=lambda: run_daily_agent_with_context(app_obj),
                trigger=CronTrigger(day_of_week=days, hour=hour, minute=0),
                id='daily_research_agent',
                name='SciTools Daily Research Agent',
                replace_existing=True,
            )
            flash(f'Scheduler actualizado: {days} a las {hour}:00', 'success')
        else:
            flash('Scheduler desactivado', 'warning')
    else:
        flash('Configuracion guardada (scheduler no activo en este entorno)', 'info')

    return redirect(url_for('admin.agent_control'))


# ==================== API DE ESTADO (para polling AJAX) ====================

@admin_bp.route('/agent/status')
@login_required
def agent_status_api():
    """Endpoint JSON para monitoreo en tiempo real del agente"""
    return jsonify(_agent_status)


# ==================== REFRESH PIPELINE ====================

# Estado global del pipeline de actualización (in-memory)
_refresh_status = {
    'running': False,
    'step': '',
    'progress': 0,
    'total': 0,
    'current': 0,
    'log': [],
    'started_at': None,
    'last_result': None,
}


def _reset_refresh_status():
    _refresh_status.update({
        'running': False,
        'step': '',
        'progress': 0,
        'total': 0,
        'current': 0,
        'log': [],
        'started_at': None,
    })


@admin_bp.route('/tools/refresh-all', methods=['GET'])
@login_required
def refresh_all_view():
    """Vista del pipeline de actualización masiva de herramientas"""
    from app.agent.refresh_pipeline import scan_all_tools, review_tool_quality
    from app.models import Tool

    # Estadísticas de calidad
    all_tools = Tool.query.filter_by(status='active').all()
    total_tools = len(all_tools)

    tools_with_features = sum(1 for t in all_tools if t.features)
    tools_with_editorial = sum(1 for t in all_tools if t.editorial)
    tools_auto_updated = sum(1 for t in all_tools if t.auto_updated)
    tools_complete = sum(
        1 for t in all_tools
        if t.summary and len(t.summary) >= 100 and t.features and t.editorial
    )

    # Herramientas que necesitan actualización (sin llamar al LLM)
    pending = []
    for t in all_tools:
        review = review_tool_quality(t)
        if review['needs_update']:
            pending.append({'tool': t, 'review': review})
    pending.sort(key=lambda x: x['review']['score'])

    dashboard_stats = {
        'total_tools': total_tools,
        'tools_complete': tools_complete,
        'pct_complete': round(tools_complete / total_tools * 100) if total_tools else 0,
        'tools_with_features': tools_with_features,
        'tools_with_editorial': tools_with_editorial,
        'tools_auto_updated': tools_auto_updated,
        'pending_count': len(pending),
    }

    categories = sorted({t.category for t in all_tools if t.category})

    return render_template(
        'admin/refresh_all.html',
        dashboard_stats=dashboard_stats,
        pending_tools=pending[:20],  # Mostrar máx 20 en la vista
        categories=categories,
        refresh_status=_refresh_status,
        last_result=_refresh_status.get('last_result'),
    )


@admin_bp.route('/tools/refresh-all', methods=['POST'])
@login_required
def refresh_all_run():
    """Ejecuta el pipeline de actualización masiva en background"""
    if _refresh_status['running']:
        flash('El pipeline ya está en ejecución. Espera a que termine.', 'warning')
        return redirect(url_for('admin.refresh_all_view'))

    # Parámetros opcionales
    category_filter = request.form.get('category_filter', '').strip() or None
    min_days_old = request.form.get('min_days_old', type=int)
    only_empty = request.form.get('only_empty_fields') == 'on'
    limit_str = request.form.get('limit', '').strip()
    limit = int(limit_str) if limit_str and limit_str.isdigit() else current_app.config.get('AGENT_MAX_REFRESH', 10)

    def _run_pipeline(app, params):
        with app.app_context():
            _refresh_status.update({
                'running': True,
                'step': 'Iniciando pipeline...',
                'progress': 0,
                'total': 0,
                'current': 0,
                'log': ['Pipeline de actualización iniciado'],
                'started_at': datetime.utcnow().isoformat(),
                'last_result': None,
            })

            def progress_cb(step, total, current, message):
                pct = int(current / total * 100) if total else 0
                _refresh_status.update({
                    'step': message,
                    'progress': pct,
                    'total': total,
                    'current': current,
                })
                _refresh_status['log'].append(message)
                logger.info(f'[RefreshPipeline] {message}')

            try:
                from app.agent.refresh_pipeline import run_refresh_pipeline
                result = run_refresh_pipeline(
                    category_filter=params['category_filter'],
                    min_days_old=params['min_days_old'],
                    only_empty_fields=params['only_empty_fields'],
                    limit=params['limit'],
                    rate_limit_seconds=params.get('rate_limit_seconds', 2.0),
                    progress_callback=progress_cb,
                )

                _refresh_status['last_result'] = result
                _refresh_status['log'].append(
                    f"Completado: {result['total_updated']} actualizadas, "
                    f"{result['total_errors']} errores en {result['duration_seconds']:.1f}s"
                )
                for detail in result.get('details', []):
                    status_icon = '✓' if detail['status'] == 'updated' else '✗'
                    msg = (
                        f"  {status_icon} {detail['tool_name']}: "
                        f"score {detail['score_before']} → {detail['score_after']}"
                    )
                    if detail.get('error'):
                        msg += f" [Error: {detail['error'][:60]}]"
                    _refresh_status['log'].append(msg)

            except Exception as e:
                logger.error(f'Refresh pipeline failed: {e}', exc_info=True)
                _refresh_status['log'].append(f'ERROR: {str(e)}')
            finally:
                _refresh_status['running'] = False
                _refresh_status['step'] = 'Completado'
                _refresh_status['progress'] = 100

    params = {
        'category_filter': category_filter,
        'min_days_old': min_days_old,
        'only_empty_fields': only_empty,
        'limit': limit,
        'rate_limit_seconds': 2.0,
    }

    app = current_app._get_current_object()
    t = threading.Thread(target=_run_pipeline, args=(app, params), daemon=True)
    t.start()

    flash('Pipeline de actualización iniciado en background. Revisa el progreso abajo.', 'info')
    return redirect(url_for('admin.refresh_all_view'))


@admin_bp.route('/tools/refresh-status')
@login_required
def refresh_status_api():
    """Endpoint JSON para polling del estado del pipeline de actualización"""
    return jsonify(_refresh_status)


# ==================== CALIDAD ====================

@admin_bp.route('/quality')
@login_required
def quality_metrics():
    """Metricas de calidad detalladas"""
    days = request.args.get('days', 30, type=int)
    trends = StatsService.get_agent_quality_trends(days=days)
    costs = StatsService.get_agent_cost_summary(days=days)

    runs = AgentRun.query.filter(
        AgentRun.status == 'success'
    ).order_by(AgentRun.started_at.desc()).limit(30).all()

    metrics = {
        'avg_completeness': sum(r.completeness or 0 for r in runs) / len(runs) if runs else 0,
        'avg_field_diversity': sum(r.field_diversity or 0 for r in runs) / len(runs) if runs else 0,
        'avg_social_coverage': sum(r.social_coverage or 0 for r in runs) / len(runs) if runs else 0,
        'avg_hallucination_risk': sum(r.hallucination_risk or 0 for r in runs) / len(runs) if runs else 0,
    }

    return render_template(
        'admin/quality.html',
        days=days,
        metrics=metrics,
        trends=trends,
        costs=costs,
        runs=runs,
    )
