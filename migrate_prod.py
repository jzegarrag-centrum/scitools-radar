"""Apply migration to Railway PostgreSQL"""
import os
import time
from sqlalchemy import create_engine, text

db_url = os.environ.get('DATABASE_URL')
if not db_url:
    raise RuntimeError("Set DATABASE_URL env var")

# Add sslmode if not present
if 'sslmode' not in db_url:
    sep = '&' if '?' in db_url else '?'
    db_url += f'{sep}sslmode=require'

engine = create_engine(db_url, connect_args={"connect_timeout": 30})

for attempt in range(3):
    try:
        with engine.connect() as conn:
            r = conn.execute(text('SELECT version_num FROM alembic_version'))
            current = r.fetchone()[0]
            print(f"Current version: {current}")
            
            conn.execute(text('ALTER TABLE entry ADD COLUMN IF NOT EXISTS cover_image_url VARCHAR(1000)'))
            print("Added cover_image_url column")
            
            conn.execute(text("UPDATE alembic_version SET version_num = '5fe879277811'"))
            print("Updated alembic version to 5fe879277811")
            
            # Backfill logos
            result = conn.execute(text("""
                SELECT id, url FROM tool 
                WHERE url IS NOT NULL AND logo_url IS NULL AND status = 'active'
            """))
            rows = result.fetchall()
            print(f"Tools needing logos: {len(rows)}")
            
            for tool_id, url in rows:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    domain = parsed.netloc or parsed.path.split('/')[0]
                    if domain:
                        logo = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
                        conn.execute(
                            text("UPDATE tool SET logo_url = :logo WHERE id = :id"),
                            {"logo": logo, "id": tool_id}
                        )
                except Exception as e:
                    print(f"  Failed for tool {tool_id}: {e}")
            
            conn.commit()
            print("All done!")
            break
    except Exception as e:
        print(f"Attempt {attempt+1} failed: {e}")
        if attempt < 2:
            print("Retrying in 10s...")
            time.sleep(10)
        else:
            raise
