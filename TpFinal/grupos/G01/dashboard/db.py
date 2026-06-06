import os
from sqlalchemy import create_engine, text

def get_engine():
    host = os.environ.get("SOURCE_DB_HOST", "localhost")
    user = os.environ.get("SOURCE_DB_USER", "weather_user")
    password = os.environ.get("SOURCE_DB_PASS", "weather_pass")
    db = os.environ.get("SOURCE_DB_NAME", "weather_dwh")
    port = 5432
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)

def test_connection():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as e:
        return False, str(e)