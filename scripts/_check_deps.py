"""_check_deps.py -- dependency probe used by scripts/check.ps1.

Exits 0 when every runtime dependency imports, 1 otherwise.
Kept ASCII-only so it behaves the same under any console codepage.
"""
from __future__ import annotations

import importlib
import importlib.metadata as md
import sys

MODULES = ["numpy", "pandas", "sklearn", "flask", "jieba"]


def _version(name: str) -> str:
    """Version string without triggering Flask 3.2's __version__ deprecation."""
    module = importlib.import_module(name)
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        pass
    # Locally unpacked wheels (scripts/fetch_deps.py -> .deps/) carry no
    # dist-info in every case, so fall back to the module's own attribute.
    for attr in ("__version__", "VERSION", "__VERSION__"):
        value = getattr(module, attr, None)
        if isinstance(value, str):
            return value
        if value is not None:
            return str(value)
    return "?"


def main() -> int:
    missing: list[str] = []
    for name in MODULES:
        try:
            version = _version(name)
        except Exception as exc:  # noqa: BLE001 - report whatever went wrong
            missing.append(f"{name}: {exc}")
            print(f"  {name:<10} MISSING")
        else:
            print(f"  {name:<10} {version}")

    if missing:
        print("MISSING " + " | ".join(missing))
        return 1
    print("DEPS_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
