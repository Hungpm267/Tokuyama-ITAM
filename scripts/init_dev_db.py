import psycopg
import subprocess

with psycopg.connect("postgresql://postgres@127.0.0.1:5432/postgres", autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname='itam_dev'")
        if not cur.fetchone():
            cur.execute("CREATE DATABASE itam_dev")
            print("Created itam_dev database!")
        else:
            print("itam_dev already exists.")

# Run alembic upgrade head on itam_dev
subprocess.run(["alembic", "upgrade", "head"], check=True)
print("Alembic upgrade head finished for itam_dev!")
