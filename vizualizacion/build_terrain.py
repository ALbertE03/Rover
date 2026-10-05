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
    combined = nz["combined"]
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

    return {
        "seed": seed, "W": width, "H": height, "depth": depth,
        "noise": nz,
        "block_rate":gen.config['map']['block_rate'],
        "heightmap": hm,
        "terrain": terrain,
        "terrain_mix": mix,
        "boulders": boulders,
        "height_colors": _height_colors(depth),
        "stations": stations,
        "pois": pois,
        # quantization report
        "contrast": contrast,
        "cells": width * height,
        "avg_range": [min(flat_avg), max(flat_avg)],
        "post_range": [min(flat_post), max(flat_post)],
        "clamped_low": sum(1 for v in flat_post if v < 0.0),
        "clamped_high": sum(1 for v in flat_post if v > 1.0),
        "layer_hist": hist,
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


def render_html(entries: List[Tuple[Dict,int]], title: str = "Terrenos") -> str:
    """Self-contained HTML showing the pipeline behind every map."""
    heading = escape(title)
    parts = []
    parts.append("""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + heading + """</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1060px;margin:0 auto;padding:14px;background:#0f1419;color:#e6e9ee}
h1{font-size:19px}h2{font-size:16px;margin:26px 0 8px;color:#9fd0ff}
.grid{display:flex;gap:12px;flex-wrap:wrap}
.panel{background:#1a2230;border-radius:10px;padding:10px;margin-bottom:12px}
.panel h3{margin:4px 0 8px;font-size:12px;color:#cfe3ff}
.note{background:#1a2230;border-left:4px solid #e2a63d;border-radius:6px;padding:10px 14px;margin:12px 0;font-size:13px;line-height:1.6}
canvas{border-radius:8px;background:#0a0d12;max-width:100%}
code{background:#0a0d12;padding:1px 6px;border-radius:4px;font-size:12px}
hr{border:0;border-top:2px solid #2b3a55;margin:30px 0}
.legend{font-size:12px;color:#9aa3b2;margin-top:6px;line-height:1.9}
ol.steps{margin:8px 0;padding-left:22px}
ol.steps li{margin:5px 0}
table.kv{border-collapse:collapse;margin:10px 0;font-size:12px;width:100%}
table.kv th{text-align:left;color:#9fd0ff;font-weight:600;padding:4px 8px;border-bottom:1px solid #2b3a55}
table.kv td{padding:4px 8px;border-top:1px solid #233047;vertical-align:top}
table.kv td:first-child{color:#9aa3b2}
td.num{text-align:right;white-space:nowrap;color:#9aa3b2}
td.bar{width:26%}
td.bar span{display:block;height:9px;border-radius:2px;min-width:1px}
.cap{display:block;color:#9aa3b2;font-size:12px;margin-top:8px;line-height:1.6}
.m{display:inline-block;min-width:1em;text-align:center;font-family:ui-monospace,monospace;
   font-weight:700;background:#0a0d12;border-radius:3px;padding:0 3px;margin-right:2px}
.mB{color:#7ef0a0}.mR{color:#ffa94d}.mO{color:#c792ea}.mA{color:#ff8787}
.dim{color:#79839a;font-size:11px}
.feat{margin-top:8px;line-height:2}
</style></head><body>
<h1>""" + heading + f"""</h1>
<div class="note">Cada mapa nace de <b>3 ruidos aleatorios</b> (estrella + manchas + ondas)
&rarr; promedio &rarr; contraste &rarr; <b>cuantizaci&oacute;n</b>.
Las <b>rocas \u25b2</b> (<code>block_rate={entries[0]["block_rate"]}</code> por columna) bloquean el paso.</div>

<h2>C&oacute;mo funciona la cuantizaci&oacute;n</h2>
<div class="note">
<ol class="steps">
<li><b>Promediar</b> los tres ruidos normalizados &rarr;
<code>n = (estrella + manchas + ondas) / 3</code></li>
<li><b>Estirar</b> alrededor del punto medio &rarr;
<code>n = 0.5 + (n - 0.5) &times; height_contrast</code></li>
<li><b>Recortar</b> al rango v&aacute;lido &rarr;
<code>n = clamp(n, 0, 1)</code></li>
<li><b>Redondear</b> a la capa m&aacute;s cercana, los empates hacia arriba &rarr;
<code>h = int(n &times; (depth - 1) + 0.5)</code></li>
</ol>
</div>
""")

    for e in entries:
        seed, W, H, depth = e["seed"], e["W"], e["H"], e["depth"]
        S = max(2, 480 // W)
        SZ = W * S
        mix = ", ".join(f"{k}: {v}" for k, v in sorted(e["terrain_mix"].items()))
        parts.append(f"<hr><h1>Semilla {seed} \u2014 {W}\u00d7{H}\u00d7{depth}</h1>")
        parts.append("<h2>El mapa, paso a paso</h2><div class='grid'>")
        stages = [
            (f"cvS{seed}", f"1. Estrella ({e['noise']['star_arms']} brazos)"),
            (f"cvB{seed}", f"2. Manchas ({e['noise']['n_blobs']})"),
            (f"cvW{seed}", "3. Ondas"),
            (f"cvC{seed}", "4. Promedio de los 3"),
            (f"cvX{seed}", f"5. Estiramiento de contraste (x{e['contrast']:g})"
                            f" + recorte [0,1]"),
            (f"cvH{seed}", "6. Cuantizada \u2192 altura z"),
            (f"cvT{seed}", "7. Terrenos + rocas \u25b2"),
        ]
        for cid, name in stages:
            parts.append(f"<div class='panel'><h3>{name}</h3>"
                         f"<canvas id='{cid}' width='{SZ}' height='{SZ}'></canvas></div>")
        parts.append("</div>")
        zleg = " ".join(
            f"<span style='color:{c}'>\u25a0</span>z={z}"
            for z, c in enumerate(e["height_colors"]))
        bases = [f"<b class='mB'>{_mark('B')}</b> {escape(s['id'])}"
                 f"<span class='dim'> ({s['x']},{s['y']},z{s['z']} &middot; "
                 f"r={s['radius']:g} &middot; se&ntilde;al {s['signal']:g})</span>"
                 for s in e["stations"] if s["main"]]
        relays = [f"<b class='mR'>{_mark('R')}</b> {escape(s['id'])}"
                  f"<span class='dim'> ({s['x']},{s['y']},z{s['z']} &middot; "
                  f"r={s['radius']:g} &middot; se&ntilde;al {s['signal']:g})</span>"
                  for s in e["stations"] if not s["main"]]
        poi_list = ", ".join(
            f"<b class='mO'>{_mark('O')}</b> {escape(p['id'])}"
            f"<span class='dim'> ({p['x']},{p['y']},z{p['z']} &middot; "
            f"inter&eacute;s {p['interest']:.2f})</span>"
            for p in e["pois"]) or "sin pois"
        parts.append(
            f"<div class='note'><b>{len(e['boulders'])} rocas</b> \u00b7 "
            f"{len(e['pois'])} pois \u00b7 {len(e['stations'])} bases \u00b7 "
            f"terrenos: {mix}<br>"
            f"<span class='legend'>Altura: {zleg} \u00b7 "
            f"Terreno: <span style='color:#4a7c59'>\u25a0</span>llano "
            f"<span style='color:#c9a227'>\u25a0</span>arena "
            f"<span style='color:#6b7280'>\u25a0</span>roca "
            f"<span style='color:#1f2937'>\u25a0</span>grieta</span>"
            f"<span class='legend feat'>Marcas: "
            f"<b class='mB'>{_mark('B')}</b>base principal \u00b7 "
            f"<b class='mR'>{_mark('R')}</b>base repetidora \u00b7 "
            f"<b class='mO'>{_mark('O')}</b>poi de inter&eacute;s \u00b7 "
            f"<b class='mA'>{_mark(chr(0x25B2))}</b>roca<br>"
            f"{' \u00b7 '.join(bases)}{' \u00b7 '.join(relays)}<br>{poi_list}</span>"
            "</div>")
        parts.append(_quant_report(e))
        

    parts.append("<script>")
    parts.append("const D=" + json.dumps({"entries": entries}) + ";")
    parts.append("""
const TC={"plain":"#4a7c59","sand":"#c9a227","rock":"#6b7280","crevasse":"#1f2937"};
function gray(v){const g=Math.round(20+v*220);return "rgb("+g+","+g+","+g+")";}
D.entries.forEach((e)=>{
  const seed=e.seed,W=e.W,H=e.H,S=Math.max(2,Math.floor(480/W));
  const paint=(id,fn)=>{const c=document.getElementById(id),x=c.getContext("2d");
    for(let i=0;i<W;i++)for(let j=0;j<H;j++){x.fillStyle=fn(i,j);x.fillRect(i*S,j*S,S,S);}};
  const nz=e.noise;
  paint("cvS"+seed,(i,j)=>gray(nz.star[i][j]));
  paint("cvB"+seed,(i,j)=>gray(nz.blobs[i][j]));
  paint("cvW"+seed,(i,j)=>gray(nz.waves[i][j]));
  paint("cvC"+seed,(i,j)=>gray(nz.combined[i][j]));
  {const ct=(v)=>0.5+(v-0.5)*e.contrast;
   paint("cvX"+seed,(i,j)=>gray(Math.max(0,Math.min(1,ct(nz.combined[i][j])))));}
  paint("cvH"+seed,(i,j)=>e.height_colors[e.heightmap[i][j]]);
  {const c=document.getElementById("cvT"+seed),x=c.getContext("2d");
   for(let i=0;i<W;i++)for(let j=0;j<H;j++){
     x.fillStyle=TC[e.terrain[i+","+j]]||"#333";x.fillRect(i*S,j*S,S,S);
     x.strokeStyle="rgba(0,0,0,.25)";x.strokeRect(i*S+.5,j*S+.5,S-1,S-1);}
   x.textAlign="center";x.textBaseline="middle";
   const mark=(cx,cy,ch,col,font)=>{
     x.font=font;
     x.lineWidth=Math.max(1,S/6);x.strokeStyle="rgba(0,0,0,.75)";
     x.strokeText(ch,cx,cy);x.fillStyle=col;x.fillText(ch,cx,cy);};
   const small=Math.max(6,S-6)+"px sans-serif";
   for(const b of e.boulders)mark(b[0]*S+S/2,b[1]*S+S/2+1,"\\u25b2","#ff8787",small);
   /* Ground features, grouped per cell so two marks on one column stay legible. */
   const marks={};
   const put=(k,ch,col)=>{(marks[k]=marks[k]||[]).push([ch,col]);};
   e.stations.forEach(s=>put(s.x+","+s.y,s.main?"B":"R",s.main?"#7ef0a0":"#ffa94d"));
   e.pois.forEach(p=>put(p.x+","+p.y,"O","#c792ea"));
   const big="bold "+Math.max(12,Math.round(S*1.6))+"px sans-serif";
   const r=Math.max(6,Math.round(S*0.78));
   for(const k in marks){
     const list=marks[k],xy=k.split(",");
     /* Clamp so the disc stays whole on edge and corner columns: relays
        always land in a corner (farthest-point fill), so this is the norm. */
     const cx=Math.min(Math.max(xy[0]*S+S/2,r+1),c.width-r-1);
     const cy=Math.min(Math.max(xy[1]*S+S/2,r+1),c.height-r-1);
     list.forEach((m,i)=>{
       const dx=list.length>1?(i-(list.length-1)/2)*(r*2.15):0;
       x.beginPath();x.arc(cx+dx,cy,r,0,6.2832);
       x.fillStyle="rgba(10,13,18,.88)";x.fill();
       x.lineWidth=1.5;x.strokeStyle=m[1];x.stroke();
       mark(cx+dx,cy+1,m[0],m[1],big);});}}
});
</script></body></html>
""")
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
