#!/usr/bin/env python3
"""Export board + component STLs for R0.5 (needs KiCad's pcbnew module and kicad-cli).
KiCad's STL exporter ignores VRML models, so the project's simple IndexedFaceSet .wrl
bodies are placed here and merged: <board>-board.stl (copper plate), <board>-components.stl, <board>-assembly.stl.
WRL units are 0.1 inch; board bottom face z=0, top face z=1.55 (as in kicad-cli output)."""
import math, re, struct, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1] / 'hardware/split-r0.5'
ZTOP = 1.55

def write(path, tris):
    with open(path, 'wb') as f:
        f.write(b'Compact D R0.5'.ljust(80, b' ')); f.write(struct.pack('<I', len(tris)))
        for a, b, c in tris:
            u = [b[i] - a[i] for i in range(3)]; v = [c[i] - a[i] for i in range(3)]
            n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]; l = math.sqrt(sum(x*x for x in n)) or 1
            f.write(struct.pack('<12fH', *[x/l for x in n], *a, *b, *c, 0))

def read_ascii(path):
    v = [tuple(map(float, m)) for m in re.findall(rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)', Path(path).read_bytes())]
    return [tuple(v[i:i+3]) for i in range(0, len(v), 3)]

def wrl_tris(path):
    t = Path(path).read_text(); out = []
    for shape in t.split('Shape {')[1:]:
        pts = re.search(r'point \[(.*?)\]', shape, re.S); idx = re.search(r'coordIndex \[(.*?)\]', shape, re.S)
        if not pts or not idx: continue
        nums = [float(x) for x in re.findall(r'-?\d+\.?\d*(?:e-?\d+)?', pts.group(1))]
        P = [tuple(nums[i:i+3]) for i in range(0, len(nums), 3)]
        poly = []
        for tok in re.findall(r'-?\d+', idx.group(1)):
            i = int(tok)
            if i == -1:
                out += [(P[poly[0]], P[poly[k]], P[poly[k+1]]) for k in range(1, len(poly)-1)]; poly = []
            else: poly.append(i)
    return out

def main():
    import pcbnew as p
    for bd in ('control', 'core'):
        pcb = R / bd / (bd + '.kicad_pcb')
        for name, extra in (('board', ['--board-only']),):
            subprocess.run(['kicad-cli', 'pcb', 'export', 'stl', '-f', '--include-tracks', '--include-pads', '--include-zones', '--fuse-shapes', *extra, '-o', f'/tmp/{bd}-board-ascii.stl', str(pcb)], check=True, capture_output=True)
        board = read_ascii(f'/tmp/{bd}-board-ascii.stl'); comps = []
        cache = {}
        for f in p.LoadBoard(str(pcb)).GetFootprints():
            if not f.Models().size(): continue
            fn = f.Models()[0].m_Filename.replace('${KIPRJMOD}', str(R / bd))
            if not Path(fn).exists(): continue
            tris = cache.setdefault(fn, wrl_tris(fn))
            bottom = f.GetLayerName() == 'B.Cu'; th = math.radians(f.GetOrientationDegrees()); c, s = math.cos(th), math.sin(th)
            fx, fy = p.ToMM(f.GetPosition().x), p.ToMM(f.GetPosition().y)
            def T(q):
                mx, my, mz = q[0]*2.54, q[1]*2.54, q[2]*2.54
                if bottom: mz = -mz                       # bottom side: mirror z; x/y handled below
                x, y = (mx, -my) if not bottom else (mx, my)
                px, py = fx + x*c + y*s, fy - x*s + y*c      # y-down pcb frame
                return (px, -py, mz if bottom else ZTOP + mz)
            comps += [tuple(T(q) for q in tri) for tri in tris]
        write(R / 'stl' / f'{bd}-board.stl', board); write(R / 'stl' / f'{bd}-components.stl', comps); write(R / 'stl' / f'{bd}-assembly.stl', board + comps)
        print(bd, len(board), 'board tris', len(comps), 'component tris')

if __name__ == '__main__': main()
