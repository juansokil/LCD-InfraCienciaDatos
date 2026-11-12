import os
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL

def get_warehouse_engine():
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
        host=os.environ["WAREHOUSE_HOST"],
        port=int(os.environ["WAREHOUSE_PORT"]),
        database=os.environ["WAREHOUSE_DB"],
    )
    return create_engine(url, pool_pre_ping=True)