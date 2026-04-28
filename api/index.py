import os
import sys

# The root directory is now the parent of the /api folder
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)

from main import app

# Vercel's Python runtime expects 'app' or 'handler'
app = app
