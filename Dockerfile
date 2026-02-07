# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# git is often needed for installing dependencies from git
# curl/wget for healthchecks if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY src/ src/
COPY .agent/ .agent/
COPY docs/ docs/
COPY README.md .
COPY setup.py .

# Install the package in editable mode (or standard mode)
RUN pip install -e .

# Create a non-root user for security
RUN useradd -m appuser
USER appuser

# Define the entrypoint
ENTRYPOINT ["python", "-m", "als_finder.cli"]
CMD ["--help"]
