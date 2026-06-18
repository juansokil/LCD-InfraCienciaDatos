FROM apache/airflow:3.1.5

USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

USER root
COPY init-airflow.sh /init-airflow.sh
RUN chmod +x /init-airflow.sh

USER airflow
ENTRYPOINT ["/init-airflow.sh"]