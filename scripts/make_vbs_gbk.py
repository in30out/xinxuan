"""make_vbs_gbk.py —— 把 UTF-8 的 .vbs 源文件转成 ANSI/GBK 的发布副本。

为什么需要：VBScript 宿主（wscript.exe / cscript.exe）按 **ANSI 代码页**读 .vbs。
本机是 zh-CN（GBK），所以启动器里的中文（"芯选\芯选.exe"）必须以 GBK 存盘；
用 UTF-8 存会出现乱码，`FileExists` 直接失败。

约定
----
* `packaging/silent_launch_utf8.vbs` 是**可编辑的源**（UTF-8，commit 进仓库）；
* `packaging/silent_launch.vbs` 是**生成的发布副本**（GBK，打包时用）。
改完源文件跑一次本脚本（或 `packaging\\rebuild_vbs.cmd`）即可。

用法
----
    python scripts/make_vbs_gbk.py packaging/silent_launch_utf8.vbs
    python scripts/make_vbs_gbk.py 源.vbs --out 目标.vbs
"""
from __future__ import annotations

import argparse
import os


def convert(src: str, dst: str | None = None) -> tuple[str, int, int]:
    """把 src 从 UTF-8 转成 GBK+CRLF 写到 dst（默认就地）。返回 (路径, 字节数, 非ASCII字节数)。"""
    target = dst or src
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    with open(target, "w", encoding="gbk", newline="\r\n") as fh:
        fh.write(text)
    raw = open(target, "rb").read()
    return target, len(raw), sum(1 for b in raw if b > 127)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把 UTF-8 的 .vbs 转成 ANSI/GBK 发布副本")
    ap.add_argument("src", nargs="+", help="UTF-8 的 .vbs 源文件")
    ap.add_argument("--out", default=None,
                    help="输出路径（仅单个源文件时可用；默认把 _utf8 后缀去掉）")
    args = ap.parse_args(argv)

    if args.out and len(args.src) > 1:
        print("[X] --out 只能配一个源文件使用")
        return 2

    for src in args.src:
        if not os.path.exists(src):
            print(f"[X] 不存在：{src}")
            return 1
        dst = args.out or (src.replace("_utf8.vbs", ".vbs") if src.endswith("_utf8.vbs") else src)
        try:
            target, size, non_ascii = convert(src, dst)
        except UnicodeDecodeError as exc:
            print(f"[!] {src} 看起来不是 UTF-8（可能已经是 GBK）：{exc}")
            continue
        print(f"[OK] {src} -> {target}（{size} B，非 ASCII 字节 {non_ascii}，无 BOM，CRLF）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
