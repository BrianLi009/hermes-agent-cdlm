"""hermes-cdlm — isolated Hermes instance with HERMES_HOME=~/.hermes-cdlm"""

import os
from pathlib import Path


def main():
    home = Path.home() / ".hermes-cdlm"
    home.mkdir(exist_ok=True)
    os.environ["HERMES_HOME"] = str(home)

    from hermes_cli.main import main as hermes_main
    hermes_main()
