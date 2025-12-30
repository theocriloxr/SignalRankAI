#!/bin/bash
# Deployment script for SignalRankAI

# Activate virtual environment (if any)
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Export environment variables
export $(grep -v '^#' .env | xargs)

# Start the bot
python -m telegram.bot &

# Start the main engine
python main.py &

# Start Flask API (if needed)
# python api.py &

wait
