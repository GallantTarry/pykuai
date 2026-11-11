# -*- coding: utf-8 -*-
"""
PyKuai Terminal Icon Lifecycle Watchdog
Background daemon that waits for the parent console process to exit (normal exit,
Ctrl+C, crash, or clicking [X]) and immediately restores Windows Terminal settings.json
so default PowerShell tabs never retain temporary icon overrides.
"""
import os
import sys
import json
import ctypes


def main():
    if len(sys.argv) < 3:
        return

    try:
        parent_pid = int(sys.argv[1])
        settings_path = sys.argv[2]
    except Exception:
        return

    # Wait for the host pykuai process to terminate
    SYNCHRONIZE = 0x00100000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)
    if handle:
        kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        kernel32.CloseHandle(handle)

    # Restore settings.json by removing any temporary icon injection
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            changed = False
            profiles_list = data.get("profiles", {}).get("list", [])
            for p in profiles_list:
                pname = p.get("name", "")
                # Include localized Chinese profile name for Windows compatibility
                if pname in ["Windows PowerShell", "PowerShell", "命令提示符", "Command Prompt"]:
                    if "icon" in p:
                        del p["icon"]
                        changed = True
            if changed:
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
    except Exception:
        pass


if __name__ == "__main__":
    main()
