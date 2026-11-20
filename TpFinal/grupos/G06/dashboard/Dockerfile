FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py inicio.py db.py tema.py ./
COPY pages/ pages/

EXPOSE 8501
#CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]
CMD ["streamlit", "run", "inicio.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]