import json
import subprocess
from typing import Dict


def storcli_overview() -> Dict:
    return _run(["/opt/MegaRAID/storcli/storcli64", "show", "j"])


def storcli_physical() -> Dict:
    return _run(["/opt/MegaRAID/storcli/storcli64", "/c0", "/eall", "/sall", "show", "j"])


def _run(cmd):
    try:
        output = subprocess.check_output(cmd, text=True)
        return json.loads(output)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return {}
