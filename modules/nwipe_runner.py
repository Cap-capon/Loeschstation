import subprocess


def run_nwipe() -> None:
    try:
        subprocess.Popen(["gnome-terminal", "--", "sudo", "nwipe", "--sync", "--verify=last"])
    except FileNotFoundError:
        pass
