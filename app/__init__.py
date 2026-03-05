import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_caching import Cache
from config import config

# Extensiones
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
cache = Cache()


def create_app(config_name=None):
    """Application factory pattern"""
    
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'production')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Inicializar extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    cache.init_app(app)
    
    # Configurar login
    login_manager.login_view = 'admin.login'
    login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
    
    # Importar modelos (necesario para Migrate)
    from app import models
    
    # Registrar blueprints
    from app.routes.main import main_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    
    # Iniciar scheduler del agente (solo en producción o si está habilitado)
    if app.config['AGENT_ENABLED']:
        from app.agent.scheduler import init_scheduler
        init_scheduler(app)
    
    # Context processors para templates
    @app.context_processor
    def inject_theme():
        return {'theme': app.config['THEME_COLORS']}
    
    # Health check (lightweight, no DB)
    @app.route('/health')
    def health():
        return {'status': 'ok'}, 200
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        from flask import request as req
        if req.path.startswith('/api/'):
            return {'error': 'Not found'}, 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def server_error(e):
        from flask import request as req
        if req.path.startswith('/api/'):
            return {'error': 'Internal server error'}, 500
        return render_template('errors/500.html'), 500
    
    # ── Garantizar esquema de BD ────────────────────────────
    _ensure_schema(app)

    # ── Limpiar AgentRuns atascados ──────────────────────────
    _cleanup_stuck_runs(app)

    # ── Corregir categorías con letras sueltas ───────────────
    _fix_letter_categories(app)

    # ── Garantizar usuario admin ──────────────────────────────
    _ensure_admin(app)
    
    return app


def _ensure_schema(app):
    """Ensure all required columns exist (safe for cold starts)."""
    try:
        with app.app_context():
            from sqlalchemy import text, inspect as sa_inspect
            inspector = sa_inspect(db.engine)
            
            # Check if 'entry' table exists at all
            if 'entry' not in inspector.get_table_names():
                db.create_all()
                app.logger.info('Tables created via create_all()')
                return
            
            # Check for cover_image_url column
            columns = [c['name'] for c in inspector.get_columns('entry')]
            if 'cover_image_url' not in columns:
                with db.engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE entry ADD COLUMN cover_image_url VARCHAR(1000)"
                    ))
                    conn.commit()
                app.logger.info('Added cover_image_url column to entry table')
    except Exception as exc:
        app.logger.warning('Schema ensure skipped: %s', exc)


def _cleanup_stuck_runs(app):
    """Marca AgentRuns atascados en 'running' como 'failed' al iniciar."""
    try:
        with app.app_context():
            from app.models import AgentRun
            from datetime import datetime
            stuck = AgentRun.query.filter_by(status='running').all()
            for run in stuck:
                run.status = 'failed'
                run.error = 'Stuck run cleaned up on startup'
                run.finished_at = run.finished_at or datetime.utcnow()
            if stuck:
                db.session.commit()
                app.logger.info('Cleaned up %d stuck AgentRun records', len(stuck))
    except Exception:
        pass


def _fix_letter_categories(app):
    """Reemplaza categorías de una sola letra (A-P) con nombres descriptivos."""
    LETTER_MAP = {
        'A': 'Bases de datos bibliográficas',
        'B': 'IA para investigación',
        'C': 'Mapeo por citaciones',
        'D': 'Bibliometría y cienciometría',
        'E': 'Métricas e impacto',
        'F': 'Gestores de referencias',
        'G': 'Escritura académica con IA',
        'H': 'Edición y publicación',
        'I': 'Ilustración y visualización',
        'J': 'Revisiones sistemáticas',
        'K': 'Gestión del conocimiento',
        'L': 'Ciencia abierta y reproducibilidad',
        'M': 'Búsqueda de financiamiento',
        'N': 'Análisis cualitativo y métodos mixtos',
        'O': 'Notebooks y ambientes de cómputo',
        'P': 'Gestión de proyectos',
    }
    try:
        with app.app_context():
            from app.models import Tool
            fixed = 0
            for tool in Tool.query.all():
                if tool.category and tool.category.strip() in LETTER_MAP:
                    old = tool.category
                    tool.category = LETTER_MAP[old.strip()]
                    fixed += 1
            if fixed:
                db.session.commit()
                app.logger.info('Fixed %d tools with letter categories', fixed)
    except Exception:
        pass


def _ensure_admin(app):
    """Crea el usuario admin si no existe (seguro pre-migración)."""
    try:
        with app.app_context():
            from app.models import User
            admin = User.query.filter_by(
                username=app.config['ADMIN_USERNAME']
            ).first()
            if admin is None:
                admin = User(
                    username=app.config['ADMIN_USERNAME'],
                    email=app.config['ADMIN_EMAIL'],
                    name='Administrador',
                    is_admin=True,
                )
                admin.set_password(app.config['ADMIN_PASSWORD'])
                db.session.add(admin)
                db.session.commit()
                app.logger.info('Admin user created (%s)', app.config['ADMIN_USERNAME'])
    except Exception:
        # Las tablas pueden no existir aún (pre-migración)
        pass
