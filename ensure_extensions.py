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

        # Ensure column widths are sufficient (safety net for migrations)
        cols = conn.execute(text(
            "SELECT column_name, data_type, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_name = 'tool' AND column_name IN ('pricing','platform','developer') "
            "ORDER BY column_name"
        )).fetchall()

        for col_name, dtype, max_len in cols:
            if col_name == 'pricing' and dtype != 'text':
                conn.execute(text("ALTER TABLE tool ALTER COLUMN pricing TYPE TEXT"))
                print(f'[extensions] ✓ pricing widened to TEXT')
            if col_name == 'platform' and max_len and max_len < 500:
                conn.execute(text("ALTER TABLE tool ALTER COLUMN platform TYPE VARCHAR(500)"))
                print(f'[extensions] ✓ platform widened to VARCHAR(500)')
            if col_name == 'developer' and max_len and max_len < 500:
                conn.execute(text("ALTER TABLE tool ALTER COLUMN developer TYPE VARCHAR(500)"))
                print(f'[extensions] ✓ developer widened to VARCHAR(500)')

        conn.commit()

    engine.dispose()


if __name__ == '__main__':
    main()
