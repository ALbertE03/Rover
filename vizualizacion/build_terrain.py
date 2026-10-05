import json
from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Dict, List, Optional,Tuple

from enviro.config import load_config
from enviro.terrain import (
    InstanceParams,
    MapGenerator,
    cell_id,
    parse_cell_id,
)


def _station_count(config_path: Optional[Path]) -> int:
    cfg = load_config(config_path)
    return len(cfg["network"]["stations"])


def pipeline_data(seed: int, width: int = 64, height: int = 64, depth: int = 3,
                  poi_count: int = 10,
                  config_path: Optional[Path] = None) -> Dict:
    """Generate one map and return everything needed to draw it."""
    params = InstanceParams(seed=seed, width=width, height=height,
                            depth=depth, poi_count=poi_count,
                            station_count=_station_count(config_path))
    if config_path is not None:
        params = replace(params, config_path=Path(config_path))
    gen = MapGenerator(params)
    m = gen.create()
    field = gen.field
    hm = field.heightmap()

    def sid(x: int, y: int) -> str:
        return cell_id(x, y, hm[x][y])

    terrain: Dict[str, str] = {}
    boulders: List[List[int]] = []
    for x in range(width):
        for y in range(height):
            c = m.cell(sid(x, y))
            terrain[f"{x},{y}"] = c.true_terrain if c else "?"
            if c is not None and c.blocked:
                boulders.append([x, y])

    mix: Dict[str, int] = {}
    for name in terrain.values():
        mix[name] = mix.get(name, 0) + 1

    # Quantization report. Everything below is derived from the two public
    # entry points of the field (noise_pipeline, heightmap) plus the contrast
    # knob, so the page can explain the arithmetic without the generator
    # having to expose a second, parallel copy of it.
    nz = field.noise_pipeline()
    combined: List[List[float]] = nz["combined"]
    contrast = float(field.height_contrast)
    span = max(1, depth - 1)

    def layer_of(value: float, scale: float) -> int:
        """The one line of arithmetic this whole page is about."""
        stretched = 0.5 + (value - 0.5) * scale
        capped = max(0.0, min(1.0, stretched))
        return max(0, min(depth - 1, int(capped * span + 0.5)))

    flat_avg = [v for row in combined for v in row]
    flat_post = [0.5 + (v - 0.5) * contrast for v in flat_avg]
    hist = [0] * depth
    for row in hm:
        for z in row:
            hist[z] += 1

    # Ground features. Placement order decides the mark: the first station is
    # the main base (B) and any relay after it is R. Both are always surface
    # cells, so the plan view at (x, y) is the right place to draw them.
    stations = [
        {"id": s.id, "x": s.center[0], "y": s.center[1], "z": s.center[2],
         "radius": s.radius, "signal": s.signal, "main": index == 0}
        for index, s in enumerate(m.stations)
    ]
    pois = []
    for poi in m.pois.values():
        px, py, pz = parse_cell_id(poi.cell_id)
        pois.append({"id": poi.id, "x": px, "y": py, "z": pz,
                     "interest": poi.interest,
                     "min_visibility": poi.min_visibility})

    # Terrain catalogue: dynamic, so new types in config appear automatically.
    # Color: from config if present, else deterministic palette by name.
    _PALETTE = [(74, 124, 89), (201, 162, 39), (107, 114, 128), (31, 41, 55),
                (180, 80, 80), (80, 140, 180), (140, 80, 180), (180, 140, 80)]
    cat = []
    for idx, name in enumerate(sorted(gen.config["terrain"].keys())):
        spec = gen.config["terrain"][name]
        if "color" in spec:
            rgb = _hex(spec["color"])
        else:
            rgb = _PALETTE[idx % len(_PALETTE)]
        cat.append({
            "name": name,
            "cost": float(spec["cost"]),
            "visibility": float(spec["visibility"]),
            "color": "#%02x%02x%02x" % rgb,
            "rgb": rgb,
        })

    # ---- Extended statistics ----
    import math
    n = width * height
    flat_h = [z for row in hm for z in row]
    h_mean = sum(flat_h) / n
    h_var = sum((z - h_mean) ** 2 for z in flat_h) / n
    # roughness: mean |dz| between 4-neighbors
    diffs = []
    for x in range(width):
        for y in range(height):
            if x + 1 < width:
                diffs.append(abs(hm[x][y] - hm[x + 1][y]))
            if y + 1 < height:
                diffs.append(abs(hm[x][y] - hm[x][y + 1]))
    roughness = sum(diffs) / len(diffs) if diffs else 0.0
    # terrain diversity (Shannon entropy, bits)
    entropy = -sum((c / n) * math.log2(c / n)
                   for c in mix.values() if c > 0)
    most = max(mix.items(), key=lambda kv: kv[1]) if mix else ("?", 0)
    least = min(mix.items(), key=lambda kv: kv[1]) if mix else ("?", 0)
    total_science = sum(p["interest"] for p in pois)
    boulder_set = {tuple(b) for b in boulders}

    return {
        "seed": seed, "W": width, "H": height, "depth": depth,
        "noise": nz,
        "block_rate":gen.config['map']['block_rate'],
        "heightmap": hm,
        "terrain": terrain,
        "terrain_mix": mix,
        "terrain_catalogue": cat,
        "boulders": boulders,
        "height_colors": _height_colors(depth),
        "stations": stations,
        "pois": pois,
        # statistics
        "stats": {
            "h_mean": h_mean,
            "h_std": math.sqrt(h_var),
            "h_min": min(flat_h),
            "h_max": max(flat_h),
            "roughness": roughness,
            "entropy": entropy,
            "most_terrain": most[0],
            "most_pct": 100 * most[1] / n,
            "least_terrain": least[0],
            "least_pct": 100 * least[1] / n,
            "total_science": total_science,
            "boulder_pct": 100 * len(boulders) / n,
        },
        # quantization report
        "contrast": contrast,
        "cells": width * height,
        "avg_range": [min(flat_avg), max(flat_avg)],
        "post_range": [min(flat_post), max(flat_post)],
        "clamped_low": sum(1 for v in flat_post if v < 0.0),
        "clamped_high": sum(1 for v in flat_post if v > 1.0),
        "layer_hist": hist,
        "biome_map": [[field.biome_at(x, y) for y in range(height)]
                      for x in range(width)],
        "biome_centers": field.biome_centers,
        "top_layer": max((z for z, n in enumerate(hist) if n), default=0),
        "top_layer_flat": max((layer_of(v, 1.0) for v in flat_avg), default=0),
    }


