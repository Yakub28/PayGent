import os
import sys

# Add the project root to the path
path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, path)

from main import app

# Vercel's Python runtime expects 'app' or 'handler'
app = app
