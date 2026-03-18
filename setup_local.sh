#!/bin/bash

echo "========================================="
echo "Simple Memory API - Local Setup"
echo "========================================="
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

echo "✓ Python 3 found"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create directories
echo ""
echo "Creating directories..."
mkdir -p db models logs

# Initialize database
echo ""
echo "Initializing database..."
python3 -c "from simple_db import SimpleMemoryDB; SimpleMemoryDB('db/memories.db')"

# Generate encryption key if .env doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Generating encryption key..."
    python3 -c "from encryption import generate_encryption_key; print('ENCRYPTION_KEY=' + generate_encryption_key())" > .env
    echo "✓ Encryption key saved to .env"
    echo ""
    echo "⚠️  IMPORTANT: Backup your .env file!"
    echo "   Without it, encrypted data cannot be recovered."
fi

echo ""
echo "========================================="
echo "✓ Setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the API server:"
echo "   source venv/bin/activate"
echo "   python3 app_local.py"
echo ""
echo "2. Create an API key (in another terminal):"
echo "   curl -X POST http://localhost:8000/api-keys \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"user_id\": \"your-email@example.com\"}'"
echo ""
echo "3. (Optional) Install Ollama for AI features:"
echo "   https://ollama.com/download"
echo "   ollama pull llama3.1:8b-instruct-fp16"
echo ""
echo "4. View API docs:"
echo "   http://localhost:8000/docs"
echo ""
echo "⚠️  Remember to backup .env file (contains encryption key)!"
echo ""
