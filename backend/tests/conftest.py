import sys
from pathlib import Path

# Mirror how the API resolves imports: pipeline modules are flat, not a package.
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "pipeline"))
sys.path.insert(0, str(BACKEND / "api"))
