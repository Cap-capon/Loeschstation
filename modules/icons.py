import os


BASE_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "img")

# Dateibasierte Icons – explizit ohne Theme-Namen, damit alle Tiles konsistent
ICON_SHREDOS = "img/shredOS_icon.svg"
ICON_BLANCCO = "img/blancco_icon.svg"
ICON_BAOBAB = "img/baobab.svg"
ICON_GPARTED = "img/gparted.svg"
ICON_PARTITIONMANAGER = "img/partitionmanager.svg"
ICON_BLEACHBIT = "img/bleachbit.svg"
ICON_FIO = "img/utilities-terminal.svg"
ICON_BADBLOCKS = "img/media-removable.svg"

# Theme-basierte Icons (Fallbacks bleiben bestehen)
ICON_GSMART = "gsmartcontrol"
ICON_GNOME_DISKS = "org.gnome.DiskUtility"
ICON_SMARTCLI = "utilities-terminal"
ICON_NVMEINFO = "document-properties"
ICON_NWIPE = os.path.join(BASE_IMG_DIR, "blancco_icon.svg")
ICON_SECURE_ERASE = "edit-delete"
ICON_BLANCCO_OS = ICON_BLANCCO
ICON_CERT_GUI = "text-x-generic"
ICON_LOG_FOLDER = "folder"

# Default-Icon für unbekannte Tools
ICON_DEFAULT = "drive-harddisk"
