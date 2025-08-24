# --- Build frontend ---
    FROM node:20-alpine AS ui
    WORKDIR /ui
    
    # WICHTIG: Dev-Dependencies wie react-scripts müssen installiert werden
    ENV NODE_ENV=development
    
    # Package.json + lockfile zuerst kopieren (Cache layer)
    COPY frontend/package.json frontend/package-lock.json ./
    
    # Installiere alles inkl. devDependencies
    RUN npm install --no-audit --no-fund
    
    # Restliches Frontend kopieren
    COPY frontend ./ 
    
    # Build React App
    RUN npm run build
    
    # --- Backend image ---
    FROM python:3.11-slim AS api
    WORKDIR /app
    
    # System deps
    RUN apt-get update && apt-get install -y --no-install-recommends curl \
      && rm -rf /var/lib/apt/lists/*
    
    COPY backend/requirements.txt ./
    RUN pip install --no-cache-dir -r requirements.txt
    COPY backend ./
    
    # Copy built frontend into backend container
    COPY --from=ui /ui/build ./static
    
    ENV PORT=8000
    EXPOSE 8000
    
    CMD ["sh", "-lc", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
    