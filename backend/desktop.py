"""桌面外壳入口：内嵌启动后端，用系统 WebView2 开窗，无控制台窗口。

用法：双击根目录「灵感空间.vbs」（pythonw 运行本文件）。
若 8000 端口已有运行中的后端（如开发模式），窗口直接附着到它。
日志写入 data/desktop.log。
"""

import ctypes
import logging
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

import uvicorn
import webview

HOST = "127.0.0.1"
PORT = 8000
BACKEND_DIR = Path(__file__).resolve().parent

if getattr(sys, "frozen", False):
    from app.config import DATA_DIR

    LOG_FILE = DATA_DIR / "desktop.log"
    ICON_CANDIDATES = [
        Path(getattr(sys, "_MEIPASS", BACKEND_DIR)) / "frontend_dist" / "favicon.ico",
        Path(sys.executable).parent / "favicon.ico",
    ]
else:
    LOG_FILE = BACKEND_DIR / "data" / "desktop.log"
    ICON_CANDIDATES = [
        BACKEND_DIR.parent / "frontend" / "dist" / "favicon.ico",
        BACKEND_DIR.parent / "scripts" / "icon" / "favicon.ico",
    ]

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
)


def _port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, PORT)) == 0


def _serve() -> None:
    # 直接传 app 对象而非 import 字符串，并显式指定 asyncio/h11，兼容 PyInstaller 冻结模式
    from app.main import app

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", loop="asyncio", http="h11")


def _set_window_icon() -> None:
    """后台线程：等窗口出现后用 Win32 换掉任务栏/标题栏图标（默认继承 pythonw.exe）。"""
    icon = next((p for p in ICON_CANDIDATES if p.exists()), None)
    if icon is None:
        return
    user32 = ctypes.windll.user32
    for _ in range(50):  # 最多等 5 秒
        hwnd = user32.FindWindowW(None, "灵感空间")
        if hwnd:
            # 按系统实际尺寸分别从多尺寸 ico 中取最匹配的图，避免小图放大发糊
            big_w = user32.GetSystemMetrics(11)   # SM_CXICON
            big_h = user32.GetSystemMetrics(12)   # SM_CYICON
            sm_w = user32.GetSystemMetrics(49)    # SM_CXSMICON
            sm_h = user32.GetSystemMetrics(50)    # SM_CYSMICON
            hbig = user32.LoadImageW(None, str(icon), 1, big_w, big_h, 0x10)
            hsmall = user32.LoadImageW(None, str(icon), 1, sm_w, sm_h, 0x10)
            if hbig:
                user32.SendMessageW(hwnd, 0x80, 1, hbig)  # WM_SETICON, ICON_BIG
                user32.SetClassLongPtrW(hwnd, -14, hbig)  # GCLP_HICON
            if hsmall:
                user32.SendMessageW(hwnd, 0x80, 0, hsmall)  # ICON_SMALL
                user32.SetClassLongPtrW(hwnd, -34, hsmall)  # GCLP_HICONSM
            if hbig or hsmall:
                logging.info("窗口图标已设置为 %s（big=%dx%d small=%dx%d）", icon, big_w, big_h, sm_w, sm_h)
            return
        time.sleep(0.1)


def main() -> None:
    # 单实例锁：已有一个桌面外壳在运行则静默退出，避免重复弹窗
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "InspirationSpaceDesktopSingleton")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return
    _ = mutex  # 持有到进程结束

    # 独立 AppUserModelID：任务栏不再按 pythonw.exe 的关联解析图标（Spyder/Jupyter）
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "InspirationSpace.Desktop"
    )

    if not _port_open():
        threading.Thread(target=_serve, daemon=True).start()
        for _ in range(100):  # 最多等 10 秒
            if _port_open():
                break
            time.sleep(0.1)

    threading.Thread(target=_set_window_icon, daemon=True).start()
    webview.create_window("灵感空间", f"http://{HOST}:{PORT}", width=1280, height=860)
    webview.start()
    logging.info("窗口已关闭，进程退出")
    os._exit(0)  # 不让 daemon 线程（uvicorn）拖住进程


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.error("桌面外壳启动失败\n%s", traceback.format_exc())
        raise
