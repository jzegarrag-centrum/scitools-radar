import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuración base"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database — Railway puede inyectar con distintos nombres
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('DATABASE_URL')
        or os.environ.get('DATABASE_PRIVATE_URL')
        or os.environ.get('DATABASE_PUBLIC_URL')
        or 'sqlite:///scitools.db'
    )
    if SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        # Railway usa postgres:// pero SQLAlchemy 1.4+ requiere postgresql://
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    
    # Cache (usa SimpleCache si Redis no está disponible)
    REDIS_URL = os.environ.get('REDIS_URL')
    if REDIS_URL:
        CACHE_TYPE = 'RedisCache'
        CACHE_REDIS_URL = REDIS_URL
    else:
        CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # CometAPI
    COMETAPI_KEY = os.environ.get('COMETAPI_KEY')
    COMETAPI_BASE_URL = os.environ.get('COMETAPI_BASE_URL', 'https://api.cometapi.com/v1')
    
    # Modelos LLM via CometAPI
    MODELS = {
        'research': 'claude-sonnet-4-20250514',
        'classifier': 'claude-sonnet-4-20250514',
        'writer': 'claude-opus-4-20250514',
        'evaluator': 'claude-sonnet-4-20250514',
        'chat': 'claude-sonnet-4-20250514',
        'fallback': 'gemini-2.5-flash-preview-04-17',
    }
    
    # Web Search
    TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
    
    # Admin
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@smartcentrum.edu.pe')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin1234')
    
    # Agent
    AGENT_SCHEDULE_HOUR = int(os.environ.get('AGENT_SCHEDULE_HOUR', 7))
    AGENT_SCHEDULE_DAYS = os.environ.get('AGENT_SCHEDULE_DAYS', 'tue,thu')
    AGENT_MAX_NEW_TOOLS = int(os.environ.get('AGENT_MAX_NEW_TOOLS', 6))
    AGENT_MAX_UPDATES = int(os.environ.get('AGENT_MAX_UPDATES', 5))
    AGENT_ENABLED = os.environ.get('AGENT_ENABLED', 'True').lower() == 'true'
    
    # API
    API_KEY = os.environ.get('API_KEY')
    
    # Pagination
    TOOLS_PER_PAGE = 20
    ENTRIES_PER_PAGE = 10
    
    # Smart Centrum Design
    THEME_COLORS = {
        'azul': '#003865',
        'naranja': '#FF6B00',
        'naranja_dark': '#E55D00',
        'gris_oscuro': '#333333',
        'gris_claro': '#F5F5F5',
        'borde': '#E5E5E5',
    }


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    TESTING = False
    
    # Security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


class TestingConfig(Config):
    """Configuración para tests"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    AGENT_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
