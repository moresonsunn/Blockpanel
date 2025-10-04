# --- Build frontend ---
FROM node:20-alpine AS ui
WORKDIR /ui

# Install dependencies first for better caching
ENV NODE_ENV=production
COPY frontend/package*.json ./
# Prefer npm ci when lockfile is present; fall back to npm install
RUN if [ -f package-lock.json ]; then npm ci --omit=dev --silent; else npm install --omit=dev --silent; fi

# Copy frontend source
COPY frontend ./

# Build React app
RUN npm run build

# --- Backend image ---
FROM python:3.11-slim AS api
WORKDIR /app
# --- Build metadata injection ---
# Accept build-time args (in CI we pass tag or short SHA + commit hash)
ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown

# OCI standard labels for better provenance in registries
LABEL org.opencontainers.image.title="BlockPanel Controller" \
    org.opencontainers.image.description="BlockPanel (Minecraft server controller) - backend API + bundled static frontend" \
    org.opencontainers.image.version=$APP_VERSION \
    org.opencontainers.image.revision=$GIT_COMMIT \
    org.opencontainers.image.source="https://github.com/moresonsun/Minecraft-Controller" \
    org.opencontainers.image.licenses="MIT"

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
ENV APP_VERSION=$APP_VERSION \
    GIT_COMMIT=$GIT_COMMIT \
    PORT=8000
EXPOSE 8000

# Use Python module syntax for better reliability
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
    