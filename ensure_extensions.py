"""
Crea extensiones PostgreSQL requeridas ANTES de las migraciones.
Necesario para el índice GIN con gin_trgm_ops en Tool.
"""
import os
import sys


def main():
    db_url = os.environ.get('DATABASE_URL', '')

    # Solo aplica a PostgreSQL
    if 'postgresql' not in db_url and 'postgres' not in db_url:
        print('[extensions] No es PostgreSQL — omitido.')
        return

    # Railway usa postgres:// pero SQLAlchemy requiere postgresql://
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.commit()
        print('[extensions] ✓ pg_trgm extension OK')

    engine.dispose()


if __name__ == '__main__':
    main()
