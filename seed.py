"""
Seed script — Carga datos iniciales en la base de datos.
Uso: python seed.py
En Railway: python seed.py (desde el shell del servicio)
"""
import json
import os
import sys
from datetime import date, datetime
from werkzeug.security import generate_password_hash

# Asegurar que podemos importar la app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Tool, Entry, User


def seed():
    """Carga tools, entries y admin user desde seed_data.json"""
    
    data_file = os.path.join(os.path.dirname(__file__), 'seed_data.json')
    
    if not os.path.exists(data_file):
        print("ERROR: seed_data.json not found")
        sys.exit(1)
    
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # --- Admin User ---
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@smartcentrum.edu.pe')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin1234')
    
    existing_user = User.query.filter_by(username=admin_username).first()
    if not existing_user:
        user = User(
            username=admin_username,
            email=admin_email,
            password_hash=generate_password_hash(admin_password)
        )
        db.session.add(user)
        print(f"  + Admin user: {admin_username}")
    else:
        print(f"  = Admin user already exists: {admin_username}")
    
    # --- Tools ---
    tools_created = 0
    tools_skipped = 0
    slug_to_tool = {}
    
    for t in data['tools']:
        existing = Tool.query.filter_by(slug=t['slug']).first()
        if existing:
            slug_to_tool[t['slug']] = existing
            tools_skipped += 1
            continue
        
        tool = Tool(
            slug=t['slug'],
            name=t['name'],
            summary=t.get('summary'),
            description_html=t.get('description_html'),
            url=t.get('url'),
            logo_url=t.get('logo_url'),
            field=t.get('field'),
            category=t.get('category'),
            priority_source=t.get('priority_source'),
            tags=t.get('tags'),
            pricing=t.get('pricing'),
            platform=t.get('platform'),
            developer=t.get('developer'),
            first_seen=date.fromisoformat(t['first_seen']) if t.get('first_seen') else None,
            last_updated=date.fromisoformat(t['last_updated']) if t.get('last_updated') else None,
            status=t.get('status', 'active'),
        )
        db.session.add(tool)
        slug_to_tool[t['slug']] = tool
        tools_created += 1
    
    db.session.flush()  # Get IDs for relationships
    print(f"  + Tools created: {tools_created}, skipped: {tools_skipped}")
    
    # --- Entries ---
    entries_created = 0
    entries_skipped = 0
    
    for e in data['entries']:
        entry_date = date.fromisoformat(e['date'])
        existing = Entry.query.filter_by(date=entry_date).first()
        if existing:
            entries_skipped += 1
            continue
        
        entry = Entry(
            date=entry_date,
            editorial=e.get('editorial'),
            status=e.get('status', 'published'),
            created_by=e.get('created_by', 'seed'),
        )
        
        # Associate tools
        for slug in e.get('tool_slugs', []):
            tool = slug_to_tool.get(slug)
            if not tool:
                tool = Tool.query.filter_by(slug=slug).first()
            if tool:
                entry.tools.append(tool)
        
        db.session.add(entry)
        entries_created += 1
    
    print(f"  + Entries created: {entries_created}, skipped: {entries_skipped}")
    
    # Commit
    db.session.commit()
    print("\n  Seed complete!")


if __name__ == '__main__':
    config_name = os.environ.get('FLASK_ENV', 'production')
    app = create_app(config_name)
    
    with app.app_context():
        print(f"\nSeeding database ({config_name})...")
        print(f"DB: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
        seed()
