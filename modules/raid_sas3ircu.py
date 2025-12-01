import subprocess


def sas3ircu_display() -> str:
    try:
        return subprocess.check_output(["sas3ircu", "0", "display"], text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
