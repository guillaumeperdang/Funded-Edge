# Base Image
FROM python:3.9-slim

# Install System Dependencies (Chrome, curl, etc)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Chromium and Driver (System Packages - Stable on Debian 12)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*
    
# Set Environment Variables for Selenium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Set up Workspace
WORKDIR /app

# Copy Requirements and Install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy App Code
COPY . .

# Expose Port (Render uses $PORT env var, but we expose 5000 as default doc)
EXPOSE 5000

# Start Command using Gunicorn
CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 600 --workers 1
