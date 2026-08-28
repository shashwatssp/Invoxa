"""
Pytest configuration for backend tests.
Adds the backend directory to sys.path so tests can import app.* modules.
"""
import sys
import os

# Add backend directory to path so `from app...` imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
