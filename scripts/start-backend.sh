#!/bin/bash

# RUTE Backend Start Script

echo "🐍 Starting RUTE Backend Server..."

cd backend

# Check if virtual environment exists
if [ ! -d "venv" ]; then
  echo "📦 Creating virtual environment..."
  python -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
  source venv/Scripts/activate
else
  source venv/bin/activate
fi

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Start the server
echo "🚀 Starting FastAPI server..."
echo "API will be available at: http://localhost:8000"
echo "API docs available at: http://localhost:8000/docs"
echo ""

python -m uvicorn main:app --reload
