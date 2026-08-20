#!/bin/bash

# RUTE Build Script

echo "🚀 Building RUTE Trading Assistant..."

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
  echo "📦 Installing dependencies..."
  npm install
fi

# Build the extension
echo "🔨 Building extension..."
npm run build

# Copy manifest and assets to dist
echo "📋 Copying manifest..."
cp public/manifest.json dist/

# Create icons directory in dist if it doesn't exist
mkdir -p dist/icons

# Copy icons if they exist
if [ -d "public/icons" ]; then
  echo "🎨 Copying icons..."
  cp -r public/icons/* dist/icons/ 2>/dev/null || echo "⚠️  No icons found - extension will use default icon"
else
  echo "⚠️  No icons directory found - create icons in public/icons/"
fi

echo "✅ Build complete! Extension is ready in dist/ folder"
echo ""
echo "Next steps:"
echo "1. Open Chrome and go to chrome://extensions/"
echo "2. Enable 'Developer mode'"
echo "3. Click 'Load unpacked'"
echo "4. Select the 'dist' folder"
echo ""
echo "Don't forget to start the backend:"
echo "  cd backend && python -m uvicorn main:app --reload"
