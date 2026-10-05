"""CLI: python -m vizualizacion --seeds 7,55,188 -o terrenos.html

Llama al generador y escribe el HTML con el pipeline de cada terreno.
Sin simulación: solo terrenos.
"""
import argparse
from pathlib import Path

from .terreno import build_html


def _main() -> None:
    ap = argparse.ArgumentParser(description="Visualiza terrenos del generador.")
    ap.add_argument("--seeds", default="7",
                    help="seeds separadas por coma (default: 7)")
    ap.add_argument("--width", type=int, default=64)
    ap.add_argument("--height", type=int, default=64)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--pois", type=int, default=10)
    ap.add_argument("--config", default=None, help="config JSON alternativa")
    ap.add_argument("--title", default="Terrenos del rover")
    ap.add_argument("-o", "--out", default="terrenos.html")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    out = build_html(
        seeds,
        width=args.width, height=args.height, depth=args.depth,
        poi_count=args.pois,
        config_path=Path(args.config) if args.config else None,
        title=args.title, out=Path(args.out),
    )
    print(f"OK -> {out} ({len(seeds)} mapas)")


if __name__ == "__main__":
    _main()
