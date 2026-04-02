import ctypes
import json
import keyboard
import os.path
import sys
import threading
import time

import psutil
import pystray
import tendo.singleton
from PIL import Image


DEFAULT_CONFIG = {
    "target_app_shortcuts": {
        "sai.exe": {"pen": "b", "eraser": "e"},
        "sai2.exe": {"pen": "b", "eraser": "e"},
        "photoshop.exe": {"pen": "b", "eraser": "e"},
        "clipstudiopaint.exe": {"pen": "p", "eraser": "e"},
        "clipstudiopaint_x64.exe": {"pen": "p", "eraser": "e"},
        "krita.exe": {"pen": "b", "eraser": "e"},
        "concepts.exe": {"pen": "1", "eraser": "e"},
    }
}

compat_mode_enabled = True
TARGET_APP_SHORTCUTS = DEFAULT_CONFIG["target_app_shortcuts"].copy()
SHORTCUT_SEND_DELAY_SECONDS = 0.03
SHORTCUT_WAIT_TIMEOUT_SECONDS = 1.0


def deep_copy_json_compatible(value):
    if isinstance(value, dict):
        return {k: deep_copy_json_compatible(v) for k, v in value.items()}
    if isinstance(value, list):
        return [deep_copy_json_compatible(item) for item in value]
    return value


def merge_dict_defaults(base: dict, override: dict) -> dict:
    merged = deep_copy_json_compatible(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def quote_windows_arg(arg: str) -> str:
    return '"' + arg.replace('"', '\\"') + '"'


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = " ".join(quote_windows_arg(arg) for arg in sys.argv[1:])
    else:
        executable = sys.executable
        script_path = os.path.abspath(sys.argv[0])
        all_args = [script_path] + sys.argv[1:]
        params = " ".join(quote_windows_arg(arg) for arg in all_args)

    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, params, None, 1
    )
    if result <= 32:
        raise RuntimeError("管理员权限申请失败或被取消。")
    sys.exit(0)


def ensure_admin() -> None:
    if not is_admin():
        relaunch_as_admin()


def runtime_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(getattr(sys, "_MEIPASS"), relative_path)
    return os.path.join(runtime_dir(), relative_path)


def config_path() -> str:
    return os.path.join(runtime_dir(), "config.json")


def write_config(config: dict) -> None:
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalize_shortcuts(raw_shortcuts: dict) -> dict:
    normalized = {}
    for process_name, shortcuts in raw_shortcuts.items():
        if not isinstance(process_name, str) or not isinstance(shortcuts, dict):
            continue
        pen_key = shortcuts.get("pen")
        eraser_key = shortcuts.get("eraser")
        if not isinstance(pen_key, str) or not pen_key.strip():
            continue
        if not isinstance(eraser_key, str) or not eraser_key.strip():
            continue
        normalized[process_name.lower()] = {
            "pen": pen_key.strip(),
            "eraser": eraser_key.strip(),
        }
    return normalized


def load_config(logger=print) -> dict:
    config_file = config_path()
    config = deep_copy_json_compatible(DEFAULT_CONFIG)

    if not os.path.exists(config_file):
        write_config(config)
        logger(f"已生成默认配置: {config_file}")
        return config

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            user_config = json.load(f)
    except Exception as exc:
        logger(f"读取配置失败，使用默认配置: {exc}")
        write_config(config)
        return config

    if not isinstance(user_config, dict):
        logger("配置文件格式错误，已重置为默认配置。")
        write_config(config)
        return config

    merged_config = merge_dict_defaults(DEFAULT_CONFIG, user_config)
    merged_config["target_app_shortcuts"] = normalize_shortcuts(
        merged_config.get("target_app_shortcuts", {})
    )
    write_config(merged_config)
    logger(f"已加载配置: {config_file}")
    return merged_config


def get_foreground_process_name() -> str:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return ""

    pid = ctypes.c_ulong(0)
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return ""

    try:
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def send_compat_shortcut(eraser_mode: bool) -> None:
    if not compat_mode_enabled:
        return

    process_name = get_foreground_process_name()
    app_shortcuts = TARGET_APP_SHORTCUTS.get(process_name)
    if not app_shortcuts:
        return

    key = app_shortcuts["eraser"] if eraser_mode else app_shortcuts["pen"]

    def _send_after_hotkey_release() -> None:
        # The pen double-click arrives as win+f19. Wait for the physical Win key
        # to be released instead of force-releasing it, which can open Start.
        deadline = time.time() + SHORTCUT_WAIT_TIMEOUT_SECONDS
        while time.time() < deadline:
            if not (
                keyboard.is_pressed("windows")
                or keyboard.is_pressed("left windows")
                or keyboard.is_pressed("right windows")
            ):
                break
            time.sleep(0.01)

        time.sleep(SHORTCUT_SEND_DELAY_SECONDS)
        keyboard.send(key, do_press=True, do_release=True)

    threading.Thread(target=_send_after_hotkey_release, daemon=True).start()


