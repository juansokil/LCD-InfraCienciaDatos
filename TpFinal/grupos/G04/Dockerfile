FROM apache/airflow:3.1.5 AS airflow

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir -r /requirements.txt


FROM python:3.11-slim AS dashboard

WORKDIR /opt/airflow/project

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir -r /requirements.txt