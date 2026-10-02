from enviro.config import CONFIG
from enviro.terrain import (
    InstanceParams,
    Map,
    MapGenerator,
    TerrainField,
    build_registry,
    generate,
    mean_cost,
    terrain,
    terrain_names,
)


def banner(title: str) -> None:
    print("\n" + "=" * 74)
    print(f"  {title}".center(74))
    print("=" * 74)


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * 74)


def demo_1_one_map() -> None:
    banner("1. One map")
    terrain_map = generate(seed=42)
    print(terrain_map.summary())
    print()
    print(terrain_map.render())

    section("Cost of the steps out of one cell")
    start = _start_cell(terrain_map)
    print(f"  from {start}  ({terrain_map.cell(start).true_terrain})")
    for other in terrain_map.neighbours(start)[:6]:
        cell = terrain_map.cell(other)
        if cell.blocked:
            print(f"  -> {other}  blocked")
            continue
        climb = cell.pos[2] - terrain_map.cell(start).pos[2]
        print(f"  -> {other}  {cell.true_terrain:<9} "
              f"cost={terrain_map.cost_between(start, other):6.2f}"
              f"{'  (climbing)' if climb > 0 else ''}")


def demo_2_family() -> None:
    banner("2. A family of maps, one per seed")
    header = (f"  {'seed':>4} {'cells':>6} {'blocked':>8} {'reachable':>10} "
              f"{'covered':>8}  {'terrain mix':<34} points of interest")
    print(f"\n{header}")
    for terrain_map in MapGenerator().batch(range(1, 9)):
        print(f"  {terrain_map.params.seed:>4} {len(terrain_map.cells):>6} "
              f"{terrain_map.blocked_ratio():>8.1%} "
              f"{len(terrain_map.reachable_from_surface()) / len(terrain_map.cells):>10.1%} "
              f"{terrain_map.coverage_ratio():>8.1%}  "
              f"{_mix(terrain_map):<34} {_layers(terrain_map)}")
    print("\n  Same config, eight different maps. Same terrain statistics,")
    print("  different arrangement: that is the controlled variation a")
    print("  comparison over instances needs.")


def demo_3_reproducibility() -> None:
    banner("3. Reproducibility")
    a = generate(seed=7)
    b = generate(seed=7)
    c = generate(seed=8)

    def fingerprint(m: Map) -> tuple:
        return (
            tuple((i, n.true_terrain, n.blocked) for i, n in sorted(m.cells.items())),
            m.pois,
            tuple((s.id, s.center) for s in m.stations),
        )

    print(f"\n  same seed, identical map       : {fingerprint(a) == fingerprint(b)}")
    print(f"  different seed, different map  : {fingerprint(a) != fingerprint(c)}")
    print(f"  summary text identical         : {a.summary() == b.summary()}")

    import random as global_random
    global_random.seed(1234)
    expected = global_random.random()
    global_random.seed(1234)
    generate(seed=99)
    print(f"  global RNG untouched           : {global_random.random() == expected}")


def demo_4_catalogue() -> None:
    banner("4. Terrain catalogue and cost model")
    meaning = {
        "plain": "dust: cheap to cross, sees far",
        "sand": "soft: moderate cost, still clear enough to observe from",
        "rock": "rough: expensive, and too dark to observe from",
        "crevasse": "worst ground and worst vantage point",
    }
    print(f"\n  {'terrain':<10} {'cost':>6} {'visibility':>11}   meaning")
    for name in terrain_names():
        t = terrain(name)
        print(f"  {name:<10} {t.cost:>6.2f} {t.visibility:>11.2f}   {meaning.get(name, '')}")
    print(f"\n  unsurveyed ground costs the catalogue mean, {mean_cost():.2f}, "
          f"which is the expected cost of a random cell")

    terrain_map = generate(seed=3)
    penalty = terrain_map.params.climb_penalty
    print(f"\n  cost of one step onto each terrain   (climb penalty {penalty:.0%})")
    print(f"  {'terrain':<10} {'same level':>11} {'climbing 1':>11} {'descending 1':>13}")
    for name in terrain_names():
        print(f"  {name:<10} "
              f"{terrain_map.layer_cost(name, 0):>11.2f} "
              f"{terrain_map.layer_cost(name, 1):>11.2f} "
              f"{terrain_map.layer_cost(name, -1):>13.2f}")
    print("\n  Climbing is work, descending is not. The destination pays.")


def demo_5_depth() -> None:
    banner("5. Depth stratification")
    print("\n  The ramp in the field is the only depth rule. Deeper cells trend")
    print("  toward the expensive end of the band table.\n")
    print(f"  {'layer':<7} " + " ".join(f"{n:>9}" for n in terrain_names()) +
          f" {'mean cost':>10}")
    for z, counts in enumerate(generate(seed=5).layer_distribution()):
        total = sum(counts.values())
        mean = sum(terrain(name).cost * n for name, n in counts.items()) / total
        print(f"  z{z:<6} " + " ".join(f"{counts[n]:>9}" for n in terrain_names()) +
              f" {mean:>10.2f}")

    print("\n  Over 20 seeds, mean cost per layer:")
    totals = {z: 0.0 for z in range(3)}
    maps = MapGenerator().batch(range(20))
    for terrain_map in maps:
        for z, counts in enumerate(terrain_map.layer_distribution()):
            total = sum(counts.values())
            totals[z] += sum(terrain(n).cost * c for n, c in counts.items()) / total
    print("  " + "  ".join(f"z{z}={v / len(maps):.2f}" for z, v in sorted(totals.items())))


