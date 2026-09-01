"""
Pytest configuration for backend tests.

* Adds the backend directory to ``sys.path`` so tests can import the
  ``app.*`` packages at the project root.
* Sets placeholder environment variables so modules that import
  ``app.config`` at collection time don't error out in local CI runs that
  don't have real Supabase credentials wired up.
"""
import os
import sys

# Add backend directory to path so `from app...` imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Defaults so ``app.config`` can be imported without real secrets. Tests
# that actually hit Supabase (today: none - they use fake clients) would
# need to override these in their own fixture.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "test-publishable-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("GEMINI_API_KEY", "")
