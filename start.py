#!/usr/bin/env python
"""Railway startup: run migrations then start gunicorn"""
import os
import sys
import subprocess


if __name__ == '__main__':
    # The schema guarantee is now in create_app() -> _ensure_schema()
    # Just start gunicorn directly
    port = os.environ.get('PORT', '5000')
    args = [
        sys.executable, '-m', 'gunicorn',
        'wsgi:app',
        '--bind', f'0.0.0.0:{port}',
        '--workers', '1',
        '--timeout', '120',
    ]
    print(f"Starting gunicorn on port {port}")
    sys.exit(subprocess.call(args))