def demo_6_sweeps() -> None:
    banner("6. Instance statistics across settings")
    print(f"\n  {'setting':<20} {'cells':>6} {'blocked':>8} {'reachable':>10} "
          f"{'covered':>8} {'mean cost':>10} {'pois':>5}")
    for label, overrides in [
        ("default", {}),
        ("blocks 0.0", dict(block_rate=0.0)),
        ("blocks 0.15", dict(block_rate=0.15)),
        ("grid 8x8x2", dict(width=8, height=8, depth=2)),
        ("grid 16x16x4", dict(width=16, height=16, depth=4)),
        ("one station", dict(station_count=1)),
        ("six points", dict(poi_count=6)),
    ]:
        maps = MapGenerator().batch(range(10), **overrides)
        cells = sum(len(m.cells) for m in maps) / len(maps)
        blocked = sum(m.blocked_ratio() for m in maps) / len(maps)
        reach = sum(len(m.reachable_from_surface()) / len(m.cells) for m in maps) / len(maps)
        cover = sum(m.coverage_ratio() for m in maps) / len(maps)
        cost = sum(_mean_cost(m) for m in maps) / len(maps)
        pois = sum(len(m.pois) for m in maps) / len(maps)
        print(f"  {label:<20} {cells:>6.0f} {blocked:>8.1%} {reach:>10.1%} "
              f"{cover:>8.1%} {cost:>10.2f} {pois:>5.1f}")
    print("\n  Averages over 10 seeds each. A single map would hide every one of")
    print("  these differences, which is why the protocol needs the family.")


def demo_7_validation() -> None:
    banner("7. Config validation")
    param_cases = [
        ("width = 0", dict(width=0)),
        ("width = 999", dict(width=999)),
        ("block_rate = 1.5", dict(block_rate=1.5)),
        ("station_count = 3", dict(station_count=3)),
        ("poi_count = -1", dict(poi_count=-1)),
        ("seed = 'a'", dict(seed="a")),
    ]
    for label, overrides in param_cases:
        try:
            InstanceParams(**overrides)
            print(f"  {label:<30} -> accepted (unexpected)")
        except (ValueError, TypeError) as exc:
            print(f"  instance  {label:<21} -> {str(exc)[:56]}")

    field_cases = [
        ("odd noise_scale", dict(noise_scale=3)),
        ("fractional noise_scale", dict(noise_scale=2.5)),
        ("weights not summing to 1", dict(axis_weights={"x": 0.4, "y": 0.4})),
        ("third noise axis", dict(axis_weights={"x": 0.3, "y": 0.3, "z": 0.4})),
        ("duplicate band edges", dict(bands=[{"max": 0.5, "terrain": "plain"},
                                            {"max": 0.5, "terrain": "sand"}])),
        ("no bands", dict(bands=[])),
        ("unknown terrain in bands", dict(bands=[{"max": 1.0, "terrain": "lava"}])),
        ("depth_slope out of range", dict(depth_slope=4.0)),
    ]
    for label, overrides in field_cases:
        try:
            TerrainField(12, 12, 3, settings={**CONFIG["generation"], **overrides})
            print(f"  {label:<30} -> accepted (unexpected)")
        except (ValueError, TypeError, KeyError) as exc:
            print(f"  field     {label:<21} -> {str(exc)[:56]}")

    catalogue_cases = [
        ("free terrain", dict(cost=0.0)),
        ("visibility above 1", dict(visibility=1.5)),
        ("zero visibility", dict(visibility=0.0)),
        ("two-character glyph", dict(glyph="ab")),
    ]
    for label, patch in catalogue_cases:
        try:
            build_registry(
                {**CONFIG["terrain"], "plain": {**CONFIG["terrain"]["plain"], **patch}}
            )
            print(f"  {label:<30} -> accepted (unexpected)")
        except ValueError as exc:
            print(f"  catalogue {label:<21} -> {str(exc)[:56]}")


# helpers 

def _start_cell(terrain_map: Map) -> str:
    """Any traversable surface cell, for illustration."""
    return terrain_map.surface_ids()[0]


def _mix(terrain_map: Map) -> str:
    distribution = terrain_map.terrain_distribution()
    return " ".join(f"{name[:4]}{count}" for name, count in distribution.items())


def _layers(terrain_map: Map) -> str:
    from enviro.terrain import parse_cell_id
    layers = sorted({parse_cell_id(p.cell_id)[2] for p in terrain_map.pois.values()})
    return "layers " + str(layers)


def _mean_cost(terrain_map: Map) -> float:
    distribution = terrain_map.terrain_distribution()
    total = sum(distribution.values())
    return sum(terrain(name).cost * count for name, count in distribution.items()) / total


def _main() -> None:
    print("Rover terrain inspector")
    for demo in (
        demo_1_one_map,
        demo_2_family,
        demo_3_reproducibility,
        demo_4_catalogue,
        demo_5_depth,
        demo_6_sweeps,
        demo_7_validation,
    ):
        demo()
    banner("done")



