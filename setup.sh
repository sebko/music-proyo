#!/bin/bash
# Music Library Genre Tagger - Setup Script
# Similar to "npm install" for this Python project

set -e  # Exit on any error

echo "🎵 Music Library Genre Tagger - Setup"
echo "======================================"

# Check if we're in a virtual environment
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✅ Virtual environment detected: $VIRTUAL_ENV"
else
    echo "⚠️  Warning: No virtual environment detected"
    echo "   Consider running: python3 -m venv venv && source venv/bin/activate"
    echo "   Continuing with system Python..."
fi

echo ""
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "🧹 Cleaning up any Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

echo ""
echo "🔧 Setting up configuration files..."

# Create API config if it doesn't exist
if [ ! -f "api_config.json" ]; then
    echo "Creating default api_config.json..."
    cat > api_config.json << 'EOF'
{
    "spotify": {
        "client_id": "YOUR_SPOTIFY_CLIENT_ID",
        "client_secret": "YOUR_SPOTIFY_CLIENT_SECRET"
    },
    "musicbrainz": {
        "user_agent": "music-genre-tagger/1.0"
    },
    "lastfm": {
        "api_key": "YOUR_LASTFM_API_KEY"
    }
}
EOF
    echo "⚠️  Please edit api_config.json with your API credentials"
fi

# Create tagger config if it doesn't exist  
if [ ! -f "tagger_config.json" ]; then
    echo "Creating default tagger_config.json..."
    cat > tagger_config.json << 'EOF'
{
    "confidence_thresholds": {
        "high_confidence": 95.0,
        "review_threshold": 70.0,
        "skip_threshold": 40.0
    },
    "genre_limits": {
        "max_genres_per_album": 5,
        "min_genre_confidence": 60.0
    },
    "processing": {
        "batch_size": 50,
        "api_rate_limit_delay": 0.1
    }
}
EOF
    echo "✅ Created default tagger_config.json"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 Quick start commands:"
echo "   python3 music_dashboard.py --interactive    # Start web interface with detailed logging"
echo "   python3 music_dashboard.py --help           # See all available options"
echo "   python3 batch_processor.py                  # Run batch genre processing"
echo ""
echo "📊 Web interface will be available at: http://localhost:5002"
echo "💡 Use --interactive mode to see detailed startup progress and debug any issues"