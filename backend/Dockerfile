FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including curl for uv installation
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv using the official installer
# The installer requires curl (and certificates) to download the release archive
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

# Download the latest installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin:$PATH"

# Verify uv installation and Python version
RUN uv --version && python --version && which python

# Copy dependency files for better caching
COPY pyproject.toml requirements.txt ./

# Install dependencies directly to system Python (no virtual environment needed in Docker)
# This ensures email-validator from pydantic[email] is installed
RUN uv pip install --system --no-cache -r requirements.txt

# Verify email-validator is installed and check Python path
RUN python -c "import email_validator; print('email-validator version:', email_validator.__version__)" && \
    python -c "import sys; print('Python executable:', sys.executable)" && \
    python -c "import sys; print('Python path:', sys.path)"

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application using python -m to ensure we use the correct Python interpreter
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

