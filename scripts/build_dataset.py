"""build_dataset.py -- turn a jlcparts `all.jsonlines.tar` snapshot into a chips CSV.

Why this exists: the prototype ships with 89 hand-made demo rows, but Section 4 of the
design doc promises a path from the real, verified public data source to a usable dataset.
This script is that path. It was written against the real snapshot structure (inspected
entry by entry, not guessed):

    -> tar members are named  components-<n>.jsonlines.gz   (418 of them)
                    +  attributes-lut.jsonlines.gz
                    +  subcategories.jsonlines.gz

    -> each member is a PLAIN gzip stream (not a nested tar). The first JSON line of
       components-*.jsonlines.gz is a header mapping field name -> column index:
       {"lcsc":0,"mfr":1,"description":2,"attrsIdx":3,"stock":4,"subcategoryIdx":5,
        "joints":6,"datasheet":7,"price":8,"img":9,"url":10}
       Every following line is a JSON ARRAY indexed by that map.

    -> attributes-lut.jsonlines.gz line N is [attributeName, meta] where
       meta = {"format": "${...}", "primary": "<key>",
               "values": {"<key>": [value, unit], ...}}
       A component's `attrsIdx` is a LIST of ABSOLUTE line numbers into this LUT. Those
       numbers are NOT necessarily sorted or contiguous, so look each one up directly.

    -> `subcategoryIdx` is 1-based and matches the <n> of the sibling
       components-<n>.jsonlines.gz member (418 of each).

    -> `mfr` column holds the PART NUMBER, not the manufacturer. The manufacturer comes
       from the "Manufacturer" attribute (only ~704/43102 LUT entries). The real package
       string comes from the "Package" attribute (~3980 entries).

    NOT available in this source: lead time and lifecycle. The only status attribute is
    "Status" (value "Active" for all 1896 occurrences), so NRND/EOL judgments are not
    possible here. Those demo columns are left EMPTY instead of being invented.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import re
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "chips.csv"

# Attribute lookup priority. The first name present wins.
TEMP_KEYS = ("Operating Temperature", "Working Temperature", "Temperature Range",
             "Operating Junction Temperature Range")
VCC_KEYS = ("Supply Voltage", "Operating Voltage", "Voltage - Supply")
PIN_KEYS = ("Number of Pins", "Number of Contacts")
PACKAGE_KEYS = ("Package",)
MANUFACTURER_KEYS = ("Manufacturer",)

# Package string -> pin count, e.g. "LQFP48" -> 48, "SOIC-8" -> 8, "SOT-23-5" -> 5.
PKG_TOKEN_RE = re.compile(
    r"LQFP|TQFP|QFN|DFN|SOIC|SOP|SSOP|TSSOP|MSOP|DIP|PDIP|CDIP|QFP|LCC|PLCC|BGA|SOT|SOD|"
    r"TO-?\d|DPAK|D2PAK|SMB|SMC|DO-?\d|MELF|SC-?\d", re.I)
PKG_PIN_PATTERNS = (
    re.compile(r"(?:LQFP|TQFP|QFN|DFN|SOIC|SOP|SSOP|TSSOP|MSOP|DIP|PDIP|CDIP|QFP|LCC|PLCC|BGA|SOT-?23|TO-?220|TO-?252|TO-?263|DPAK|D2PAK|SMB|SMC|DO-?214|DO-?201)[-_ ]?(\d{1,3})\b", re.I),
    re.compile(r"\b(\d{1,3})[-_ ]?(?:PIN|LEAD|PINS|P)\b", re.I),
)
DESCR_PIN_PATTERNS = (
    re.compile(r"(?:LQFP|TQFP|QFN|DFN|SOIC|SOP|SSOP|TSSOP|MSOP|DIP|PDIP|QFP|BGA|SOT-?23)[-_ ]?(\d{1,3})\b", re.I),
    re.compile(r"(\d{1,3})\s*(?:PINS?|针|脚)\b", re.I),
)

# Categories worth keeping for a chip-SELECTION dataset. The raw snapshot is dominated by
# Connectors (17647) / passives, which have no meaningful substitution semantics.
SEMI_CATEGORIES = (
    "Power Management", "Interface ICs", "Amplifiers and Comparators", "Logic",
    "Sensors", "Motor Driver ICs", "Embedded Processors and Controllers", "Memory",
    "Data Converters", "Clock and Timing", "RF and Wireless", "Signal Isolation Devices",
    "Signal Isolation", "Logic ICs", "Displays and LED Drivers", "Transistors and Thyristors",
    "Diodes", "Circuit Protection", "Optoelectronics", "Power Modules", "IoT / Communication Modules",
    "Silicon Carbide (Si C) Devices", "Gallium Nitride (GaN) Devices", "Optocouplers / Photocouplers",
)
DOMESTIC_HINTS = ("Geehy", "WCH", "STC", "Nation", "Nations", "HDSC", "ChipON", "MindMotion",
                  "GigaDevice", "SGMicro", "SGM", "Maxic", "Silergy", "Southchip", "Joulwatt",
                  "Injoinic", "ESPRESSIF", "Espressif", "Beken", "Belling", "3Peak", "SGMC",
                  "China", "Fudan", "Unicmicro", "Cmsemicon", "Run-ic", "Nexperia? China")


def _num(value):
    """Coerce a LUT value to float, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            n = float(value.strip().rstrip("%"))
        except ValueError:
            return None
        return n if math.isfinite(n) else None
    return None


