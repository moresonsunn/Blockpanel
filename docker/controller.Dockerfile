# --- Build frontend ---
FROM node:20-alpine AS ui
WORKDIR /ui

# Install dependencies first for better caching
COPY frontend/package.json ./
RUN npm install --silent

# Copy frontend source
COPY frontend ./

# Build React app
RUN npm run build

# --- Backend image ---
FROM python:3.11-slim AS api
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend ./

# Copy built frontend
COPY --from=ui /ui/build ./static

# Create data directory
RUN mkdir -p /data/servers

ENV PORT=8000
EXPOSE 8000

# Use Python module syntax for better reliability
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
    