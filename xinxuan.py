"""xinxuan.py —— 桌面窗口壳：Flask 后台线程 + pywebview 原生窗口。

.exe 的入口就是它（由 build_exe.py 打包）。三种运行模式：
  python xinxuan.py               原生窗口（pywebview + WebView2）
  python xinxuan.py --browser     起服务并打开默认浏览器（pywebview 不可用时的兜底）
  python xinxuan.py --no-window   只起服务（调试用）

关键取舍
--------
* **先起服务、后开窗口**：pywebview 的窗口加载 URL 时会立刻请求页面，若此时 Flask
  还没监听会白屏。这里显式轮询 /api/health 直到 200 才创建窗口。
* **端口占用**：默认 5000，被占则依次试 5001..5020；用户也可用 PORT 指定。
* **窗口关闭 = 进程退出**：webview.start() 返回后走 os._exit(0)，因为 werkzeug
  的 serve_forever 线程是非 daemon 的，直接 return 会挂住进程（表现为窗口关了但
  exe 还在任务管理器里）。
* **冻结状态**：sys.frozen 为真时是 PyInstaller 单文件包，sys.path 里已由
  PyInstaller 注入原型模块（wsgi/data_loader/... 是按 --paths prototype 分析进去的），
  而 web/ 与 data/samples/ 由 --add-data 落在 sys._MEIPASS 下，wsgi.py 自己处理。
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

log = logging.getLogger("xinxuan")

# 开发态：仓库根 + prototype/ 都要在搜索路径里（根目录放 xinxuan.py，本体在 prototype/）。
# 冻结态：这些模块已被打包进 exe，_HERE 也会指向解包目录，加上去无害且更稳。
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "prototype")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from wsgi import VERSION, create_app  # noqa: E402

WINDOW_TITLE = "芯选 —— 芯片替代选型智能推荐系统"
PORT_TRIES = range(5000, 5021)


def free_port(preferred=None):
    """返回可用的本地端口；preferred 可用就优先用它。"""
    cands = [preferred] if preferred else []
    cands += [p for p in PORT_TRIES if p != preferred]
    for port in cands:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("找不到可用端口（5000-5020 全被占用）")


def serve(app, port):
    """在后台线程里跑 werkzeug。线程非 daemon，进程退出由调用方决定。"""
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, name="xinxuan-http")
    thread.start()
    return server


def wait_ready(port, timeout=30.0):
    """轮询 /api/health，直到服务真正可连（含首次索引构建时间）。"""
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.15)
    return False


def probe_marker_path():
    """浏览器探针文件的路径（由 --browser-probe 传入，或读环境变量）。"""
    return os.environ.get("XINXUAN_BROWSER_PROBE") or None


def browser_reached(prefix=None, wait=8.0, marker=None):
    """判断"浏览器是否真的把页面打开了"。

    为什么不能只看调用返回值：实测（见 .tmp/probe_browser2.py）在受限环境里
    os.startfile / webbrowser.open / open_new_tab / msedge+独立 profile / chrome+独立 profile
    全部返回"成功"，但服务端 access log **一次请求都没有** —— 调用成功 != 页面打开。

    唯一硬判据是"浏览器真的来请求过页面"。这里给每次尝试生成一个一次性 URL 后缀，
    由页面里的 <img src="/_boot/<token>"> 触发；自定义的 /_boot/ 处理器收到后落一个
    标记文件，我们轮询这个文件即可确认。
    """
    marker = marker or probe_marker_path()
    if not marker or not prefix:
        return None  # 没有探针渠道，无法判定
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            if os.path.exists(marker):
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def _browser_paths():
    """常见 Chromium 系浏览器的可执行文件位置（按存在性过滤）。"""
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("ProgramFiles", r"C:\Program Files")
    prog86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    out = []
    for cands in (
        [os.path.join(prog86, r"Microsoft\Edge\Application\msedge.exe"),
         os.path.join(prog, r"Microsoft\Edge\Application\msedge.exe"),
         os.path.join(local, r"Microsoft\Edge\Application\msedge.exe")],
        [os.path.join(prog, r"Google\Chrome\Application\chrome.exe"),
         os.path.join(prog86, r"Google\Chrome\Application\chrome.exe"),
         os.path.join(local, r"Google\Chrome\Application\chrome.exe")],
    ):
        for path in cands:
            if os.path.exists(path):
                out.append(path)
                break
    return out


def is_elevated():
    """当前进程是否提权运行（提权会让浏览器交接失败，见 _open_browser 说明）。"""
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _open_browser(url, prefix=None, wait=6.0):
    """把 URL 交给浏览器，并**验证它真的打开了**。返回 (是否已打开, 成功的方式名)。

    顺序按"**先把能用的用掉**"排，每次尝试后立刻用探针确认：

      1. Edge/Chrome + **独立 user-data-dir** —— 放在第一位是有原因的：用户实测反馈过
         「Microsoft Edge 未响应，因为现有实例正在以提升的权限运行。是否要用普通权限
         重启现有实例？」那句话，正是 os.startfile（走 shell 默认程序 + 已有实例 IPC）
         触发的。带独立 user-data-dir 启动会**另起一个全新实例**，不碰已有实例的 IPC，
         从根上绕开权限冲突，也不会弹那个让人不知所措的对话框。
      2. os.startfile —— Windows 最正统的"用默认程序打开"。只有在"另起实例"没能把页面
         打开时才会走到这里（例如系统里只有默认浏览器、且它不是 Edge/Chrome）。
         这种环境通常是权限一致的，一次就中，不会多出一个孤立窗口。
      3. Edge/Chrome 直启（不带 profile）—— 最后再试一次。
      （不再单独试 webbrowser.open：它内部就是 os.startfile / ShellExecute，重复且多花时间。）

    返回值严格：True=探针命中（浏览器真的来请求过页面）；False=试完都没命中。
    """
    attempts: list[str] = []

    def _try(name, fn):
        try:
            fn()
            attempts.append(name)
            return True
        except Exception as exc:  # noqa: BLE001
            attempts.append(f"{name}({type(exc).__name__})")
            return False

    exes = _browser_paths()
    log.info("浏览器交接开始（每次尝试后用探针确认页面是否真的被打开）：%s",
             "、".join(os.path.basename(e) for e in exes) or "未找到 Edge/Chrome")
    profile = os.path.join(tempfile.gettempdir(), "xinxuan-browser-profile")
    try:
        os.makedirs(profile, exist_ok=True)
    except OSError:
        profile = None

    # 1) 独立 profile 优先：绕开"已有实例权限不一致"，同时避免 Edge 弹权限对话框
    if profile:
        for exe in exes:
            tag = os.path.basename(exe)
            _try(f"{tag}+独立profile",
                 lambda e=exe: subprocess.Popen(  # noqa: S603
                     [e, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", url],
                     close_fds=True))
            if browser_reached(prefix, wait=wait):
                log.info("浏览器已打开（方式：%s + 独立 profile）", tag)
                return True, f"{tag}+profile"

    # 2) 系统默认程序（正统路径；换了环境才走到这里）
    _try("os.startfile", lambda: os.startfile(url))  # noqa: S606 —— Windows 专有，正是要用它
    if browser_reached(prefix, wait=8.0):
        log.info("浏览器已打开（方式：os.startfile）")
        return True, "os.startfile"

    # 3) 直启（不另带 profile）：最后再试一次，等待时间收紧，避免用户白等
    for exe in exes:
        tag = os.path.basename(exe)
        _try(f"{tag}(直启)", lambda e=exe: subprocess.Popen([e, url], close_fds=True))  # noqa: S603
        if browser_reached(prefix, wait=4.0):
            log.info("浏览器已打开（方式：%s 直启）", tag)
            return True, tag

    log.warning("浏览器交接失败（全部方式都没收到页面请求，说明浏览器没打开）。已尝试：%s",
                "、".join(attempts))
    if is_elevated():
        log.warning("当前进程是提权运行的；提权进程常常无法把 URL 交给普通权限的浏览器实例，"
                    "请改用非提权的终端/资源管理器双击启动。")
    return False, ""


def browser_tip(url):
    """浏览器没打开时的原生提示：把地址摆到用户眼前，并说明怎么自己打开。"""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            f"芯选 已经启动，但自动打开浏览器没有成功。\n\n"
            f"请在浏览器地址栏里手动粘贴：\n{url}\n\n"
            f"（本窗口不要关闭，关掉它就停止服务）\n\n"
            f"提示：如果刚才 Microsoft Edge 弹过\n"
            f"「现有实例正在以提升的权限运行」，\n"
            f"请从资源管理器双击启动，或换一个非管理员终端。",
            WINDOW_TITLE, 0x30)
    except Exception as exc:  # noqa: BLE001
        log.debug("浏览器提示框失败：%s", exc)


def hide_console():
    """隐藏控制台窗口（打包成 --console 后由 VBS 启动时用）。

    为什么需要：PyInstaller 的 --windowed 形态在受限环境里会静默失败，所以正式包
    用的是稳定的 --console 形态；但那会留一个黑框。静默启动器把进程起出来后调用
    这里把黑框藏掉，用户看到的就是"双击 → 界面打开"。
    返回 True 表示确实藏了一个控制台窗口。
    """
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    try:
        import ctypes

        kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, 0)      # SW_HIDE
        user32.SetConsoleTitleW(WINDOW_TITLE)
        return True
    except Exception as exc:  # noqa: BLE001 —— 藏不掉不影响功能
        log.debug("隐藏控制台失败：%s", exc)
        return False


def confirm_exit(url):
    """无控制台时用一个原生对话框占住进程，直到用户确认退出。

    浏览器模式下进程必须活着（服务在它里面）；没有控制台就没有 Ctrl+C，
    所以给一个 OK 对话框做"关闭即退出"的入口。
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            f"芯选 已在运行。\n\n界面地址：{url}\n"
            f"（如果浏览器没有自动打开，请手动复制上面的地址访问）\n\n"
            f"看完之后点「确定」，服务就随之关闭。",
            WINDOW_TITLE, 0x40)
    except Exception as exc:  # noqa: BLE001
        log.debug("退出对话框失败：%s", exc)


