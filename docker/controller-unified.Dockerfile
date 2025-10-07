# Unified BlockPanel image: backend API + built frontend + embedded multi-Java runtime
# This eliminates the separate runtime image for single-container deployments.

FROM node:20-alpine AS ui
WORKDIR /ui
ENV NODE_ENV=production
COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev --silent; else npm install --omit=dev --silent; fi
COPY frontend ./
RUN npm run build

# Base: start from OpenJDK 21 (includes Java 21)
FROM openjdk:21-jdk-slim AS unified
WORKDIR /app

ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="BlockPanel Unified" \
      org.opencontainers.image.description="BlockPanel controller + static frontend + embedded multi-Java runtime" \
      org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.revision=$GIT_COMMIT \
      org.opencontainers.image.source="https://github.com/moresonsun/Minecraft-Controller" \
      org.opencontainers.image.licenses="MIT"

# System deps (python, build basics, curl, wget, unzip, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev gcc curl wget unzip bash ca-certificates fontconfig libfreetype6 libxi6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Multi-Java toolchain (8, 11, 17 already added manually like runtime image)
RUN wget -qO- https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u392-b08/OpenJDK8U-jdk_x64_linux_hotspot_8u392b08.tar.gz | tar -xz -C /opt/ && \
    ln -sf /opt/jdk8u392-b08/bin/java /usr/local/bin/java8 && \
    wget -qO- https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.21%2B9/OpenJDK11U-jdk_x64_linux_hotspot_11.0.21_9.tar.gz | tar -xz -C /opt/ && \
    ln -sf /opt/jdk-11.0.21+9/bin/java /usr/local/bin/java11 && \
    wget -qO- https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.9%2B9/OpenJDK17U-jdk_x64_linux_hotspot_17.0.9_9.tar.gz | tar -xz -C /opt/ && \
    ln -sf /opt/jdk-17.0.9+9/bin/java /usr/local/bin/java17 && \
    ln -sf /usr/local/openjdk-21/bin/java /usr/local/bin/java21

ENV JAVA_TOOL_OPTIONS="-Djava.awt.headless=true -Dsun.java2d.noddraw=true -Djava.net.preferIPv4Stack=true" \
    APP_VERSION=$APP_VERSION \
    GIT_COMMIT=$GIT_COMMIT

# Python dependencies (use venv to avoid Debian PEP 668 externally managed restriction)
COPY backend/requirements.txt ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:$PATH"

# Copy backend
COPY backend ./
# Copy built frontend
COPY --from=ui /ui/build ./static

# Data dirs
RUN mkdir -p /data/servers /data/sqlite
ENV PORT=8000
EXPOSE 8000 25565

# Provide an internal marker so backend can detect unified mode (optional future use)
ENV BLOCKPANEL_UNIFIED_IMAGE=1

# Uvicorn startup (same as controller base)
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
