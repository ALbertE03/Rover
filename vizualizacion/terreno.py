"""Terreno -> HTML. Llama al generador (MapGenerator) y dibuja el pipeline
de cada mapa: estrella -> manchas -> ondas -> promedio -> altura
cuantizada -> tipos de terreno + rocas. Sin simulación.
"""
import json
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional

from enviro.config import load_config
from enviro.terrain import InstanceParams, MapGenerator, cell_id


def _station_count(config_path: Optional[Path]) -> int:
    cfg = load_config(config_path)
    return len(cfg["network"]["stations"])


def pipeline_data(seed: int, width: int = 64, height: int = 64, depth: int = 3,
                  poi_count: int = 10,
                  config_path: Optional[Path] = None) -> Dict:
    """Genera un mapa y devuelve todo lo necesario para dibujarlo."""
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

    return {
        "seed": seed, "W": width, "H": height, "depth": depth,
        "noise": field.noise_pipeline(),
        "heightmap": hm,
        "terrain": terrain,
        "terrain_mix": mix,
        "boulders": boulders,
        "height_colors": _height_colors(depth),
    }


def _height_colors(depth: int) -> List[str]:
    """Rampa azul -> verde -> naranja según z."""
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


def render_html(entries: List[Dict], title: str = "Terrenos") -> str:
    """HTML autocontenido con el pipeline de cada mapa."""
    parts = []
    parts.append("""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + title + """</title>
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
</style></head><body>
<h1>\u26f0\ufe0f """ + title + """</h1>
<div class="note">Cada mapa nace de <b>3 ruidos aleatorios</b> (estrella + manchas + ondas)
&rarr; promedio &rarr; contraste &rarr; <b>cuantizaci\u00f3n</b>. Sin suavizados.
Las <b>rocas \u25b2</b> (<code>block_rate=0.06</code> por columna) bloquean. Sin simulaci\u00f3n: solo terrenos.</div>
""")

    for e in entries:
        seed, W, H, depth = e["seed"], e["W"], e["H"], e["depth"]
        S = max(2, 480 // W)
        SZ = W * S
        mix = ", ".join(f"{k}: {v}" for k, v in sorted(e["terrain_mix"].items()))
        parts.append(f"<hr><h1>\U0001f331 Seed {seed} \u2014 {W}\u00d7{H}\u00d7{depth}</h1>")
        parts.append("<h2>El mapa paso a paso</h2><div class='grid'>")
        stages = [
            (f"cvS{seed}", f"1. Estrella ({e['noise']['star_arms']} brazos)"),
            (f"cvB{seed}", f"2. Manchas ({e['noise']['n_blobs']})"),
            (f"cvW{seed}", "3. Ondas"),
            (f"cvC{seed}", "4. Promedio de los 3"),
            (f"cvH{seed}", "5. Cuantizada \u2192 altura z"),
            (f"cvT{seed}", "6. Terrenos + rocas \u25b2"),
        ]
        for cid, name in stages:
            parts.append(f"<div class='panel'><h3>{name}</h3>"
                         f"<canvas id='{cid}' width='{SZ}' height='{SZ}'></canvas></div>")
        parts.append("</div>")
        zleg = " ".join(
            f"<span style='color:{c}'>\u25a0</span>z={z}"
            for z, c in enumerate(e["height_colors"]))
        parts.append(
            f"<div class='note'>\U0001faa8 <b>{len(e['boulders'])} rocas</b> \u00b7 "
            f"terrenos: {mix}<br><span class='legend'>Altura: {zleg} \u00b7 "
            f"Terreno: <span style='color:#4a7c59'>\u25a0</span>llano "
            f"<span style='color:#c9a227'>\u25a0</span>arena "
            f"<span style='color:#6b7280'>\u25a0</span>roca "
            f"<span style='color:#1f2937'>\u25a0</span>grieta</span></div>")

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
  paint("cvH"+seed,(i,j)=>e.height_colors[e.heightmap[i][j]]);
  {const c=document.getElementById("cvT"+seed),x=c.getContext("2d");
   for(let i=0;i<W;i++)for(let j=0;j<H;j++){
     x.fillStyle=TC[e.terrain[i+","+j]]||"#333";x.fillRect(i*S,j*S,S,S);
     x.strokeStyle="rgba(0,0,0,.25)";x.strokeRect(i*S+.5,j*S+.5,S-1,S-1);}
   x.fillStyle="#ff8787";x.font=Math.max(6,S-6)+"px sans-serif";
   x.textAlign="center";x.textBaseline="middle";
   for(const b of e.boulders)x.fillText("\\u25b2",b[0]*S+S/2,b[1]*S+S/2+1);}
});
</script></body></html>
""")
    return "\n".join(parts)


def build_html(seeds: List[int], width: int = 64, height: int = 64,
               depth: int = 3, poi_count: int = 10,
               config_path: Optional[Path] = None,
               title: str = "Terrenos del rover",
               out: Path = Path("terrenos.html")) -> Path:
    """Genera los mapas y escribe el HTML. Devuelve la ruta del archivo."""
    entries = [pipeline_data(s, width, height, depth, poi_count, config_path)
               for s in seeds]
    out = Path(out)
    out.write_text(render_html(entries, title=title), encoding="utf-8")
    return out