def _mark(ch: str) -> str:
    """The same glyph the canvas draws, so the legend matches the map."""
    return f"<span class='m'>{ch}</span>"


def _height_colors(depth: int) -> List[str]:
    """Blue -> green -> orange ramp, indexed by z."""
    stops = [(59, 91, 219), (47, 158, 68), (230, 119, 0)]
    colors = []
    for z in range(depth):
        t = z / max(1, depth - 1) * (len(stops) - 1)
        i = min(int(t), len(stops) - 2)
        f = t - i
        r = round(stops[i][0] + (stops[i + 1][0] - stops[i][0]) * f)
        g = round(stops[i][1] + (stops[i + 1][1] - stops[i][1]) * f)
        b = round(stops[i][2] + (stops[i + 1][2] - stops[i][2]) * f)
        colors.append(f"#{r:02x}{g:02x}{b:02x}")
    return colors


def _quant_report(e: Dict) -> str:
    """The quantization explained, with this map's own numbers.

    The prose is generic but every figure in it is measured for this entry, so
    the page never asserts something the map above it does not show.
    """
    depth = e["depth"]
    if depth < 2:
        return ("<div class='note'><b>Informe de cuantización</b><br>"
                f"Con <code>depth={depth}</code> todas las columnas quedan en z=0 "
                "y no hay nada que cuantizar.</div>")

    span = depth - 1
    cells = e["cells"] or 1
    hist = e["layer_hist"]
    pinned = e["clamped_low"] + e["clamped_high"]
    a_lo, a_hi = e["avg_range"]
    p_lo, p_hi = e["post_range"]

    rows = []
    for z in range(depth):
        lo = max(0.0, (z - 0.5) / span)
        hi = min(1.0, (z + 0.5) / span)
        share = hist[z] / cells
        color = e["height_colors"][z]
        rows.append(
            f"<tr><td><span style='color:{color}'>\u25a0</span> z={z}</td>"
            f"<td><code>n &isin; [{lo:.3f}, {hi:.3f})</code></td>"
            f"<td class='bar'><span style='width:{share * 100:.2f}%;"
            f"background:{color}'></span></td>"
            f"<td class='num'>{hist[z]}</td><td class='num'>{share:.1%}</td></tr>")

    if e["top_layer_flat"] < e["top_layer"]:
        stretch = (f"El estiramiento es lo que llega a z={e['top_layer']}: con "
                   f"<code>height_contrast={e["contrast"]}</code> este mapa se queda en "
                   f"z={e['top_layer_flat']} y la capa alta saldría vacía.")
    else:
        stretch = (f"Con depth={depth} el estiramiento no es lo que llega a "
                   f"z={e['top_layer']}: <code>height_contrast={e["contrast"]}</code> también "
                   f"llega (z={e['top_layer_flat']}). Lo que cambia es cómo se reparten "
                   f"las columnas, no si la cima existe.")

    return (
        "<div class='note'><b>Informe de cuantización</b>"
        "<table class='kv'>"
        "<tr><td>promedio antes del estiramiento</td>"
        f"<td><code>{a_lo:.3f} &rarr; {a_hi:.3f}</code></td>"
        "<td class='num'>nunca llega a 0 ni a 1</td></tr>"
        "<tr><td>después del estiramiento</td>"
        f"<td><code>{p_lo:.3f} &rarr; {p_hi:.3f}</code></td>"
        "<td class='num'>se pasa por los dos extremos</td></tr>"
        "<tr><td>aplanadas por el recorte</td>"
        f"<td><code>{pinned} / {cells}</code> &rarr; {pinned / cells:.0%}</td>"
        f"<td class='num'>{e['clamped_low']} abajo, {e['clamped_high']} arriba</td></tr>"
        "<tr><td>capa m&aacute;xima alcanzada</td>"
        f"<td><code>z={e['top_layer']}</code> de {span}</td>"
        f"<td class='num'>z={e['top_layer_flat']} sin estirar</td></tr>"
        "</table>"
        f"{stretch}"
        "<table class='kv'>"
        "<tr><th>capa</th><th>intervalo</th><th>parte de las columnas</th>"
        "<th class='num'>celdas</th><th class='num'>parte</th></tr>"
        + "".join(rows) +
        "</table>"
        "</div>")


