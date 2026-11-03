FROM python:3.11-slim

# Dépendances système pour WeasyPrint et psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libssl-dev \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copie et installation des dépendances Python
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY backend/ .

# Répertoires de données
RUN mkdir -p /app/media /app/staticfiles /app/data

# Utilisateur non-root
RUN addgroup --system app && adduser --system --group app
RUN chown -R app:app /app
USER app

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
