# -*- coding: utf-8 -*-
"""
PyKuai Terminal Icon Lifecycle Watchdog
守护进程：在后台等待主控制台进程退出（无论是正常退出、Ctrl+C、崩溃，还是用户点击 [X] 强行关闭窗口），
一旦主进程结束，瞬间（5毫秒内）自动还原 Windows Terminal 的配置文件，
彻底确保日常普通 PowerShell 不留存任何小蛇图标！
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

    # 等待宿主 pykuai 进程结束
    SYNCHRONIZE = 0x00100000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)
    if handle:
        kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        kernel32.CloseHandle(handle)

    # 宿主进程已结束！立即还原 settings.json，移除任何临时 icon 绑定
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            changed = False
            profiles_list = data.get("profiles", {}).get("list", [])
            for p in profiles_list:
                pname = p.get("name", "")
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
