"""
Script para migrar datos del HTML original a PostgreSQL
"""
import os
import sys
import json
import re
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import Tool, Entry, User
from werkzeug.security import generate_password_hash


def extract_data_from_html(html_path):
    """Extrae el objeto DATA del archivo HTML"""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Buscar: const DATA = { ... };
    pattern = r'const DATA\s*=\s*(\{[\s\S]*?\});'
    match = re.search(pattern, content)
    
    if not match:
        raise ValueError("No se encontró 'const DATA = {...}' en el HTML")
    
    data_js = match.group(1)
    
    # Convertir JS a JSON (remover trailing commas, etc.)
    # Esto es simplificado - en producción usar un parser JS real
    data_json = re.sub(r',(\s*[}\]])', r'\1', data_js)  # Remove trailing commas
    
    data = json.loads(data_json)
    
    return data


def seed_database(data):
    """
    Seed la base de datos con datos del HTML
    
    Args:
        data: Dict con keys: entries, tools, updates
    """
    app = create_app('development')
    
    with app.app_context():
        print("🗑️  Limpiando base de datos...")
        db.drop_all()
        db.create_all()
        
        print("👤 Creando usuario admin...")
        admin = User(
            email=app.config['ADMIN_EMAIL'],
            name='Administrador',
            is_admin=True,
            created_at=datetime.utcnow()
        )
        admin.set_password(app.config['ADMIN_PASSWORD'])
        db.session.add(admin)
        db.session.commit()
        print(f"   ✓ Admin creado: {admin.email}")
        
        print(f"\n📦 Insertando {len(data.get('tools', []))} herramientas...")
        tools_by_slug = {}
        
        for tool_data in data.get('tools', []):
            tool = Tool(
                slug=tool_data['slug'],
                name=tool_data['name'],
                summary=tool_data.get('summary', ''),
                url=tool_data.get('url', ''),
                field=tool_data.get('field', ''),
                category=tool_data.get('category', ''),
                priority_source=tool_data.get('prioritySource', ''),
                first_seen=datetime.utcnow(),
                status='active'
            )
            db.session.add(tool)
            tools_by_slug[tool.slug] = tool
        
        db.session.commit()
        print(f"   ✓ {len(tools_by_slug)} herramientas insertadas")
        
        print(f"\n📝 Insertando {len(data.get('entries', []))} entradas...")
        
        for entry_data in data.get('entries', []):
            try:
                entry_date = datetime.strptime(entry_data['date'], '%Y-%m-%d').date()
            except:
                print(f"   ⚠️  Fecha inválida: {entry_data.get('date')} - skipping")
                continue
            
            entry = Entry(
                date=entry_date,
                editorial=entry_data.get('editorial', ''),
                created_by='seed',
                created_at=datetime.utcnow()
            )
            
            # Asociar tools
            for tool_slug in entry_data.get('tools', []):
                if tool_slug in tools_by_slug:
                    entry.tools.append(tools_by_slug[tool_slug])
                else:
                    print(f"   ⚠️  Tool no encontrada: {tool_slug}")
            
            db.session.add(entry)
        
        db.session.commit()
        print(f"   ✓ Entradas insertadas")
        
        print("\n✅ Seed completo!")
        print(f"   - Tools: {Tool.query.count()}")
        print(f"   - Entries: {Entry.query.count()}")
        print(f"   - Users: {User.query.count()}")
        print(f"\n🔑 Admin login:")
        print(f"   Email: {app.config['ADMIN_EMAIL']}")
        print(f"   Password: {app.config['ADMIN_PASSWORD']}")


if __name__ == '__main__':
    # Path al HTML original
    html_path = os.path.join(
        os.path.dirname(__file__),
        '..',
        '..',
        'scitools_blog.html'
    )
    
    if not os.path.exists(html_path):
        print(f"[ERROR] No se encontro {html_path}")
        print("   Por favor ajusta el path en el script")
        sys.exit(1)
    
    print("[INFO] Leyendo datos del HTML...")
    try:
        data = extract_data_from_html(html_path)
        print(f"   OK - Datos extraidos: {len(data.get('tools', []))} tools, "
              f"{len(data.get('entries', []))} entries")
    except Exception as e:
        print(f"[ERROR] Error al leer HTML: {e}")
        sys.exit(1)
    
    print("\n[INFO] Iniciando seed...")
    seed_database(data)
