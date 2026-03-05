#!/usr/bin/env python
"""Railway startup: run migrations then start gunicorn"""
import os


def run_migrations():
    """Run Alembic migrations before starting the server"""
    try:
        from app import create_app
        from flask_migrate import upgrade
        
        app = create_app()
        with app.app_context():
            upgrade()
            print("✓ Migrations applied successfully")
    except Exception as e:
        print(f"⚠ Migration via Alembic failed: {e}")
        # Fallback: ensure critical columns exist via raw SQL
        try:
            from app import create_app, db
            from sqlalchemy import text
            app = create_app()
            with app.app_context():
                with db.engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE entry ADD COLUMN IF NOT EXISTS cover_image_url VARCHAR(1000)"
                    ))
                    conn.commit()
                    print("✓ Fallback: cover_image_url column ensured")
        except Exception as e2:
            print(f"⚠ Fallback column creation also failed: {e2}")

if __name__ == '__main__':
    run_migrations()
    
    port = os.environ.get('PORT', '5000')
    cmd = f"gunicorn wsgi:app --bind 0.0.0.0:{port} --workers 1 --timeout 120"
    print(f"Starting: {cmd}")
    os.execvp('gunicorn', ['gunicorn', 'wsgi:app', '--bind', f'0.0.0.0:{port}', '--workers', '1', '--timeout', '120'])
