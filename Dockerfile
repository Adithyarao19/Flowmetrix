# Stage 1: Build dependencies
FROM python:3.10-slim as builder
WORKDIR /app
RUN pip install --no-cache-dir gunicorn
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final image
FROM python:3.10-slim
WORKDIR /app

# --- THIS IS THE FIX ---
# Install curl so the healthcheck in docker-compose.yml can work
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
# --- END FIX ---

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY flowmetrix.py .

EXPOSE 8000
CMD ["python", "-u", "flowmetrix.py"]