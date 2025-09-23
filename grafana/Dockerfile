FROM python:3.9-slim

WORKDIR /app


# Instala dependências do sistema necessárias para psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*










# Copia o frontend para imports funcionarem
COPY frontend ./frontend

# Copia scripts do Grafana
COPY grafana/create_service_account.py ./grafana/
COPY grafana/create_dashboard.py ./grafana/
COPY grafana/grafana_api_key.txt ./grafana/

COPY grafana/port_manager.py ./grafana/
COPY grafana/database_manager.py ./grafana/
COPY grafana/streaming.py ./grafana/
COPY grafana/vessel.py ./grafana/
 



 

# Copia requirements e instala dependências
COPY frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Define PYTHONPATH para reconhecer 'app'
ENV PYTHONPATH=/app

# Executa com output unbuffered para ver logs em tempo real
CMD ["python", "-u", "./grafana/create_dashboard.py"]