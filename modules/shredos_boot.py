import subprocess


def reboot_to_shredos(entry: str = "ShredOS") -> None:
    try:
        subprocess.check_call(["sudo", "grub-reboot", entry])
        subprocess.check_call(["sudo", "reboot"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
