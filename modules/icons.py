import os


BASE_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "img")

# Dateibasierte Icons
ICON_SHREDOS = os.path.join(BASE_IMG_DIR, "shredOS_icon.svg")
ICON_BLANCCO = os.path.join(BASE_IMG_DIR, "blancco_icon.svg")

# Theme-basierte Icons
ICON_GSMART = "gsmartcontrol"
ICON_GNOME_DISKS = "org.gnome.DiskUtility"
ICON_PARTITIONMANAGER = "partitionmanager"
ICON_GPARTED = "gparted"
ICON_BAOBAB = "baobab"
ICON_SMARTCLI = "utilities-terminal"
ICON_NVMEINFO = "document-properties"
ICON_FIO = "utilities-terminal"
ICON_BADBLOCKS = "media-removable"
ICON_NWIPE = os.path.join(BASE_IMG_DIR, "blancco_icon.svg")
ICON_SECURE_ERASE = "edit-delete"
ICON_BLANCCO_OS = ICON_BLANCCO
ICON_CERT_GUI = "text-x-generic"
ICON_LOG_FOLDER = "folder"
ICON_BLEACHBIT = "bleachbit"

# Default-Icon für unbekannte Tools
ICON_DEFAULT = "drive-harddisk"
