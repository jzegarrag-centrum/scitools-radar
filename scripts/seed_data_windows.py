"""
Script para migrar datos del HTML original a la base de datos
"""
import os
import sys
import re
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import Tool, Entry, User
from werkzeug.security import generate_password_hash

try:
    import demjson3
    HAS_DEMJSON = True
except ImportError:
    HAS_DEMJSON = False


def extract_data_from_html(html_path):
    """Extrae el objeto DATA del archivo HTML"""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Buscar: const DATA = { ... };
    pattern = r'const DATA\s*=\s*(\{[\s\S]*?\n\};)'
    match = re.search(pattern, content)
    
    if not match:
        raise ValueError("No se encontro 'const DATA = {...}' en el HTML")
    
    data_js = match.group(1).rstrip(';').strip()
    
    # Usar demjson para parsear JavaScript directamente
    if HAS_DEMJSON:
        data = demjson3.decode(data_js)
    else:
        raise ImportError("Se requiere demjson3. Instalar con: pip install demjson3")
    
    # La estructura del HTML es DATA.entries (array de entradas)
    # Cada entrada tiene tools (array de herramientas)
    # Necesitamos convertir a: {tools: [...], entries: [...]}
    
    result = {
        'tools': [],
        'entries': []
    }
    
    # Map para evitar duplicados
    tools_by_id = {}
    
    for entry_data in data.get('entries', []):
        # Agregar herramientas únicas
        for tool in entry_data.get('tools', []):
            tool_id = tool.get('id')
            if tool_id and tool_id not in tools_by_id:
                tools_by_id[tool_id] = {
                    'slug': tool_id,
                    'name': tool.get('name', ''),
                    'summary': tool.get('summary', ''),
                    'url': tool.get('url', ''),
                    'field': tool.get('field', ''),
                    'category': tool.get('type', ''),
                    'prioritySource': 'manual'
                }
        
        # Crear entrada simplificada
        result['entries'].append({
            'fecha': entry_data.get('date'),
            'editorial': entry_data.get('editorial', ''),
            'herramientas': [t.get('id') for t in entry_data.get('tools', []) if t.get('id')]
        })
    
    # Convertir dict a array
    result['tools'] = list(tools_by_id.values())
    
    return result


def seed_database(data):
    """Popula la base de datos con los datos extraídos"""
    app = create_app('development')
    
    with app.app_context():
        print("[INFO] Limpiando base de datos...")
        db.drop_all()
        db.create_all()
        
        print("[INFO] Creando usuario admin...")
        admin = User(
            email=app.config['ADMIN_EMAIL'],
            is_admin=True
        )
        admin.set_password(app.config['ADMIN_PASSWORD'])
        db.session.add(admin)
        db.session.commit()
        print(f"   OK - Admin creado: {admin.email}")
        
        print(f"\n[INFO] Insertando {len(data.get('tools', []))} herramientas...")
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
        print(f"   OK - {len(tools_by_slug)} herramientas insertadas")
        
        print(f"\n[INFO] Insertando {len(data.get('entries', []))} entradas...")
        
        for entry_data in data.get('entries', []):
            # Parsear fecha
            fecha_str = entry_data['fecha']
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            
            entry = Entry(
                date=fecha,
                editorial=entry_data.get('editorial', ''),
                created_by='manual'
            )
            
            # Asociar herramientas a la entrada
            tool_slugs = entry_data.get('herramientas', [])
            for slug in tool_slugs:
                if slug in tools_by_slug:
                    entry.tools.append(tools_by_slug[slug])
            
            db.session.add(entry)
        
        db.session.commit()
        
        print("\n[SUCCESS] Seed completado exitosamente!")
        print(f"   - {len(tools_by_slug)} herramientas insertadas")
        print(f"   - {len(data.get('entries', []))} entradas insertadas")
        
        print(f"\n[INFO] Admin login:")
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
