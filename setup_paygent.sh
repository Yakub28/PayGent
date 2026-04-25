#!/bin/bash

echo "🚀 Initializing PayGent: The Agent Economy Setup..."

# Clean up any previous failed attempts
rm -rf venv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install the verified dependencies
# lexe-sdk: Lightning Network Wallet
# fastapi & uvicorn: API Layer
# requests: For agent HTTP calls
# langchain: For agent tooling
# python-dotenv: Environment management
pip install lexe-sdk fastapi uvicorn requests langchain python-dotenv

echo "-----------------------------------------------"
echo "✅ PayGent setup complete!"
echo "👉 RUN THIS NOW: source venv/bin/activate"
echo "-----------------------------------------------"