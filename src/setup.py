from cx_Freeze import setup, Executable
import sys

base = None
if sys.platform == "win32":
    base = "Win32GUI"

build_exe_options = {
    "packages": ["tkinter", "sqlite3", "matplotlib", "speedtest", "pystray", "PIL"],
    "excludes": [],
    "include_files": []
}

setup(
    name="Internet Speed Monitor",
    version="1.0",
    description="Мониторинг скорости интернета",
    options={"build_exe": build_exe_options},
    executables=[Executable("internet_speed_monitor.py", base=base, icon="icon.ico")]
)