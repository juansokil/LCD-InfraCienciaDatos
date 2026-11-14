# Imagen de Airflow del TP: la oficial 3.1.5 + nuestras dependencias
FROM apache/airflow:3.1.5-python3.11

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Contrasena del login de la UI (admin / admin) y script de arranque.
# --chown: Airflow abre passwords.json para escribir; si queda de root, no arranca.
COPY --chown=airflow:root airflow/passwords.json /opt/airflow/passwords.json
COPY airflow/init-airflow.sh /opt/airflow/init-airflow.sh

CMD ["bash", "/opt/airflow/init-airflow.sh"]