def load_lut(tar: tarfile.TarFile) -> list[list]:
    name = next(n for n in tar.getnames() if "attribute" in n)
    raw = gzip.decompress(tar.extractfile(name).read()).decode("utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def load_subcategories(tar: tarfile.TarFile) -> dict[int, tuple[str, str]]:
    """Return {subcategoryIdx: (subcategory, category)}.

    Verified structure: subcategories.jsonlines.gz has 419 lines -- line 0 is the column
    map {"subcategory":0,"category":1,"subcategoryIdx":2}, then 418 rows whose
    subcategoryIdx runs 1..418 (DELIBERATELY 1-based, not 0-based), and each row's
    subcategoryIdx also matches the <n> of the sibling components-<n>.jsonlines.gz member.
    """
    name = next(n for n in tar.getnames() if "subcat" in n)
    lines = gzip.decompress(tar.extractfile(name).read()).decode("utf-8").splitlines()
    colmap = json.loads(lines[0])
    out: dict[int, tuple[str, str]] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        row = json.loads(line)
        out[int(row[colmap["subcategoryIdx"]])] = (
            str(row[colmap["subcategory"]]),
            str(row[colmap["category"]]),
        )
    return out


PLACEHOLDER_RE = re.compile(r"\$\{([^}]+)\}")
def _resolve_numbers(meta: dict) -> list[float]:
    """All numeric values the attribute's `format` template actually renders.

    `values[primary]` alone is NOT the full value: e.g. Operating Temperature has
    format "${temperature min} ~ ${temperature max}" and primary "temperature min", so
    resolving every named placeholder is what recovers both ends of the range.
    """
    values = meta.get("values") or {}
    names = PLACEHOLDER_RE.findall(meta.get("format") or "")
    if not names:
        primary = meta.get("primary")
        if primary in values:
            names = [primary]
    out = []
    for name in names:
        payload = values.get(name)
        if isinstance(payload, list) and payload:
            n = _num(payload[0])
            if n is not None:
                out.append(n)
    return out


def collect_attributes(lut: list[list], attrs_idx: list[int]) -> dict:
    """Map attribute name -> {"values", "nums", "primary", "format"} for one component.

    `attrsIdx` is a list of ABSOLUTE line numbers into the LUT. Verified on the real
    snapshot: the numbers are NOT guaranteed to be sorted or contiguous (one component's
    list reads [271, 272, ..., 14, 283]), so every index must be looked up on its own --
    do NOT iterate as `lut[attrsIdx[0] + offset]`.
    """
    out: dict[str, dict] = {}
    for i in attrs_idx or []:
        try:
            entry = lut[int(i)]
        except (TypeError, ValueError, IndexError):
            continue
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        name, meta = entry[0], entry[1]
        if not isinstance(meta, dict) or name in out:
            continue
        payload = (meta.get("values") or {}).get(meta.get("primary")) if meta.get("primary") else None
        out[name] = {
            "values": meta.get("values") or {},
            "primary": meta.get("primary"),
            "format": meta.get("format") or "",
            "nums": _resolve_numbers(meta),
            "first": payload[0] if isinstance(payload, list) and payload else None,
        }
    return out


# --- plausibility filters for the unit-type fallback -------------------------------
# A snapshot-wide scan of attributes shows that a bare "voltage" unit can also be a
# Breakdown / Clamping / Reverse / Threshold rating, which is NOT an operating supply
# range. These word filters keep the fallback honest; the explicit key list is tried first.
VCC_BAD_WORDS = ("breakdown", "clamp", "reverse", "threshold", "esd", "surge",
                 "dissipation", "isolation", "withstand", "dropout", "ripple",
                 "reference", "tolerance", "coefficient", "noise", "gain")
VCC_GOOD_WORDS = ("supply", "operating", "input", "output", "voltage")
TEMP_BAD_WORDS = ("coefficient", "color", "conversion", "resolution", "tolerance",
                  "hysteresis", "stability", "drift", "accuracy", "bleaching",
                  "detection", "limit", "resistance", "frequency")
TEMP_GOOD_WORDS = ("operating", "working", "junction", "ambient", "temperature", "range")


def _plausible_vcc(nums: list[float]) -> bool:
    """Supply voltage plausibility: positive and within the range seen in real silicon."""
    if not nums:
        return False
    return all(0.5 <= n <= 1500 for n in nums)


def _plausible_temp(nums: list[float]) -> bool:
    """Temperature plausibility: Celsius, within what any packaged part tolerates."""
    if not nums:
        return False
    return all(-100 <= n <= 400 for n in nums)


def _name_filter(good_words, bad_words):
    def check(name: str) -> bool:
        low = name.lower()
        if any(w in low for w in bad_words):
            return False
        return any(w in low for w in good_words)
    return check


def attr_range(attrs: dict, keys, min_key, max_key, row, unit_types=(), name_ok=None):
    """Fill row[min_key]/row[max_key] for the first matching attribute.

    Two things learned from the real snapshot:
      1. `values[primary]` is only ONE number. For "Operating Temperature" the format is
         "${temperature min} ~ ${temperature max}" while primary is "temperature min", so
         reading the primary alone silently drops the maximum. We therefore resolve every
         placeholder named in `format` and take min/max of all numeric values.
      2. Attribute names vary per subcategory, so `keys` is only a priority list; when it
         misses we fall back to `unit_types` (the LUT tags each value with a unit such as
         "voltage" / "temperature") filtered by `name_ok`.
    """
    candidates = [k for k in keys if k in attrs]
    if not candidates and unit_types:
        for name, meta in attrs.items():
            payload = meta.get("values") or {}
            if any((v[1] if isinstance(v, list) and len(v) > 1 else None) in unit_types
                   for v in payload.values()):
                candidates.append(name)

    for key in candidates:
        vals = [n for n in (attrs[key].get("nums") or []) if n is not None]
        if name_ok and not name_ok(key, vals):
            continue
        if len(vals) >= 2:
            row[min_key], row[max_key] = min(vals), max(vals)
        elif len(vals) == 1:
            row[min_key] = vals[0]
        return row
    return row


def _plausible_vcc_name(name: str, nums: list[float]) -> bool:
    return _name_filter(VCC_GOOD_WORDS, VCC_BAD_WORDS)(name) and _plausible_vcc(nums)


def _plausible_temp_name(name: str, nums: list[float]) -> bool:
    return _name_filter(TEMP_GOOD_WORDS, TEMP_BAD_WORDS)(name) and _plausible_temp(nums)


def attr_number(attrs: dict, keys):
    for key in keys:
        if key in attrs:
            nums = attrs[key].get("nums") or []
            for n in nums:
                if n is not None and not math.isnan(n):
                    return n
    return None


def normalize_package(raw: str) -> str:
    """Turn jlcparts' package/pitch mix into a comparable package token.

    Observed values include "插件,P=7.62mm", "SOT-23-5", "MSOP-10-EP", "0603", "-".
    We keep the machine-comparable package name when one is present and fall back to the
    original string otherwise (e.g. passives that only carry an imperial size code).
    """
    text = (raw or "").strip()
    if not text or text == "-":
        return text
    parts = [p.strip() for p in re.split(r"[,，]", text) if p.strip()]
    real = [p for p in parts if not re.fullmatch(r"P\s*=\s*[\d.]+\s*(?i:mm)", p)]
    for p in real:
        if PKG_TOKEN_RE.search(p):
            return p
    return (real[0] if real else text)


def pins_from_description(description: str):
    """Fallback pin count from a description like "... DIP-4 ..." or "41 Pin"."""
    if not description:
        return None
    for pat in DESCR_PIN_PATTERNS:
        m = pat.search(description)
        if m:
            return int(m.group(1))
    return None


def guess_pins(package: str, attrs: dict, description: str = ""):
    """Pin count from the attribute, the package string, or finally the description.

    The "Number of Pins" attribute exists for only 13 of 43102 LUT entries, so the package
    string (e.g. "SOIC-8", "LQFP48", "SOT-23-5") is the practical source.
    """
    n = attr_number(attrs, PIN_KEYS)
    if n:
        return int(n)
    if package:
        for pat in PKG_PIN_PATTERNS:
            m = pat.search(package)
            if m:
                return int(m.group(1))
    return pins_from_description(description)


def guess_domestic(manufacturer: str) -> str:
    low = (manufacturer or "").lower()
    for hint in DOMESTIC_HINTS:
        if hint.lower() in low:
            return "1"
    return "0"


def representative_price(price_tiers):
    """Lowest listed tier, which is what a production buyer actually pays."""
    if not isinstance(price_tiers, list) or not price_tiers:
        return None
    prices = []
    for tier in price_tiers:
        if isinstance(tier, dict):
            p = _num(tier.get("price"))
            if p is not None:
                prices.append(p)
    return min(prices) if prices else None


def build(tar_path: Path, out_path: Path, limit: int | None = None,
          per_subcategory: int | None = None, categories=None) -> dict:
    tar = tarfile.open(tar_path, "r")
    lut = load_lut(tar)
    subcats = load_subcategories(tar)
    comp_names = sorted((n for n in tar.getnames() if n.startswith("components-")),
                        key=lambda n: int(re.search(r"(\d+)", n.rsplit("-", 1)[1]).group(1)))

    fields = ["part_no", "manufacturer", "category", "subcategory", "package", "pin_count",
              "vcc_min", "vcc_max", "temp_min", "temp_max", "stock", "price_cny",
              "lead_time_days", "lifecycle", "description", "datasheet_url", "is_domestic"]

    seen: set[str] = set()
    keep_cats = set(categories or ())
    stats = {"rows_in": 0, "rows_out": 0, "dup": 0, "no_manufacturer": 0,
             "no_pins": 0, "no_voltage": 0, "no_temp": 0, "skipped_category": 0,
             "categories_seen": set()}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()

        for name in comp_names:
            if limit and stats["rows_out"] >= limit:
                break
            sub_seen = 0
            raw = gzip.decompress(tar.extractfile(name).read()).decode("utf-8")
            lines = raw.splitlines()
            if not lines:
                continue
            colmap = json.loads(lines[0])
            for line in lines[1:]:
                if not line.strip():
                    continue
                if limit and stats["rows_out"] >= limit:
                    break
                if per_subcategory and sub_seen >= per_subcategory:
                    break
                stats["rows_in"] += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                part_no = str(rec[colmap["mfr"]]).strip()
                if not part_no or part_no in seen:
                    stats["dup"] += 1
                    continue

                attrs = collect_attributes(lut, rec[colmap["attrsIdx"]])
                sub = rec[colmap["subcategoryIdx"]]
                subcat_name, category_name = subcats.get(int(sub), ("", ""))
                stats["categories_seen"].add(category_name)
                if keep_cats and category_name not in keep_cats:
                    stats["skipped_category"] += 1
                    continue

                pack = ""
                if "Package" in attrs:
                    pack = str(attrs["Package"]["first"] or "").strip()
                subcat_name = subcat_name or ""
                # jlcparts mixes a real package name with a pitch note ("插件,P=1.2mm");
                # normalize_package keeps the comparable token and falls back to the raw
                # string for passives that only carry a size code.
                package = normalize_package(pack) if pack else normalize_package(subcat_name)

                manufacturer = ""
                if "Manufacturer" in attrs:
                    manufacturer = str(attrs["Manufacturer"]["first"] or "").strip()
                if not manufacturer:
                    stats["no_manufacturer"] += 1

                row = {
                    "part_no": part_no,
                    "manufacturer": manufacturer,
                    "category": category_name,
                    "subcategory": subcat_name,
                    "package": package,
                    "pin_count": "",
                    "vcc_min": "", "vcc_max": "",
                    "temp_min": "", "temp_max": "",
                    "stock": rec[colmap["stock"]] if colmap.get("stock") is not None else "",
                    "price_cny": "",
                    "lead_time_days": "",   # not provided by this source
                    "lifecycle": "",        # not provided by this source
                    "description": re.sub(r"\s+", " ", str(rec[colmap["description"]])).strip(),
                    "datasheet_url": rec[colmap["datasheet"]] or "",
                    "is_domestic": guess_domestic(manufacturer),
                }

                pins = guess_pins(package, attrs, row["description"])
                if pins:
                    row["pin_count"] = pins
                else:
                    stats["no_pins"] += 1

                attr_range(attrs, VCC_KEYS, "vcc_min", "vcc_max", row,
                           unit_types=("voltage",), name_ok=_plausible_vcc_name)
                attr_range(attrs, TEMP_KEYS, "temp_min", "temp_max", row,
                           unit_types=("temperature", "kelvin"), name_ok=_plausible_temp_name)
                if row["vcc_min"] == "":
                    stats["no_voltage"] += 1
                if row["temp_min"] == "":
                    stats["no_temp"] += 1

                price = representative_price(rec[colmap["price"]])
                if price is not None:
                    row["price_cny"] = round(price, 4)

                writer.writerow(row)
                seen.add(part_no)
                stats["rows_out"] += 1
                sub_seen += 1

    tar.close()
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a chips CSV from a jlcparts tar snapshot.")
    ap.add_argument("--tar", default=str(ROOT / "data" / "samples" / "jlcparts-all.jsonlines.tar"),
                    help="path to all.jsonlines.tar")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output CSV path")
    ap.add_argument("--limit", type=int, default=None, help="stop after N rows (for a smoke test)")
    ap.add_argument("--per-subcategory", type=int, default=None,
                    help="keep at most N parts per subcategory (balanced sample)")
    ap.add_argument("--categories", default=None,
                    help="comma-separated category allow-list, or 'semi' for the built-in "
                         "semiconductor/IC subset (drops Connectors, passives, ...)")
    ap.add_argument("--list-categories", action="store_true",
                    help="print every category in the snapshot and exit")
    args = ap.parse_args()

    tar_path = Path(args.tar)
    if not tar_path.exists():
        print(f"[X] tar not found: {tar_path}", file=sys.stderr)
        print("    download it first, e.g.:")
        print("    python scripts/fetch_dataset.py --url https://dougy83.github.io/jlcparts/data/all.jsonlines.tar")
        return 2

    if args.list_categories:
        with tarfile.open(tar_path, "r") as tar:
            subcats = load_subcategories(tar)
        counts = {}
        for _, (_sub, cat) in subcats.items():
            counts[cat] = counts.get(cat, 0) + 1
        for cat, n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"{n:6d}  {cat}")
        return 0

    categories = None
    if args.categories == "semi":
        categories = SEMI_CATEGORIES
    elif args.categories:
        categories = tuple(c.strip() for c in args.categories.split(",") if c.strip())

    stats = build(tar_path, Path(args.out), args.limit, args.per_subcategory, categories)
    print(f"wrote {args.out}")
    print(f"  components read : {stats['rows_in']}")
    print(f"  rows written    : {stats['rows_out']}  (skipped {stats['dup']} dup/empty, "
          f"{stats['skipped_category']} out-of-scope category)")
    print(f"  missing mfr     : {stats['no_manufacturer']}")
    print(f"  missing pins    : {stats['no_pins']}")
    print(f"  missing voltage : {stats['no_voltage']}")
    print(f"  missing temp    : {stats['no_temp']}")
    if categories:
        missing = [c for c in categories if c not in stats["categories_seen"]]
        if missing:
            print(f"  [!] allow-list entries not found in snapshot: {missing}")
    print("  note: lead_time_days and lifecycle are intentionally EMPTY (not in this source)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
