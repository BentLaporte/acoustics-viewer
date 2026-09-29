"""Airborne sound insulation DnT,w (C; Ctr) from four SVL files.

    python run_airborne.py
    python run_airborne.py --source samples/A_L2.SVL --receiver samples/B_L2.SVL \
        --background samples/C_L20.SVL --rt samples/B_L11.SVL --rt-kind t30

Each option accepts several files (positions / decays); they are averaged.
"""
import argparse
from pathlib import Path

from calc.airborne import compute_airborne
from calc.iso717 import BANDS, airborne_summary

S = Path(__file__).parent / "samples"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", nargs="+", default=[S / "A_L2.SVL"])
    ap.add_argument("--receiver", nargs="+", default=[S / "B_L2.SVL"])
    ap.add_argument("--background", nargs="+", default=[S / "C_L20.SVL"])
    ap.add_argument("--rt", nargs="+", default=[S / "B_L11.SVL"])
    ap.add_argument("--rt-kind", default="t30", choices=["edt", "t20", "t30"])
    a = ap.parse_args()
    files = [p for group in (a.source, a.receiver, a.background, a.rt) for p in group]
    missing = [str(p) for p in files if not Path(p).exists()]
    if missing:
        raise SystemExit("File(s) not found: " + ", ".join(missing) +
                         "\n(samples/ is git-ignored; copy your .SVL files into it "
                         "or pass paths with --source/--receiver/--background/--rt)")

    res = compute_airborne(a.source, a.receiver, a.background, a.rt, a.rt_kind)
    l1, l2, lb, l2c, status, t, d = (res.l1, res.l2_raw, res.lb, res.l2, res.status,
                                     res.t, res.dnt)

    print(f"{'Hz':>5} {'L1':>6} {'L2':>6} {'Lb':>6} {'L2corr':>7} {'status':<9} "
          f"{'T':>6} {'DnT':>6}")
    for i, f in enumerate(BANDS):
        print(f"{f:5d} {l1[i]:6.1f} {l2[i]:6.1f} {lb[i]:6.1f} {l2c[i]:7.1f} "
              f"{status[i]:<9} {t[i]:6.3f} {d[i]:6.1f}")
    r = airborne_summary(d)
    print(f"\nDnT,w = {r['w']} dB   C = {r['C']}   Ctr = {r['Ctr']}   "
          f"(T = {a.rt_kind.upper()})")


if __name__ == "__main__":
    main()