def _png_b64(img) -> str:
    """PIL image -> base64 data URI."""
    import base64, io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _bar_png(value: float, max_value: float, width: int = 120,
             height: int = 14, color: tuple = (76, 110, 245)) -> str:
    """Pixel bar: filled pixels proportional to value/max_value."""
    from PIL import Image
    img = Image.new("RGB", (width, height), (26, 34, 48))
    px = img.load()
    frac = max(0.0, min(1.0, value / max_value)) if max_value > 0 else 0.0
    filled = int(round(frac * width))
    for x in range(filled):
        for y in range(height):
            px[x, y] = color
    # pixel grid lines every 6px for the "pixel" look
    for x in range(0, width, 6):
        for y in range(height):
            if x < filled:
                px[x, y] = tuple(max(0, c - 40) for c in color)
    return _png_b64(img)


def _gray(v: float) -> tuple:
    g = max(0, min(255, int(round(20 + v * 220))))
    return (g, g, g)


def _hex(h: str) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _map_png(e: Dict, kind: str, scale: int = 10):
    """Render one map panel as a PIL image. No JavaScript needed."""
    from PIL import Image, ImageDraw
    W, H = e["W"], e["H"]
    img = Image.new("RGB", (W * scale, H * scale), (10, 13, 18))
    px = img.load()
    nz = e["noise"]
    if kind == "star":
        data = nz["star"]
        for i in range(W):
            for j in range(H):
                c = _gray(data[i][j])
                for a in range(scale):
                    for b in range(scale):
                        px[i * scale + a, j * scale + b] = c
    elif kind == "blobs":
        data = nz["blobs"]
        for i in range(W):
            for j in range(H):
                c = _gray(data[i][j])
                for a in range(scale):
                    for b in range(scale):
                        px[i * scale + a, j * scale + b] = c
    elif kind == "waves":
        data = nz["waves"]
        for i in range(W):
            for j in range(H):
                c = _gray(data[i][j])
                for a in range(scale):
                    for b in range(scale):
                        px[i * scale + a, j * scale + b] = c
    elif kind == "combined":
        data = nz["combined"]
        for i in range(W):
            for j in range(H):
                c = _gray(data[i][j])
                for a in range(scale):
                    for b in range(scale):
                        px[i * scale + a, j * scale + b] = c
    elif kind == "contrast":
        data = nz["combined"]
        ct = e["contrast"]
        for i in range(W):
            for j in range(H):
                v = max(0.0, min(1.0, 0.5 + (data[i][j] - 0.5) * ct))
                c = _gray(v)
                for a in range(scale):
                    for b in range(scale):
                        px[i * scale + a, j * scale + b] = c
    elif kind == "height":
        colors = [_hex(c) for c in e["height_colors"]]
        hm = e["heightmap"]
        for i in range(W):
            for j in range(H):
                c = colors[hm[i][j]]
                for a in range(scale):
                    for b in range(scale):
                        px[i * scale + a, j * scale + b] = c
    elif kind == "biomes":
        bcol = [(122, 162, 247), (158, 206, 106), (255, 158, 100),
                (186, 110, 220), (100, 200, 200)]
        bm = e["biome_map"]
        for i in range(W):
            for j in range(H):
                b = bm[i][j]
                c = bcol[b % len(bcol)] if b >= 0 else (40, 40, 40)
                for a in range(scale):
                    for b_ in range(scale):
                        px[i * scale + a, j * scale + b_] = c
        # mark centers
        d = ImageDraw.Draw(img)
        for cx, cy in e["biome_centers"]:
            x, y = int(cx * scale), int(cy * scale)
            d.ellipse([x - 5, y - 5, x + 5, y + 5],
                      fill=(255, 255, 255), outline=(0, 0, 0), width=2)
    elif kind == "terrain":
        tcol = {t["name"]: t["rgb"] for t in e["terrain_catalogue"]}
        for i in range(W):
            for j in range(H):
                c = tcol.get(e["terrain"][f"{i},{j}"], (51, 51, 51))
                for a in range(scale):
                    for b in range(scale):
                        px[i * scale + a, j * scale + b] = c
        # boulders as red triangles, stations/POIs as labeled dots
        d = ImageDraw.Draw(img)
        bs = max(4, scale - 2)
        for bx, by in e["boulders"]:
            cx, cy = bx * scale + scale // 2, by * scale + scale // 2
            d.polygon([(cx, cy - bs // 2), (cx - bs // 2, cy + bs // 2),
                       (cx + bs // 2, cy + bs // 2)], fill=(255, 135, 135))
        r = max(5, int(scale * 0.7))
        for s in e["stations"]:
            cx, cy = s["x"] * scale + scale // 2, s["y"] * scale + scale // 2
            col = (126, 240, 160) if s["main"] else (255, 169, 77)
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      fill=(10, 13, 18), outline=col, width=2)
            d.text((cx - 4, cy - 7), "B" if s["main"] else "R", fill=col)
        for p in e["pois"]:
            cx, cy = p["x"] * scale + scale // 2, p["y"] * scale + scale // 2
            col = (199, 146, 234)
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      fill=(10, 13, 18), outline=col, width=2)
            d.text((cx - 4, cy - 7), "O", fill=col)
    return img


def render_html(entries: List[Tuple[Dict,int]], title: str = "Terrenos") -> str:
    """Self-contained HTML showing the pipeline behind every map.

    All visualizations are server-rendered PNGs (no JavaScript needed).
    Tabs use CSS-only radio buttons. Comparison tab is default.
    """
    heading = escape(title)
    parts = []
    parts.append("""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + heading + """</title>
<style>
/* Minimalist dark */
:root{--bg:#111418;--fg:#dfe3e8;--muted:#8a919c;--line:#242b34;--accent:#7aa2f7}
body{font-family:system-ui,-apple-system,sans-serif;max-width:1000px;margin:0 auto;
  padding:24px 20px;background:var(--bg);color:var(--fg);line-height:1.5;
  -webkit-font-smoothing:antialiased}
h1{font-size:22px;font-weight:600;letter-spacing:-.02em;margin:0 0 4px}
h2{font-size:15px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;
  color:var(--muted);margin:32px 0 12px}
h3{font-size:13px;font-weight:600;margin:0 0 10px;color:var(--fg)}
.grid{display:flex;gap:16px;flex-wrap:wrap}
.panel{border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
.panel h3{margin:0 0 12px}
.note{border-left:2px solid var(--line);padding:4px 0 4px 16px;margin:16px 0;
  font-size:13.5px;line-height:1.7;color:var(--muted)}
.note b{color:var(--fg);font-weight:600}
img.viz{border-radius:8px;max-width:100%;image-rendering:pixelated;display:block}
code{font-size:12px;color:var(--muted)}
.legend{font-size:12px;color:var(--muted);margin-top:10px;line-height:2}
ol.steps{margin:8px 0;padding-left:20px;font-size:13.5px}
ol.steps li{margin:6px 0}
table.kv{border-collapse:collapse;margin:12px 0;font-size:12.5px;width:100%}
table.kv th{text-align:left;color:var(--muted);font-weight:600;padding:6px 10px;
  border-bottom:1px solid var(--line);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
table.kv td{padding:6px 10px;border-top:1px solid var(--line);vertical-align:top}
td.num{text-align:right;white-space:nowrap;color:var(--muted)}
td.bar{width:26%}
td.bar span{display:block;height:8px;border-radius:4px;min-width:1px}
.m{display:inline-block;min-width:1em;text-align:center;font-family:ui-monospace,monospace;
  font-weight:700;border-radius:3px;padding:0 3px;margin-right:2px}
.mB{color:#7ef0a0}.mR{color:#ffa94d}.mO{color:#c792ea}.mA{color:#ff8787}
.dim{color:var(--muted);font-size:11.5px}
.feat{margin-top:10px;line-height:2.1}
/* Minimal tabs: text + underline */
.tabinput{display:none}
.tabs{display:flex;gap:4px;margin:20px 0 8px;border-bottom:1px solid var(--line)}
.tabs label{padding:10px 16px;font-size:14px;color:var(--muted);cursor:pointer;
  border-bottom:2px solid transparent;margin-bottom:-1px;transition:color .15s}
.tabs label:hover{color:var(--fg)}
""" + "\n".join(
        f'#t-{e["seed"]}:checked~.tabs label[for="t-{e["seed"]}"],'
        for e in entries) + """
#t-cmp:checked~.tabs label[for="t-cmp"]{color:var(--fg);border-bottom-color:var(--accent);font-weight:600}
.tabsec{display:none}
#t-cmp:checked~#sec-cmp{display:block}
""" + "\n".join(
        f"#t-{e['seed']}:checked~#sec-{e['seed']}{{display:block}}"
        for e in entries) + """
.cmp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;align-items:start}
.cmp-card .stats{font-size:12.5px;margin-top:14px;line-height:1.6}
.stat-row{display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:4px 0;border-bottom:1px solid var(--line)}
.stat-row:last-child{border-bottom:0}
.pxbar{height:12px;border-radius:6px;image-rendering:pixelated;flex-shrink:0;opacity:.9}
.legend-box{border-left-color:var(--accent)}
.leg-item{display:inline-block;margin:0 16px 4px 0;white-space:nowrap;font-size:13px}
.swatch{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;
  vertical-align:-1px}
.panel,.note,.stats,.legend{overflow-wrap:break-word;word-break:break-word}
@media(max-width:600px){
  body{padding:16px 12px}
  h1{font-size:19px}
  .tabs{overflow-x:auto}
  .tabs label{padding:8px 12px;font-size:13px;white-space:nowrap}
  .grid{flex-direction:column}
  .panel{width:100%;box-sizing:border-box;padding:12px}
  .cmp-grid{grid-template-columns:1fr}
}
</style></head><body>
<h1>""" + heading + f"""</h1>
<div class="note">Cada mapa nace de <b>3 ruidos aleatorios</b> (estrella + manchas + ondas)
&rarr; promedio &rarr; contraste &rarr; <b>cuantizaci&oacute;n</b>.
Las <b>rocas \u25b2</b> (<code>block_rate={entries[0]["block_rate"]}</code> por columna) bloquean el paso.</div>

<input type="radio" name="tab" id="t-cmp" class="tabinput" checked>
""" + "\n".join(
        f'<input type="radio" name="tab" id="t-{e["seed"]}" class="tabinput">'
        for e in entries) + """
<div class="tabs">
<label for="t-cmp">Comparaci\u00f3n</label>
""" + "\n".join(
        f'<label for="t-{e["seed"]}">Seed {e["seed"]}</label>'
        for e in entries) + """
</div>
""")

    # ---- Comparison tab (default): final maps side by side + stats ----
    parts.append('<div class="tabsec" id="sec-cmp">')
    parts.append("<h2>Comparaci\u00f3n de terrenos</h2>")

    # Full pipeline explanation (steps 1-8)
    parts.append("""<div class="note">
<b>C\u00f3mo se genera cada mapa, paso a paso:</b>
<ol class="steps">
<li><b>Estrella:</b> ruido radial con 3–5 brazos desde un centro aleatorio.
    Crea la estructura base del relieve.</li>
<li><b>Manchas:</b> 8–14 manchas gaussianas en posiciones aleatorias.
    Aportan variaciones locales suaves.</li>
<li><b>Ondas:</b> 3 ondas sinusoidales direccionales.
    A\u00f1aden ritmo y direcci\u00f3n al terreno.</li>
<li><b>Promedio:</b> se promedian los 3 ruidos normalizados
    <code>n = (estrella + manchas + ondas) / 3</code>.
    El resultado est\u00e1 en [0,1].</li>
<li><b>Contraste:</b> se estira alrededor del punto medio
    <code>n = 0.5 + (n - 0.5) \u00d7 height_contrast</code>
    y se recorta a [0,1]. Esto exagera las diferencias:
    lo alto se vuelve m\u00e1s alto, lo bajo m\u00e1s bajo.</li>
<li><b>Cuantizaci\u00f3n \u2192 altura:</b> cada valor se redondea a la capa
    m\u00e1s cercana <code>h = int(n \u00d7 (depth-1) + 0.5)</code>.
    As\u00ed nacen los niveles z=0, 1, 2... que el rover puede escalar
    (m\u00e1ximo 1 nivel por paso).</li>
<li><b>Biomas:</b> el mapa se divide en 3 regiones Voronoi
    (cada casilla pertenece a su centro m\u00e1s cercano).
    Cada bioma saca un terreno dominante al azar y se ensancha su banda
    de ruido, as\u00ed los terrenos se agrupan en zonas en vez de salir
    salpicados.</li>
<li><b>Terrenos + rocas + lava:</b> con las bandas sesgadas de su bioma,
    cada casilla obtiene su terreno (llanos/arena/roca/grieta).
    Luego se colocan rocas \u25b2 al azar (6% de casillas, bloquean el paso)
    y 2 charcos de lava (c\u00edrculos que queman el terreno a lava y lo
    bloquean). Encima van las bases B/R y los POIs O.</li>
</ol>
</div>""")

    # Dynamic legend: color per terrain type, from the catalogue.
    cat = entries[0]["terrain_catalogue"]
    leg_items = " ".join(
        f"<span class='leg-item'><span class='swatch' style='background:{t['color']}'></span>"
        f"{escape(t['name'])} <span class='dim'>(costo {t['cost']:g})</span></span>"
        for t in cat)
    parts.append(f"<div class='note legend-box'><b>Leyenda:</b> {leg_items}</div>")

    parts.append("<div class='cmp-grid'>")
    # maxes across seeds for pixel-bar normalization
    import math as _m
    _max = {
        "boulder_pct": max(e["stats"]["boulder_pct"] for e in entries),
        "pois": max(len(e["pois"]) for e in entries),
        "interest": 1.0,
        "science": max(e["stats"]["total_science"] for e in entries),
        "cost": max(sum(t["cost"] * e["terrain_mix"].get(t["name"], 0)
                        for t in e["terrain_catalogue"]) / (e["W"] * e["H"])
                    for e in entries),
        "h_mean": entries[0]["depth"] - 1,
        "roughness": max(e["stats"]["roughness"] for e in entries),
        "entropy": _m.log2(max(2, len(entries[0]["terrain_catalogue"]))),
    }
    _BCOL = {"boulder": (255, 135, 135), "poi": (199, 146, 234),
             "cost": (255, 169, 77), "height": (59, 91, 219),
             "rough": (230, 119, 0), "div": (47, 158, 68)}
    for e in entries:
        seed = e["seed"]
        t64 = _png_b64(_map_png(e, "terrain", scale=10))
        n = e["W"] * e["H"]
        st = e["stats"]
        avg_cost = sum(t["cost"] * e["terrain_mix"].get(t["name"], 0)
                       for t in e["terrain_catalogue"]) / n
        avg_interest = (sum(p["interest"] for p in e["pois"]) / len(e["pois"])
                        if e["pois"] else 0)
        hdist = ", ".join(f"z{z}:{c}" for z, c in enumerate(e["layer_hist"]))

        def _row(emoji, label, val_txt, frac_val, frac_max, col):
            bar = _bar_png(frac_val, frac_max, color=_BCOL[col])
            return (f"<div class='stat-row'><span>{emoji} {label}: "
                    f"<b>{val_txt}</b></span>"
                    f"<img class='pxbar' src='{bar}'></div>")

        parts.append(
            f"<div class='panel cmp-card'><h3>Seed {seed}</h3>"
            f"<img class='viz' src='{t64}'>"
            f"<div class='stats'>"
            + _row("\U0001f9f1", "Rocas", f"{len(e['boulders'])} ({st['boulder_pct']:.1f}%)",
                   st["boulder_pct"], 100.0, "boulder")
            + _row("\U0001f4cd", "POIs", f"{len(e['pois'])}",
                   len(e["pois"]), _max["pois"], "poi")
            + _row("\U0001f4a1", "Inter\u00e9s medio", f"{avg_interest:.2f}",
                   avg_interest, _max["interest"], "poi")
            + _row("\U0001f52c", "Ciencia total", f"{st['total_science']:.2f}",
                   st["total_science"], _max["science"], "poi")
            + _row("\U0001f4b0", "Costo medio", f"{avg_cost:.2f}",
                   avg_cost, _max["cost"], "cost")
            + _row("\U0001f3d4\ufe0f", "Altura media", f"{st['h_mean']:.2f}",
                   st["h_mean"], _max["h_mean"], "height")
            + _row("\u3030\ufe0f", "Rugosidad", f"{st['roughness']:.2f}",
                   st["roughness"], _max["roughness"], "rough")
            + _row("\U0001f500", "Diversidad", f"{st['entropy']:.2f} bits",
                   st["entropy"], _max["entropy"], "div")
            + f"<div class='dim'>Domina {st['most_terrain']} ({st['most_pct']:.0f}%) \u00b7 "
            f"raro {st['least_terrain']} ({st['least_pct']:.0f}%)</div>"
            f"<div class='dim'>{hdist}</div>"
            f"</div></div>")
    parts.append("</div>")
    parts.append('</div>')

    # ---- Per-seed tabs ----
    for e in entries:
        seed = e["seed"]
        parts.append(f'<div class="tabsec" id="sec-{seed}">')
        W, H, depth = e["W"], e["H"], e["depth"]
        mix = ", ".join(f"{k}: {v}" for k, v in sorted(e["terrain_mix"].items()))
        parts.append(f"<h2>Semilla {seed} \u2014 {W}\u00d7{H}\u00d7{depth}</h2>")
        parts.append("<h2>El mapa, paso a paso</h2><div class='grid'>")
        stages = [
            ("star", f"1. Estrella ({e['noise']['star_arms']} brazos)"),
            ("blobs", f"2. Manchas ({e['noise']['n_blobs']})"),
            ("waves", "3. Ondas"),
            ("combined", "4. Promedio de los 3"),
            ("contrast", f"5. Contraste (x{e['contrast']:g}) + recorte [0,1]"),
            ("height", "6. Cuantizada \u2192 altura z"),
            ("biomes", f"7. Biomas ({len(e['biome_centers'])} regiones Voronoi)"),
            ("terrain", "8. Terrenos por bioma + rocas \u25b2 + lava"),
        ]
        for kind, name in stages:
            b64 = _png_b64(_map_png(e, kind, scale=max(4, 480 // W)))
            parts.append(f"<div class='panel'><h3>{name}</h3>"
                         f"<img class='viz' src='{b64}'></div>")
        parts.append("</div>")
        zleg = " ".join(
            f"<span style='color:{c}'>\u25a0</span>z={z}"
            for z, c in enumerate(e["height_colors"]))
        tleg = " ".join(
            f"<span class='leg-item'><span class='swatch' style='background:{t['color']}'></span>"
            f"{escape(t['name'])}</span>"
            for t in e["terrain_catalogue"])
        bases = [f"<b class='mB'>B</b> {escape(s['id'])}"
                 f"<span class='dim'> ({s['x']},{s['y']},z{s['z']})</span>"
                 for s in e["stations"] if s["main"]]
        relays = [f"<b class='mR'>R</b> {escape(s['id'])}"
                  f"<span class='dim'> ({s['x']},{s['y']},z{s['z']})</span>"
                  for s in e["stations"] if not s["main"]]
        poi_list = ", ".join(
            f"<b class='mO'>O</b> {escape(p['id'])}"
            f"<span class='dim'> ({p['x']},{p['y']},z{p['z']} \u00b7 "
            f"inter\u00e9s {p['interest']:.2f})</span>"
            for p in e["pois"]) or "sin pois"
        parts.append(
            f"<div class='note'><b>{len(e['boulders'])} rocas</b> \u00b7 "
            f"{len(e['pois'])} pois \u00b7 {len(e['stations'])} bases \u00b7 "
            f"terrenos: {mix}<br>"
            f"<span class='legend'>Altura: {zleg}<br>Terreno: {tleg}</span>"
            f"<span class='legend feat'>"
            f"{' \u00b7 '.join(bases)}{' \u00b7 '.join(relays)}<br>{poi_list}</span>"
            "</div>")
        parts.append(_quant_report(e))
        parts.append('</div>')

    parts.append("</body></html>")
    return "\n".join(parts)


def build_html(seeds: List[int], width: int = 64, height: int = 64,
               depth: int = 3, poi_count: int = 10,
               config_path: Optional[Path] = None,
               title: str = "Terrenos del rover",
               out: Path = Path("terrains.html")) -> Path:
    """Generate the maps and write the HTML. Returns the file path."""
    entries = [pipeline_data(s, width, height, depth, poi_count, config_path)
               for s in seeds]
    out = Path(out)
    out.write_text(render_html(entries, title=title), encoding="utf-8")
    return out
