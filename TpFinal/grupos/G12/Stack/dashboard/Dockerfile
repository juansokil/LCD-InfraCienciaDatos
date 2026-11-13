FROM python:3.11-slim

WORKDIR /app

# Primero las dependencias (versiones fijas en requirements.txt), asi Docker
# reusa esta capa mientras no cambien.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Despues el codigo. pages/ ademas se monta en vivo desde docker-compose.yml.
COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
