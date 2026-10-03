import os

from sqlalchemy import create_engine

# Example: mysql+pymysql://user:password@localhost:3306/ip_inventory
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/ip_inventory",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
