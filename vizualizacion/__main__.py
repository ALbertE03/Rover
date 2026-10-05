import argparse
from pathlib import Path

from .build_terrain import build_html


def _main() -> None:
    ap = argparse.ArgumentParser(description="Visualize terrains from the generator.")
    ap.add_argument("--seeds", default="7",
                    help="comma-separated seeds (default: 7)")
    ap.add_argument("--width", type=int, default=64)
    ap.add_argument("--height", type=int, default=64)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--pois", type=int, default=10)
    ap.add_argument("--config", default=None, help="alternate config JSON")
    ap.add_argument("--title", default="Terrenos del rover")
    ap.add_argument("-o", "--out", default="terrains.html")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    out = build_html(
        seeds,
        width=args.width, height=args.height, depth=args.depth,
        poi_count=args.pois,
        config_path=Path(args.config) if args.config else None,
        title=args.title, out=Path(args.out),
    )
    print(f"OK -> {out} ({len(seeds)} maps)")


if __name__ == "__main__":
    _main()
