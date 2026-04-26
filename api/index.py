import sys
import os

# Add the parent directory to sys.path so we can import main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

# Vercel needs the app object to be named 'app' or 'handler'
handler = app
