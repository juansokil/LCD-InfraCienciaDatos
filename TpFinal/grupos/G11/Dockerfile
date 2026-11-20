# Imagen de Airflow del grupo: la oficial 3.1.5 + nuestras dependencias.
FROM apache/airflow:3.1.5-python3.11

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chmod=755 init-airflow.sh /opt/airflow/init-airflow.sh

ENTRYPOINT []
CMD ["bash", "/opt/airflow/init-airflow.sh"]
