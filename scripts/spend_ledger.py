#!/usr/bin/env python
"""Spend ledger (C-7.1 early wiring): log AI call costs to a running JSONL.

Usage:
  Log an entry:  python scripts/spend_ledger.py log --model veo-3.1-fast \
                     --op bg-swap --units 8 --unit-type seconds --est-usd 1.20
  Show totals:   python scripts/spend_ledger.py total

The ledger is committed to docs/evidence/spend/ledger.jsonl (evidence pack,
C-3.5). Estimates are logged at call time; real billing export (when enabled
in console) reconciles later. Budget alert ($50) stays the hard backstop.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "evidence" / "spend" / "ledger.jsonl"

# Public list prices (USD), paid tier, draft/fast tier where applicable.
# Kept coarse on purpose: the ledger logs estimates; billing export reconciles.
PRICE_TABLE = {
    "veo-3.1-fast-generate-001": {"seconds": 0.15},
    "veo-3.1-generate-001": {"seconds": 0.40},
    "gemini-omni-1.1-flash-preview": {"second": 0.15, "request": 0.01},
    "gemini-3.7-flash": {"request": 0.0005},
    "gemini-2.5-flash-preview-tts": {"request": 0.002},
    "gemini-3.1-flash-image": {"image": 0.02},
    "texttospeech-chirp3-hd": {"request": 0.003},
}


def log_entry(args: argparse.Namespace) -> int:
    est = args.est_usd
    if est is None:
        prices = PRICE_TABLE.get(args.model, {})
        unit_price = prices.get(args.unit_type, 0.0)
        est = round(unit_price * args.units, 4)
    entry = {
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "model": args.model,
        "op": args.op,
        "units": args.units,
        "unit_type": args.unit_type,
        "est_usd": round(est, 4),
        "note": args.note or "",
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"logged: {args.model} {args.op} est=${entry['est_usd']}")
    return 0


def show_total(_: argparse.Namespace) -> int:
    if not LEDGER.exists():
        print("ledger empty (no entries yet)")
        return 0
    total = 0.0
    by_model: dict[str, float] = {}
    count = 0
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        usd = float(entry.get("est_usd", 0.0))
        total += usd
        by_model[entry["model"]] = by_model.get(entry["model"], 0.0) + usd
        count += 1
    print(f"entries: {count}")
    print(f"estimated total: ${total:.2f}")
    for model, usd in sorted(by_model.items(), key=lambda kv: -kv[1]):
        print(f"  {model}: ${usd:.2f}")
    budget = 50.0
    pct = total / budget * 100
    print(f"budget: ${budget:.0f} ({pct:.1f}% used)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    log_p = sub.add_parser("log")
    log_p.add_argument("--model", required=True)
    log_p.add_argument("--op", required=True)
    log_p.add_argument("--units", type=float, required=True)
    log_p.add_argument("--unit-type", default="request")
    log_p.add_argument("--est-usd", type=float, default=None)
    log_p.add_argument("--note", default="")
    sub.add_parser("total")
    args = parser.parse_args()
    if args.cmd == "log":
        return log_entry(args)
    return show_total(args)


if __name__ == "__main__":
    sys.exit(main())
