"""
Modelos SQLAlchemy para SciTools Radar
"""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


# Tabla asociativa Tool <-> Entry (many-to-many)
tool_entries = db.Table('tool_entries',
    db.Column('tool_id', db.Integer, db.ForeignKey('tool.id'), primary_key=True),
    db.Column('entry_id', db.Integer, db.ForeignKey('entry.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)


class User(UserMixin, db.Model):
    """Usuario administrador"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    name = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username or self.email}>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Tool(db.Model):
    """Herramienta científica"""
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.Text)
    description_html = db.Column(db.Text)  # Descripción extendida con HTML
    url = db.Column(db.String(500))
    logo_url = db.Column(db.String(500))  # URL del logo/icono
    
    # Categorización (según # SciTools Radar Docs)
    field = db.Column(db.String(100))  # Campo disciplinar
    category = db.Column(db.String(10))  # A-P (16 categorías)
    priority_source = db.Column(db.String(50))  # De las 24 fuentes prioritarias
    tags = db.Column(db.String(500))  # Tags CSV: "AI,NLP,open-source"
    
    # Detalles adicionales
    pricing = db.Column(db.String(100))  # free, freemium, paid, open-source
    platform = db.Column(db.String(100))  # web, desktop, mobile, API
    developer = db.Column(db.String(200))  # Organización/desarrollador
    
    # Metadata
    first_seen = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active, deprecated, merged
    
    # Relaciones
    entries = db.relationship('Entry', secondary=tool_entries, back_populates='tools')
    updates = db.relationship('Update', back_populates='tool', cascade='all, delete-orphan')
    
    # Índice full-text search
    __table_args__ = (
        db.Index('idx_tool_search', 'name', 'summary', postgresql_using='gin',
                 postgresql_ops={'name': 'gin_trgm_ops', 'summary': 'gin_trgm_ops'}),
    )
    
    def __repr__(self):
        return f'<Tool {self.slug}>'


class Entry(db.Model):
    """Entrada del blog (diaria)"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True, index=True)
    editorial = db.Column(db.Text, nullable=False)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(50), default='agent')  # agent|manual
    status = db.Column(db.String(20), default='published')  # draft|approved|published
    
    # Relaciones
    tools = db.relationship('Tool', secondary=tool_entries, back_populates='entries')
    updates = db.relationship('Update', back_populates='entry', cascade='all, delete-orphan')
    agent_run = db.relationship('AgentRun', back_populates='entry', uselist=False)
    
    def __repr__(self):
        return f'<Entry {self.date}>'


class Update(db.Model):
    """Actualización de herramienta existente"""
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    
    # Qué campo se actualizó
    field_updated = db.Column(db.String(50), nullable=False)  # url, summary, category, etc.
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    description = db.Column(db.Text)  # Descripción narrativa del cambio
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    tool = db.relationship('Tool', back_populates='updates')
    entry = db.relationship('Entry', back_populates='updates')
    
    def __repr__(self):
        return f'<Update tool={self.tool_id} field={self.field_updated}>'


class AgentRun(db.Model):
    """Registro de ejecución del agente"""
    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='running')  # running|success|failed
    
    # Resultado
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'))
    entry = db.relationship('Entry', back_populates='agent_run')
    
    # Métricas de calidad
    completeness = db.Column(db.Float)
    field_diversity = db.Column(db.Float)
    social_coverage = db.Column(db.Float)
    hallucination_risk = db.Column(db.Float)
    
    # Stats
    tools_found = db.Column(db.Integer, default=0)
    tools_new = db.Column(db.Integer, default=0)
    updates_count = db.Column(db.Integer, default=0)
    
    # Costos
    total_tokens = db.Column(db.Integer)
    total_cost_usd = db.Column(db.Float)
    models_used = db.Column(db.JSON)  # {"research": "claude-sonnet-4-20250514", ...}
    
    # Error si falló
    error = db.Column(db.Text)
    
    def __repr__(self):
        return f'<AgentRun {self.id} status={self.status}>'
    
    @property
    def duration_seconds(self):
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
