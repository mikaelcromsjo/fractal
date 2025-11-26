FROM python:3.11-slim

WORKDIR /app

# System dependencies for asyncpg
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt /app/

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy ONLY the app folder
COPY app/ /app/

# Use /app for all imports
ENV PYTHONPATH=/app

# Run FastAPI in development mode
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030", "--reload"]
