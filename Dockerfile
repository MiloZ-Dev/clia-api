# Base image
FROM python:3.11-slim

# Avoid .pyc files and enable unbuffered stdout for clean container logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY . .

# Default command runs the API; the scheduler service overrides this.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
