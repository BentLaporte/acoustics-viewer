"""Airborne sound insulation DnT,w (C; Ctr) from four SVL files.

    python run_airborne.py
    python run_airborne.py --source samples/A_L2.SVL --receiver samples/B_L2.SVL \
        --background samples/C_L20.SVL --rt samples/B_L11.SVL --rt-kind t30
"""
import argparse
from pathlib import Path

from calc.iso16283 import dnt
from calc.iso717 import BANDS, airborne_summary
from calc.levels import background_correction
from svl.parser import ISO_SLICE, read_svl
from svl.rt import read_rt

S = Path(__file__).parent / "samples"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=S / "A_L2.SVL")
    ap.add_argument("--receiver", default=S / "B_L2.SVL")
    ap.add_argument("--background", default=S / "C_L20.SVL")
    ap.add_argument("--rt", default=S / "B_L11.SVL")
    ap.add_argument("--rt-kind", default="t30", choices=["edt", "t20", "t30"])
    a = ap.parse_args()
    missing = [str(p) for p in (a.source, a.receiver, a.background, a.rt)
               if not Path(p).exists()]
    if missing:
        raise SystemExit("File(s) not found: " + ", ".join(missing) +
                         "\n(samples/ is git-ignored; copy your .SVL files into it "
                         "or pass paths with --source/--receiver/--background/--rt)")

    l1 = read_svl(a.source).leq_total()[ISO_SLICE]
    l2 = read_svl(a.receiver).leq_total()[ISO_SLICE]
    lb = read_svl(a.background).leq_total()[ISO_SLICE]
    t = read_rt(a.rt).at(BANDS, a.rt_kind)

    l2c, status = background_correction(l2, lb)
    d = dnt(l1, l2c, t)

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
