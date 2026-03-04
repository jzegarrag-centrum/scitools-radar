import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import create_app, db
    from app.models import Tool, Entry

    app = create_app('development')
    with app.app_context():
        tool_count = Tool.query.count()
        entry_count = Entry.query.count()
        
        print(f'Tools: {tool_count}')
        print(f'Entries: {entry_count}')
        
        if tool_count > 0:
            print('\nPrimeras 5 herramientas:')
            tools = Tool.query.limit(5).all()
            for t in tools:
                print(f'  - {t.name} ({t.slug})')
        
        if entry_count > 0:
            print('\nPrimeras 3 entradas:')
            entries = Entry.query.order_by(Entry.date.desc()).limit(3).all()
            for e in entries:
                print(f'  - {e.date}: {len(e.tools)} herramientas')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
