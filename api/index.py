import sys
import os

# Add the root directory to sys.path so we can import main.py and other modules
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Ensure the working directory is the root so relative paths (like mock_lightning.json) work
os.chdir(root_dir)

from main import app

# Vercel's Python runtime expects 'app' at the module level
# or it will look for a variable named 'handler'
app = app
