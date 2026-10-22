"""Launch the organism or the integrated spectator server from a stable entry point."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aethel_pkg.main import main

if __name__ == "__main__":
    main()
