"""
Vercel Serverless Function Entry Point for FarmLink AI Backend
"""
import sys
import os

# Add the server directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

from app import app

# Vercel serverless handler
app = app
