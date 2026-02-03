# Multi-stage build for single-container deployment
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Build metadata (forwarded to Vite)
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION

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

# Install system dependencies including Chromium for Cloudflare bypass
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    ca-certificates \
    # Chromium and dependencies for SeleniumBase Cloudflare bypass
    chromium \
    chromium-driver \
    # Xvfb for virtual display (enables CDP mode in Docker)
    xvfb \
    # Required libraries for Chrome/Chromium
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    # X11 libraries for Xvfb
    libxss1 \
    libxtst6 \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

# Set Chrome path for SeleniumBase
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
# Set display for Xvfb
ENV DISPLAY=:99

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
ENV PYTHONPATH="/app/backend"

# Expose port
EXPOSE 8000

# Use entrypoint script to run migrations then start the app
ENTRYPOINT ["/app/entrypoint.sh"]