def _log_dir() -> str:
    """日志目录。打包后 exe 目录可能只读，故优先用户目录。"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or _HERE
    folder = os.path.join(base, "xinxuan")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = _HERE
    return folder


def _log_path() -> str:
    """诊断日志路径。"""
    return os.path.join(_log_dir(), "xinxuan.log")


def _setup_log(verbose: bool):
    """把日志同时写到控制台与文件；窗口模式出错时用户只能靠文件排查。"""
    handlers = [logging.FileHandler(_log_path(), encoding="utf-8")]
    if verbose:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=handlers, force=True)
    return handlers[0].baseFilename


def _open_window(url, gui_pref=None):
    """尝试用原生窗口打开页面。

    返回 True 表示窗口正常开启并已关闭；False 表示当前环境开不了窗口
    （调用方应回退到浏览器模式）。候选后端按 Windows 实情排序：
      edgechromium   WebView2（本机已装，Win10/11 默认，效果最好）
      mshtml         旧 IE 内核，仅在 WebView2 缺失时兜底
    两者都依赖 pythonnet，而 pythonnet 会尝试 **写一个临时 runtimeconfig.json** 并
    把 CoreCLR 载入进程。若运行环境不允许（受限沙箱的临时目录拒绝写入、或以
    非正常方式建立 .NET 运行时），窗口必然起不来 —— 此时只能回退浏览器。
    """
    try:
        import webview
    except ImportError as exc:
        log.warning("未安装 pywebview（%s），回退浏览器模式", exc)
        return False

    candidates = [gui_pref] if gui_pref else ["edgechromium", "mshtml"]
    for gui in candidates:
        try:
            webview.create_window(WINDOW_TITLE, url, width=1360, height=900,
                                  min_size=(1024, 700), text_select=True,
                                  confirm_close=False)
            log.info("打开原生窗口 gui=%s url=%s", gui, url)
            webview.start(gui=gui)
            log.info("窗口已关闭（gui=%s）", gui)
            return True
        except Exception as exc:  # noqa: BLE001 —— 任何后端异常都要能回退
            log.warning("原生窗口 gui=%s 启动失败：%s: %s", gui, type(exc).__name__, exc)
            # 上一次失败可能已经污染了 webview 状态（窗口已注册但未显示），
            # 清空待创建窗口列表，否则下一次 create_window 会带着残留窗口一起起
            try:
                webview.windows.clear()
            except Exception:  # noqa: BLE001
                pass
    return False


def _serve_until_interrupt(server):
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


def _crash_log(argv):
    """把启动期异常写进日志文件，并尽量弹一个原生提示框。

    为什么需要：打包成 --windowed 的 exe 没有控制台，双击失败时用户只看到
    "什么都没发生"。这里保证任何异常都留下**可读的**记录，并且退到 exe 同目录
    （用户自己就能找到），而不是只写进 %LOCALAPPDATA%。
    """
    import traceback

    detail = traceback.format_exc()
    lines = [f"芯选 启动失败（v{VERSION}）",
             f"argv: {argv}",
             f"cwd : {os.getcwd()}",
             f"exe : {sys.executable}",
             f"frozen: {getattr(sys, 'frozen', False)}",
             "",
             detail]
    text = "\n".join(lines)
    targets = []
    if getattr(sys, "frozen", False):
        targets.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                                    "xinxuan-crash.log"))
    else:
        targets.append(os.path.join(_HERE, "xinxuan-crash.log"))
    targets.append(os.path.join(_log_dir(), "xinxuan-crash.log"))
    written = None
    for path in targets:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            written = path
            break
        except OSError:
            continue
    log.error("启动失败：%s（详情见 %s）", detail.strip().splitlines()[-1], written or "日志写入失败")
    try:  # 有控制台时也打一份
        print(text, file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001
        pass
    if getattr(sys, "frozen", False):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                f"芯选 启动失败。\n\n{detail.strip().splitlines()[-1]}\n\n"
                f"完整日志：{written or '（无法写入）'}",
                "芯选", 0x10)
        except Exception:  # noqa: BLE001
            pass


def _boot_probe_hook():
    """在应用上加一次性引导探针：GET /_boot/<token> 落一个标记文件并返回 1x1 gif。

    为什么放在壳里而不是 wsgi.py：这是"启动器如何知道浏览器真的打开了"的机制，
    属于桌面壳的职责；开发态与冻结态共用同一段代码。
    """
    token = uuid.uuid4().hex[:12]
    marker = os.path.join(tempfile.gettempdir(), f"xinxuan-boot-{token}.probe")
    os.environ["XINXUAN_BROWSER_PROBE"] = marker
    gif = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
           b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")

    from flask import Response

    def register(app):
        @app.route("/_boot/<probe_token>")
        def _boot(probe_token):  # noqa: ANN202
            if probe_token == token:
                try:
                    with open(marker, "w", encoding="utf-8") as fh:
                        fh.write("ok")
                except OSError:
                    pass
            return Response(gif, mimetype="image/gif")

    return token, register


def main(argv=None):
    ap = argparse.ArgumentParser(description="芯选桌面版")
    ap.add_argument("--browser", action="store_true", help="用默认浏览器打开（不依赖 pywebview）")
    ap.add_argument("--no-window", action="store_true", help="只起 HTTP 服务，不开窗口")
    ap.add_argument("--gui", default=None,
                    help="强制指定原生 GUI 后端（edgechromium / mshtml）")
    ap.add_argument("--port", type=int, default=None, help="指定端口（默认 5000，占用则自动顺延）")
    ap.add_argument("--csv", default=None, help="自定义数据 CSV")
    ap.add_argument("--hide-console", action="store_true",
                    help="启动后隐藏控制台窗口（静默启动器用；仅打包后有效）")
    ap.add_argument("--debug", action="store_true", help="开发模式：Flask debug=True")
    ap.add_argument("--verbose", action="store_true", help="日志同时打到 stderr")
    args = ap.parse_args(argv)

    # 静默启动器（VBS）会设 XINXUAN_SILENT_LAUNCH=1：没有控制台可见，也就没有 Ctrl+C，
    # 所以退出入口改用原生对话框。
    silent = bool(os.environ.get("XINXUAN_SILENT_LAUNCH"))
    if args.hide_console or silent:
        hide_console()

    logfile = _setup_log(args.verbose)

    env_port = os.environ.get("PORT")
    port = free_port(args.port or (int(env_port) if env_port and env_port.isdigit() else None))
    app = create_app(args.csv)
    probe_token, register_probe = _boot_probe_hook()
    register_probe(app)
    if args.debug:
        app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
        return 0

    server = serve(app, port)
    url = f"http://127.0.0.1:{port}/"
    if not wait_ready(port):
        log.error("服务未能在 30 秒内就绪: %s", url)
    log.info("v%s 已就绪: %s（日志 %s）", VERSION, url, logfile)

    if args.no_window:
        _serve_until_interrupt(server)
        return 0

    opened = False
    if not args.browser:
        opened = _open_window(url, args.gui)

    if not opened:
        probe_url = f"{url}?_boot={probe_token}"
        log.info("改用浏览器模式打开 %s", probe_url)
        reached, how = _open_browser(probe_url, prefix=probe_token)
        if reached:
            log.info("浏览器已确认打开（方式：%s）", how)
        else:
            log.warning("无法确认浏览器已打开，改为弹出地址提示")
            browser_tip(url)
        if getattr(sys, "frozen", False) and (args.hide_console or silent):
            # 黑框已经藏起来了，也没有 Ctrl+C 可用 —— 用原生对话框当退出入口
            confirm_exit(url)
            server.shutdown()
            os._exit(0)
        _serve_until_interrupt(server)

    server.shutdown()
    # werkzeug 线程非 daemon，必须硬退出，否则窗口关了 exe 仍驻留
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 —— 双击 exe 时不能让异常静默消失
        _crash_log(sys.argv[1:])
        raise SystemExit(1)
