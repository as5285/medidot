#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Install system-level dependencies
echo "Installing system-level dependencies..."
apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libxext-dev \
    libsm-dev \
    libxrender-dev \
    libfreetype6-dev \
    libpng-dev \
    libjpeg-dev \
    zlib1g-dev

# Install dlib dependencies
echo "Installing dlib dependencies..."
apt-get install -y python3-dev python3-pip python3-opencv

# Install Python packages
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Migrate SQLite database (optional)
echo "Setting up SQLite database..."
if [ ! -f database.db ]; then
    python -c "
from app import Base, engine;
Base.metadata.create_all(bind=engine)
"
fi

echo "Setup complete. Ready to deploy on Heroku!"
