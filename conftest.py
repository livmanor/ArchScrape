"""
conftest.py — pytest configuration for ArchScale Intelligence tests.

Adds the project root to sys.path so imports work without installation.
"""

import pathlib
import sys

# Ensure project root is on the path
ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