class Pen:
    PenService: ctypes.CDLL
    eraser_mode: bool
    log: "function"

    def __init__(self, logger: "function" = print) -> None:
        self.PenService = None
        self.log = logger

        executable_dir_dll = os.path.join(runtime_dir(), "PenService-PCManager.dll")
        candidate_paths = [executable_dir_dll]
        if hasattr(sys, "_MEIPASS"):
            meipass_dll = os.path.join(getattr(sys, "_MEIPASS"), "PenService-PCManager.dll")
            if meipass_dll not in candidate_paths:
                candidate_paths.append(meipass_dll)

        for lib_path in candidate_paths:
            try:
                self.PenService = ctypes.cdll.LoadLibrary(lib_path)
            except Exception:
                pass
            if self.PenService:
                break

        if self.PenService:
            self.init_ink_workspace_handler()
            self.pen()
        else:
            raise Exception(
                "无法加载 PenService-PCManager.dll。请将该 DLL 放在程序所在目录，"
                "或使用打包后的单 EXE 版本（内置 DLL）。"
            )

    def init_ink_workspace_handler(self) -> None:
        self.log("切换事件监听器")
        self.PenService.CommandSendSetPenKeyFunc(2)

    def eraser(self) -> bool:
        self.log("切换为橡皮擦")
        if self.PenService.CommandSendPenCurrentFunc(1) != 0:
            self.eraser_mode = True
            return True
        return False

    def pen(self) -> bool:
        self.log("切换为笔")
        if self.PenService.CommandSendPenCurrentFunc(0) != 0:
            self.eraser_mode = False
            return True
        return False

    def switch_mode(self, callback=None) -> bool:
        if [self.eraser, self.pen][int(self.eraser_mode)]():
            send_compat_shortcut(self.eraser_mode)
            if callback:
                callback(self.eraser_mode)
            return True
        return False


def double_click_gen(pen):
    def _onhotkey():
        print("触发双击")
        pen.switch_mode(callback=icon_change)

    return _onhotkey


def kbd_thread_gen(pen):
    def _func():
        double_click = double_click_gen(pen)
        keyboard.add_hotkey("win+f19", double_click)
        keyboard.wait()

    return _func


Pen_Icon = Image.open(resource_path(os.path.join("res", "Designcontest-Vintage-Pen.ico")))
Eraser_Icon = Image.open(resource_path(os.path.join("res", "Designcontest-Vintage-Eraser.ico")))


def icon_change(eraser_mode: bool):
    global icon
    if eraser_mode:
        icon.icon = Eraser_Icon
        icon.title = "橡皮模式"
    else:
        icon.icon = Pen_Icon
        icon.title = "笔输入模式"


def stop(*_args):
    global icon
    icon.stop()


def fixup_ink_workspace(*_args):
    global pen
    pen.init_ink_workspace_handler()


def toggle_compat_mode(*_args):
    global compat_mode_enabled
    global icon
    compat_mode_enabled = not compat_mode_enabled
    icon.update_menu()


def compat_mode_checked(_item):
    return compat_mode_enabled


def loop_ink_workspace_fixup():
    global pen
    while True:
        pen.init_ink_workspace_handler()
        time.sleep(10)


menu = (
    pystray.MenuItem(text="绘画软件兼容模式", action=toggle_compat_mode, checked=compat_mode_checked),
    pystray.MenuItem(text="修复 Windows Ink 事件监听", action=fixup_ink_workspace),
    pystray.MenuItem(text="退出", action=stop),
)
icon = pystray.Icon("Eraser Service", menu=menu)


if __name__ == "__main__":
    try:
        ensure_admin()
        loaded_config = load_config()
        TARGET_APP_SHORTCUTS = loaded_config["target_app_shortcuts"]
        me = tendo.singleton.SingleInstance("HuaweiPenEraserService")
        pen = Pen()
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(None, e.args[0], "错误", 0x00000010)
        sys.exit(1)

    kbd_thread = threading.Thread(target=kbd_thread_gen(pen), daemon=True)
    kbd_thread.start()
    icon_change(False)
    icon_thread = threading.Thread(target=icon.run)
    icon_thread.start()
    ink_fixup_thread = threading.Thread(target=loop_ink_workspace_fixup, daemon=True)
    ink_fixup_thread.start()
    icon_thread.join()
