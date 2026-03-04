import os
from flask import Flask
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
        config_name = os.environ.get('FLASK_ENV', 'development')
    
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
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return {'error': 'Not found'}, 404
    
    @app.errorhandler(500)
    def server_error(e):
        return {'error': 'Internal server error'}, 500
    
    return app
