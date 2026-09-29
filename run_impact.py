"""Impact sound insulation L'nT,w from three SVL files.

    python run_impact.py
    python run_impact.py --tapping samples/B_L4.SVL --background samples/C_L20.SVL \
        --rt samples/B_L11.SVL --rt-kind t30

Each option accepts several files (positions / decays); they are averaged.
"""
import argparse
from pathlib import Path

from calc.impact import compute_impact
from calc.iso717 import BANDS

S = Path(__file__).parent / "samples"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tapping", nargs="+", default=[S / "B_L4.SVL"])
    ap.add_argument("--background", nargs="+", default=[S / "C_L20.SVL"])
    ap.add_argument("--rt", nargs="+", default=[S / "B_L11.SVL"])
    ap.add_argument("--rt-kind", default="t30", choices=["edt", "t20", "t30"])
    a = ap.parse_args()
    files = [p for group in (a.tapping, a.background, a.rt) for p in group]
    missing = [str(p) for p in files if not Path(p).exists()]
    if missing:
        raise SystemExit("File(s) not found: " + ", ".join(missing) +
                         "\n(samples/ is git-ignored; copy your .SVL files into it "
                         "or pass paths with --tapping/--background/--rt)")
    r = compute_impact(a.tapping, a.background, a.rt, a.rt_kind)
    print(f"{'Hz':>5} {'Li':>6} {'Lb':>6} {'Licorr':>7} {'status':<9} {'T':>6} {'L\'nT':>6}")
    for i, f in enumerate(BANDS):
        print(f"{f:5d} {r.li_raw[i]:6.1f} {r.lb[i]:6.1f} {r.li[i]:7.1f} "
              f"{r.status[i]:<9} {r.t[i]:6.3f} {r.lnt[i]:6.1f}")
    if r.rating is None:
        print("\nRating not possible: reverberation time missing in some bands")
    else:
        print(f"\nL'nT,w (CI) = {r.rating.value} ({r.ci}) dB   L'nT,w + CI = "
              f"{r.rating.value + r.ci} dB")
        print(f"(T = {a.rt_kind.upper()}, curve shift "
              f"{r.rating.shift:+d} dB, unfavourable sum {r.rating.unfavourable_sum:.1f} dB)")


if __name__ == "__main__":
    main()
