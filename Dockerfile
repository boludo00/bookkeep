# Multi-stage build for single-container deployment
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Copy only dependency files first for better layer caching
COPY package*.json ./

# Install dependencies (this layer will be cached unless package.json changes)
# Use BuildKit cache mount for npm cache (faster subsequent builds)
RUN --mount=type=cache,target=/root/.npm \
    npm ci --legacy-peer-deps || npm install --legacy-peer-deps

# Copy config files needed for build
COPY vite.config.ts tsconfig*.json ./
COPY tailwind.config.ts postcss.config.js ./
COPY index.html ./

# Copy source files (these change frequently, so copy after dependencies)
COPY src ./src
COPY public ./public

# Build frontend in production mode
ENV NODE_ENV=production
RUN npm run build

# Backend stage
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy backend dependency files
COPY backend/pyproject.toml backend/requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# Copy backend code (including Alembic migrations)
COPY backend ./backend

# Copy built frontend from builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend_dist

# Create data directory for SQLite
RUN mkdir -p /app/data

# Copy and make entrypoint script executable
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Set PYTHONPATH to include backend directory so imports work correctly
ENV PYTHONPATH="/app/backend:$PYTHONPATH"

# Expose port
EXPOSE 8000

# Use entrypoint script to run migrations then start the app
ENTRYPOINT ["/app/entrypoint.sh"]

