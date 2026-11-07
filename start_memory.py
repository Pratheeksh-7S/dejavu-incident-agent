"""Starts the local Hindsight memory server using the settings in .env"""
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()
server = os.path.join(os.path.dirname(sys.executable), "hindsight-api")
print("Starting DejaVu memory server on http://localhost:8888 ...")
subprocess.run([server])