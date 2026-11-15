#!/usr/bin/env python3
"""Generate the RUNCCI-YUN 3-pin slide-switch footprint (R0.5) and optionally install it.

Dimensions (user caliper measurements, 2026-11-15): pin edge-to-edge 10.25 mm,
pin width 0.7 mm => centre pitch 4.775 mm, consistent with standard SS-12D10 4.7 mm.
Body 12.7 x 6.7 mm is the generic SS-12D10 value and is NOT yet verified on the part.
Pins lie along local Y (pre-rotated, matching design-master size [6.7, 12.7]); COM = middle.
Usage: python3 build_switch_footprint_r05.py [--apply]   (--apply needs KiCad's pcbnew module)
"""
import sys, uuid
from pathlib import Path
O = Path(__file__).resolve().parents[1] / 'hardware/split-r0.5/control'
NAME = 'SS12D10_Slide_3P_P4.7'
PITCH, DRILL, PAD, BL, BW = 4.7, 1.1, 1.8, 12.7, 6.7
U = lambda s: str(uuid.uuid5(uuid.NAMESPACE_URL, 'split-r05/sw/' + s))

def line(a, b, layer, w, tag):
    return f'\t(fp_line\n\t\t(start {a[0]} {a[1]})\n\t\t(end {b[0]} {b[1]})\n\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type default)\n\t\t)\n\t\t(layer "{layer}")\n\t\t(uuid "{U(tag)}")\n\t)\n'

def rect(w, h, layer, wd, tag):
    x, y = w / 2, h / 2
    pts = [(-x, -y), (x, -y), (x, y), (-x, y)]
    return ''.join(line(pts[i], pts[(i + 1) % 4], layer, wd, f'{tag}{i}') for i in range(4))

def prop(k, v, layer, hide=True):
    return f'\t(property "{k}" "{v}"\n\t\t(at 0 0 0)\n\t\t(layer "{layer}")\n' + ('\t\t(hide yes)\n' if hide else '') + f'\t\t(uuid "{U(k)}")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n'

def footprint():
    s = f'(footprint "{NAME}"\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n\t(layer "F.Cu")\n'
    s += prop('Reference', 'S', 'F.SilkS') + prop('Value', 'RUNCCI-YUN slide SPDT', 'F.Fab') + prop('Datasheet', '', 'F.Fab') + prop('Description', 'R574 slide switch, pitch measured ~4.78 mm (SS-12D10 4.7); body size unverified', 'F.Fab')
    s += rect(BW, BL, 'F.Fab', 0.1, 'fab') + rect(BW + 0.4, BL + 0.4, 'F.SilkS', 0.12, 'silk') + rect(BW + 0.8, BL + 0.8, 'F.CrtYd', 0.05, 'crt')
    for n, y in (('1', -PITCH), ('2', 0), ('3', PITCH)):   # 1 = ON, 2 = COM, 3 = OFF (SW_SPDT symbol numbering)
        s += f'\t(pad "{n}" thru_hole circle\n\t\t(at 0 {y})\n\t\t(size {PAD} {PAD})\n\t\t(drill {DRILL})\n\t\t(layers "*.Cu" "*.Mask")\n\t\t(remove_unused_layers no)\n\t\t(uuid "{U(n)}")\n\t)\n'
    return s + ')\n'

def write():
    d = O / 'libraries/Compact.pretty'
    d.mkdir(parents=True, exist_ok=True)
    (d / (NAME + '.kicad_mod')).write_text(footprint())

def apply():
    import pcbnew as p
    pcb = O / 'control.kicad_pcb'
    b = p.LoadBoard(str(pcb))
    nets = {}
    def net(n):
        if n not in nets:
            nets[n] = b.FindNet(n) or p.NETINFO_ITEM(b, n)
            if b.FindNet(n) is None: b.Add(nets[n])
        return nets[n]
    import json
    num = {'ON': '1', 'COM': '2', 'OFF': '3'}
    pins = {c['ref']: {num[q['number']]: q['net'] for q in c['pins']} for c in json.load(open(O.parent / 'design-master.json'))['components'] if c['kind'] == 'switch'}
    for f in list(b.GetFootprints()):
        r = f.GetReference()
        if r not in pins: continue
        new = p.FootprintLoad(str(O / 'libraries/Compact.pretty'), NAME)
        new.SetReference(r); new.SetValue(f.GetValue()); new.Reference().SetVisible(False); new.Value().SetVisible(False)
        m = p.FP_3DMODEL(); m.m_Filename = '${KIPRJMOD}/models/' + r + '.wrl'; new.Add3DModel(m)
        new.SetPosition(f.GetPosition()); new.SetOrientation(f.GetOrientation())
        for pad in new.Pads():
            n = pins[r].get(pad.GetNumber())
            if n: pad.SetNet(net(n))
        b.Remove(f); b.Add(new)
    p.SaveBoard(str(pcb), b)

if __name__ == '__main__':
    write()
    if '--apply' in sys.argv: apply()
