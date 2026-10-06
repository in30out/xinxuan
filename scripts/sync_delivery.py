"""把 dist/ 里刚构建出来的产物刷新到 交付_芯选_v1.4/，并重算 SHA256。

为什么需要它：交付目录**不进仓库**（体积大、且可由 build_exe.py 一条命令重建），
所以每次重建 exe 之后都要手工同步一次；手工同步容易出现"ZIP 换了、说明里的
SHA256 还是旧的"这种事故。本脚本把这件事固定成一条命令。

用法：
    python scripts/sync_delivery.py                 # 同步 ZIP + 已解压目录
    python scripts/sync_delivery.py --dry-run       # 只比对，不写
    python scripts/sync_delivery.py --skip-extract  # 只同步 ZIP

退出码：0 成功 / 1 缺产物或校验不一致。
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUT = ROOT / "交付_芯选_v1.4"
ZIP = DIST / "芯选-便携版.zip"
EXTRACTED = DIST / "芯选-便携版"


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest().upper()


def count_files(path: Path) -> int:
    return sum(1 for p in path.rglob("*") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="刷新免安装交付目录")
    ap.add_argument("--dry-run", action="store_true", help="只比对不写")
    ap.add_argument("--skip-extract", action="store_true", help="只同步 ZIP，不复制解压目录")
    args = ap.parse_args(argv)

    if not ZIP.exists():
        print(f"[X] 找不到 {ZIP}\n    先跑： python build_exe.py --clean")
        return 1

    OUT.mkdir(exist_ok=True)
    dst_zip = OUT / f"芯选-便携版-v1.4.zip"
    src_hash = sha256(ZIP)

    print(f"[ZIP] 源  {ZIP.name}  {ZIP.stat().st_size:,} B  {src_hash[:16]}…")
    if dst_zip.exists():
        old = sha256(dst_zip)
        same = old == src_hash
        print(f"[ZIP] 旧  {dst_zip.name}  {dst_zip.stat().st_size:,} B  {old[:16]}…  "
              f"{'（一致，无需更新）' if same else '（不一致，将覆盖）'}")
    else:
        same = False
        print(f"[ZIP] 旧  不存在")

    if not args.dry_run and not same:
        shutil.copy2(ZIP, dst_zip)
        print(f"[ZIP] 已写入 {dst_zip}")

    if not args.skip_extract:
        if not EXTRACTED.is_dir():
            print(f"[!] 找不到解压源 {EXTRACTED}，跳过")
        else:
            n_src = count_files(EXTRACTED)
            dst_dir = OUT / "芯选-便携版"
            if args.dry_run:
                print(f"[DIR] 源 {n_src} 文件 / 目标 {count_files(dst_dir) if dst_dir.is_dir() else '不存在'}")
            else:
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                shutil.copytree(EXTRACTED, dst_dir)
                print(f"[DIR] 已复制 {n_src} 文件 → {dst_dir}")

    # 说明文件里的哈希必须和新包一致：这里只报告，不自动改写（避免脚本改文档）
    print("\n=== 需要写进文档的哈希 ===")
    for name, path in (("zip", dst_zip if dst_zip.exists() else ZIP),
                       ("exe", EXTRACTED / "芯选" / "芯选.exe"),
                       ("vbs", EXTRACTED / "静默启动（无黑框）.vbs")):
        if path.exists():
            print(f"  {sha256(path)}  {name}  ({path.stat().st_size:,} B)")
    print("  刷新到：交付_芯选_v1.4/README-交付说明.md、README.md §6.2、需求及开发文档.md §3.8.5/3.8.6")

    if not args.dry_run and dst_zip.exists():
        if sha256(dst_zip) != src_hash:
            print("\n[FAIL] 复制后哈希不一致")
            return 1
        print("\nDELIVERY_SYNC_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
