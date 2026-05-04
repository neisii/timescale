import os
import sys
from pathlib import Path

# Must be set before `import anthropic` to prevent AuthenticationError at client init
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

# Add orchestrator/ to path so all modules resolve as in production
sys.path.insert(0, str(Path(__file__).parent.parent))
