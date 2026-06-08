"""CLI:  peripage-a40 print <pdf> --mac <addr>   |   build <pdf> -o job.bin"""
from __future__ import annotations
import argparse
import sys
from .job import render_pdf_job, print_pdf
from .transport import PrinterAsleep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="peripage-a40",
        description="App-free PeriPage A40 native page-mode printing")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("print", help="render + print a PDF")
    p.add_argument("pdf")
    p.add_argument("--mac", required=True)
    p.add_argument("--no-dither", action="store_true")
    p.add_argument("--channel", type=int, default=1)

    b = sub.add_parser("build", help="render a PDF to a raw job .bin (no printer)")
    b.add_argument("pdf")
    b.add_argument("-o", "--out", required=True)
    b.add_argument("--no-dither", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "build":
        stream, n = render_pdf_job(args.pdf, dither=not args.no_dither)
        with open(args.out, "wb") as f:
            f.write(stream)
        print(f"{n} page(s), {len(stream)} bytes -> {args.out}")
        return 0

    if args.cmd == "print":
        try:
            n = print_pdf(args.pdf, args.mac, dither=not args.no_dither,
                          channel=args.channel)
        except PrinterAsleep as e:
            print(f"ASLEEP: {e}", file=sys.stderr)
            return 3
        print(f"printed {n} page(s)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
