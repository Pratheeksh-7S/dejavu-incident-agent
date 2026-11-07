import os
import sys
from pathlib import Path

# Dummy key so agent.py can build its Groq client; no network is ever used.
os.environ["GROQ_API_KEY"] = "test-dummy-key"

# Keep tests from reading the real .env file.
import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *a, **k: False

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
