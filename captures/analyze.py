#!/usr/bin/env python3
"""Per-byte analysis of captured Roroshetta frames."""
import sys, collections, pathlib

# offset -> (name, width) as decoded by coordinator._parse_data
KNOWN = {
    0: ("temperature", 2), 2: ("heat_index", 2), 4: ("humidity", 2),
    10: ("aqi", 2), 13: ("pm25", 2), 15: ("co2", 2), 17: ("tvoc", 2),
    36: ("uptime", 3), 44: ("alarm_level?", 1), 45: ("activity?", 1),
    46: ("power", 2), 53: ("light", 1), 56: ("fan", 1), 59: ("grease_filter?", 1),
}
def owner(i):
    for off, (name, w) in KNOWN.items():
        if off <= i < off + w:
            return name
    return None

def load(path):
    frames = []
    for line in pathlib.Path(path).read_text().splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2]:
            frames.append((parts[0], int(parts[1]), bytes.fromhex(parts[2])))
    return frames

def main(path):
    frames = load(path)
    if not frames:
        print("no frames"); return
    lens = collections.Counter(f[1] for f in frames)
    print(f"frames: {len(frames)}   span: {frames[0][0][11:]} .. {frames[-1][0][11:]}")
    print(f"lengths: {dict(lens)}\n")
    n = min(len(f[2]) for f in frames)
    print(f"{'off':>4} {'owner':<15} {'distinct':>8} {'min':>4} {'max':>4}  values")
    print("-" * 78)
    for i in range(n):
        vals = [f[2][i] for f in frames]
        distinct = sorted(set(vals))
        o = owner(i)
        tag = o if o else ("UNMAPPED" if i >= 60 else "unused")
        if len(distinct) == 1:
            shown = f"const 0x{distinct[0]:02x} ({distinct[0]})"
        else:
            head = ", ".join(f"0x{v:02x}" for v in distinct[:6])
            shown = f"{head}{' ...' if len(distinct) > 6 else ''}"
        print(f"{i:>4} {tag:<15} {len(distinct):>8} {min(vals):>4} {max(vals):>4}  {shown}")

main(sys.argv[1])
