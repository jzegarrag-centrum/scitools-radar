#!/usr/bin/env python
"""Railway startup: run migrations then start gunicorn"""
import os
import subprocess
import sys

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
        print(f"⚠ Migration warning (non-fatal): {e}")

if __name__ == '__main__':
    run_migrations()
    
    port = os.environ.get('PORT', '5000')
    cmd = f"gunicorn wsgi:app --bind 0.0.0.0:{port} --workers 1 --timeout 120"
    print(f"Starting: {cmd}")
    os.execvp('gunicorn', ['gunicorn', 'wsgi:app', '--bind', f'0.0.0.0:{port}', '--workers', '1', '--timeout', '120'])
