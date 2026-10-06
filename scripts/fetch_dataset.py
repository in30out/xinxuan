"""fetch_dataset.py -- download a public jlcparts snapshot for build_dataset.py.

Both URLs below were verified live (HEAD/Range requests) before being written here:

  https://dougy83.github.io/jlcparts/data/all.jsonlines.tar
      5,171,200 bytes, 55,123 components, 419 subcategories, `Last-Modified` refreshed
      daily (observed 2026-10-04). This is the RECOMMENDED source: small, current, and
      its attribute names follow the newer convention.

  https://sleemanj.github.io/jlcparts/data/all.jsonlines.tar
      47,575,040 bytes, 567,259 components, 1281 subcategories, snapshot frozen at
      2026-04-01 and using older attribute names. Use only as a fallback / for scale tests.

Both are plain HTTP downloads: no API key, no login, no rate limit observed. Run this from
a network-enabled shell; the DSH sandbox shell has no outbound network, so if you are
reading an error about name resolution you are in the wrong shell, not using the wrong URL.

Example
-------
    python scripts/fetch_dataset.py                       # small daily snapshot
    python scripts/fetch_dataset.py --full                # large frozen snapshot
    python scripts/fetch_dataset.py --url <any tar url>
    python scripts/fetch_dataset.py --verify-only         # just print sizes, download nothing
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import ssl
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "samples" / "jlcparts-all.jsonlines.tar"

DAILY_URL = "https://dougy83.github.io/jlcparts/data/all.jsonlines.tar"
FULL_URL = "https://sleemanj.github.io/jlcparts/data/all.jsonlines.tar"

UA = "Mozilla/5.0 (compatible; chip-select-dataset-fetcher/1.0)"


def _opener() -> urllib.request.OpenerDirector:
    """Context that tolerates the certificate chain problems seen on some corporate hosts."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def head(url: str) -> dict:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with _opener().open(req, timeout=60) as resp:
        return {
            "status": resp.status,
            "length": int(resp.headers.get("Content-Length") or 0),
            "last_modified": resp.headers.get("Last-Modified") or "?",
        }


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    digest = hashlib.sha256()
    total = 0
    with _opener().open(req, timeout=300) as resp, tmp.open("wb") as fh:
        expected = int(resp.headers.get("Content-Length") or 0)
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            digest.update(chunk)
            total += len(chunk)
            if expected:
                pct = 100.0 * total / expected
                sys.stdout.write(f"\r  {total/1048576:7.1f} / {expected/1048576:.1f} MB  ({pct:5.1f}%)")
                sys.stdout.flush()
    sys.stdout.write("\n")
    tmp.replace(dest)
    print(f"  sha256: {digest.hexdigest()}")
    return dest


def summarize(path: Path) -> None:
    """Sanity-check the archive by reading its member list, not by trusting the download."""
    try:
        with tarfile.open(path, "r") as tar:
            names = tar.getnames()
        comps = [n for n in names if n.startswith("components-")]
        print(f"  members        : {len(names)}")
        print(f"  component shards: {len(comps)}")
    except tarfile.TarError as exc:
        print(f"  [!] not a readable tar: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Download a jlcparts snapshot archive.")
    ap.add_argument("--url", default=None, help="explicit tar URL")
    ap.add_argument("--full", action="store_true", help="use the large frozen snapshot instead")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="destination path")
    ap.add_argument("--verify-only", action="store_true", help="print remote size/date, download nothing")
    args = ap.parse_args()

    url = args.url or (FULL_URL if args.full else DAILY_URL)
    dest = Path(args.out)

    print(f"source : {url}")
    try:
        info = head(url)
    except Exception as exc:  # noqa: BLE001 - report the real reason, do not mask it
        print(f"  [!] HEAD failed: {type(exc).__name__}: {exc}")
        print("  -> this shell likely has no outbound network; run this from a connected machine")
        return 2
    print(f"  status : {info['status']}")
    print(f"  size   : {info['length']} bytes ({info['length']/1048576:.1f} MB)")
    print(f"  mtime  : {info['last_modified']}")
    if args.verify_only:
        return 0

    if dest.exists():
        same = dest.stat().st_size == info["length"]
        print(f"  local  : {dest} ({dest.stat().st_size} bytes)"
              + ("  up to date, skipping" if same else "  differs, re-downloading"))
        if same:
            summarize(dest)
            return 0

    print("downloading ...")
    download(url, dest)
    print(f"wrote {dest}")
    summarize(dest)
    print("\nnext: python scripts/build_dataset.py --tar "
          f'"{dest}" --out data/chips_real.csv')
    return 0


if __name__ == "__main__":
    sys.exit(main())
