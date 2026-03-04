"""
Panel de administración
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, Tool, Entry, AgentRun
from app.services.stats_service import StatsService
from datetime import datetime

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login de administrador"""
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin.dashboard'))
        else:
            flash('Email o contraseña incorrectos', 'danger')
    
    return render_template('admin/login.html')


@admin_bp.route('/logout')
@login_required
def logout():
    """Logout"""
    logout_user()
    return redirect(url_for('main.index'))


@admin_bp.route('/')
@login_required
def dashboard():
    """Dashboard principal del admin"""
    stats = StatsService.get_dashboard_stats()
    recent_entries = Entry.query.order_by(Entry.date.desc()).limit(5).all()
    recent_runs = AgentRun.query.order_by(AgentRun.started_at.desc()).limit(10).all()
    
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        recent_entries=recent_entries,
        recent_runs=recent_runs
    )


@admin_bp.route('/tools')
@login_required
def tools():
    """Gestión de herramientas"""
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q', '', type=str)
    per_page = 50
    
    tools_query = Tool.query
    
    if query:
        tools_query = tools_query.filter(
            Tool.name.ilike(f'%{query}%') | Tool.summary.ilike(f'%{query}%')
        )
    
    tools = tools_query.order_by(Tool.last_updated.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/tools.html', tools=tools, query=query)


@admin_bp.route('/entries')
@login_required
def entries():
    """Gestión de entradas"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    entries = Entry.query.order_by(Entry.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/entries.html', entries=entries)


@admin_bp.route('/agent')
@login_required
def agent_control():
    """Agent Control Center"""
    runs = AgentRun.query.order_by(AgentRun.started_at.desc()).limit(30).all()
    quality_trends = StatsService.get_agent_quality_trends(days=30)
    cost_summary = StatsService.get_agent_cost_summary(days=30)
    
    # Próxima ejecución (ejemplo: de lunes a viernes a las 7 AM)
    # TODO: calcular desde config del scheduler
    
    return render_template(
        'admin/agent_control.html',
        runs=runs,
        quality_trends=quality_trends,
        cost_summary=cost_summary
    )


@admin_bp.route('/agent/run', methods=['POST'])
@login_required
def run_agent():
    """Trigger manual del agente"""
    from app.agent.scheduler import run_daily_agent
    
    try:
        # Ejecutar en background (idealmente con RQ o Celery, aquí síncrono por simplicidad)
        # En producción, mejor agregar a cola Redis
        flash('Agente ejecutándose en background...', 'info')
        
        # TODO: Implementar ejecución async real
        # run_daily_agent()
        
        return redirect(url_for('admin.agent_control'))
    except Exception as e:
        flash(f'Error al ejecutar agente: {str(e)}', 'danger')
        return redirect(url_for('admin.agent_control'))


@admin_bp.route('/quality')
@login_required
def quality_metrics():
    """Métricas de calidad detalladas"""
    days = request.args.get('days', 30, type=int)
    
    # Obtener trends
    trends = StatsService.get_agent_quality_trends(days=days)
    
    # Obtener costos
    costs = StatsService.get_agent_cost_summary(days=days)
    
    # Obtener ejecuciones recientes
    runs = AgentRun.query.filter(
        AgentRun.status == 'success'
    ).order_by(AgentRun.started_at.desc()).limit(30).all()
    
    # Calcular métricas promedio
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
        runs=runs
    )
