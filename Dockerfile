# Multi-stage build: compile the React/Vite frontend, then serve it from the
# same FastAPI process that serves the API - matches how run.bat works locally
# (one process, one port), just containerized.

FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS backend
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# main.py resolves the frontend build three directories up from itself
# (backend/app/main.py -> backend/app -> backend -> /app), so it must land at
# /app/frontend/dist to match what FRONTEND_DIST computes at runtime.
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
