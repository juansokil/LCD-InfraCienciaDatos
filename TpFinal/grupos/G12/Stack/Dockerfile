FROM apache/airflow:3.1.5

# Cambiamos a root para instalar dependencias del sistema si hiciera falta (ej. git)
USER root
RUN apt-get update && apt-get install -y git

# Volvemos al usuario de airflow e instalamos las librerías de Python
USER airflow
RUN pip install --no-cache-dir pandas requests sqlalchemy python-dotenv psycopg2-binary