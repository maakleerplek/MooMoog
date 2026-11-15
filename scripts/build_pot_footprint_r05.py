#!/usr/bin/env python3
"""Generate the B10K potentiometer footprint (R0.5) and optionally install it on the control PCB.

Source: Alpha RD901F-40-15R1-B10K datasheet (docs/sources/datablad-2358961-*.pdf), used as a proxy for the
Youmile pots (same RK097 family). Vertical type: shaft perpendicular to the PCB, pins parallel to the shaft.
Origin = shaft axis. Looking along the shaft (= PCB top view), pins 1-2-3 run left to right, 6.4 mm from the axis
(datasheet: 6.0 to the near edge of the 0.8 mm terminal, 6.5 in the front view), 2.5 mm pitch, holes 1.0 (+0.1).
Ground/mount tabs: slots 1.8 x 1.1 at x = +/-5.7 (11.4 apart), datasheet puts their line 7.5 mm from the pin row
(1.1 mm beyond the axis) but the front view draws it at the axis -> slot made 3.0 mm tall to cover both.
UNVERIFIED on the Youmile part: confirm with the 1:1 template before ordering boards.
Pad numbers 1/2/3 = LOW/WIPER/HIGH; tab pads T1/T2 are unconnected (mechanical) for now.
Usage: python3 build_pot_footprint_r05.py [--apply]   (--apply needs KiCad's pcbnew module)
"""
import sys, uuid, json
from pathlib import Path
O = Path(__file__).resolve().parents[1] / 'hardware/split-r0.5/control'
NAME = 'Pot_B10K_RD901F_Vertical'
PIN_Y, PITCH, DRILL, PAD = 6.4, 2.5, 1.1, 1.8
TAB_X, TAB_Y, SLOT_W, SLOT_H = 5.7, -0.5, 1.8, 3.0
U = lambda s: str(uuid.uuid5(uuid.NAMESPACE_URL, 'split-r05/pot/' + s))
FONT = '(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)'


def line(a, b, layer, w, tag):
    return f'\t(fp_line\n\t\t(start {a[0]} {a[1]})\n\t\t(end {b[0]} {b[1]})\n\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type default)\n\t\t)\n\t\t(layer "{layer}")\n\t\t(uuid "{U(tag)}")\n\t)\n'


def rect(x1, y1, x2, y2, layer, w, tag):
    p = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    return ''.join(line(p[i], p[(i + 1) % 4], layer, w, f'{tag}{i}') for i in range(4))


def prop(k, v, layer):
    return f'\t(property "{k}" "{v}"\n\t\t(at 0 0 0)\n\t\t(layer "{layer}")\n\t\t(hide yes)\n\t\t(uuid "{U(k)}")\n\t\t{FONT}\n\t)\n'


def circle(r, layer, w, tag):
    return f'\t(fp_circle\n\t\t(center 0 0)\n\t\t(end {r} 0)\n\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type default)\n\t\t)\n\t\t(fill no)\n\t\t(layer "{layer}")\n\t\t(uuid "{U(tag)}")\n\t)\n'


def footprint():
    s = f'(footprint "{NAME}"\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n\t(layer "F.Cu")\n'
    s += prop('Reference', 'RV', 'F.SilkS') + prop('Value', 'B10K', 'F.Fab') + prop('Datasheet', '', 'F.Fab')
    s += prop('Description', 'Vertical B10K pot, axis at origin; pin row 6.4 mm below axis. Alpha RD901F proxy, unverified on Youmile part', 'F.Fab')
    s += rect(-4.75, -4.85, 4.75, 6.5, 'F.Fab', 0.1, 'fab') + circle(3.5, 'F.Fab', 0.1, 'bush') + circle(3.175, 'F.Fab', 0.1, 'shaft')
    s += line((-4.0, -5.4), (4.0, -5.4), 'F.SilkS', 0.12, 'silk-top') + line((-4.4, 5.9), (-4.4, 6.9), 'F.SilkS', 0.12, 'silk-p1') + rect(-6.7, -5.8, 6.7, 7.8, 'F.CrtYd', 0.05, 'crt')
    for n, x in (('1', -PITCH), ('2', 0.0), ('3', PITCH)):
        s += f'\t(pad "{n}" thru_hole circle\n\t\t(at {x} {PIN_Y})\n\t\t(size {PAD} {PAD})\n\t\t(drill {DRILL})\n\t\t(layers "*.Cu" "*.Mask")\n\t\t(remove_unused_layers no)\n\t\t(uuid "{U("p" + n)}")\n\t)\n'
    for n, x in (('T1', -TAB_X), ('T2', TAB_X)):
        s += (f'\t(pad "{n}" thru_hole oval\n\t\t(at {x} {TAB_Y})\n\t\t(size {SLOT_W + 1.4} {SLOT_H + 1.4})\n\t\t(drill oval {SLOT_W} {SLOT_H})\n'
              f'\t\t(layers "*.Cu" "*.Mask")\n\t\t(remove_unused_layers no)\n\t\t(uuid "{U(n)}")\n\t)\n')
    return s + ')\n'


def write():
    d = O / 'libraries/Compact.pretty'
    d.mkdir(parents=True, exist_ok=True)
    (d / (NAME + '.kicad_mod')).write_text(footprint())


def strip_tracks(pcb):
    """Remove all segments/vias by text edit (pcbnew crashes when removing tracks). The old R0.5 tracks were routed
    before real pads existed and short against them; routing is redone after footprints and placement are final."""
    import re
    s = pcb.read_text()
    s2 = re.sub(r'\n\t\((?:segment|via)\n.*?\n\t\)', '', s, flags=re.S)
    pcb.write_text(s2)


def apply():
    import pcbnew as p
    pcb = O / 'control.kicad_pcb'
    b = p.LoadBoard(str(pcb))
    nets = {}

    def net(n):
        if n not in nets:
            nets[n] = b.FindNet(n) or p.NETINFO_ITEM(b, n)
            if b.FindNet(n) is None:
                b.Add(nets[n])
        return nets[n]
    num = {'LOW': '1', 'WIPER': '2', 'HIGH': '3'}
    pins = {c['ref']: {num[q['number']]: q['net'] for q in c['pins']} for c in json.load(open(O.parent / 'design-master.json'))['components'] if c['kind'] == 'pot'}
    for f in list(b.GetFootprints()):
        r = f.GetReference()
        if r not in pins:
            continue
        new = p.FootprintLoad(str(O / 'libraries/Compact.pretty'), NAME)
        new.SetReference(r); new.SetValue(f.GetValue()); new.Reference().SetVisible(False); new.Value().SetVisible(False)
        m = p.FP_3DMODEL(); m.m_Filename = '${KIPRJMOD}/models/' + r + '.wrl'; new.Add3DModel(m)
        new.SetPosition(f.GetPosition()); new.SetOrientation(f.GetOrientation())
        for pad in new.Pads():
            n = pins[r].get(pad.GetNumber())
            if n:
                pad.SetNet(net(n))
        b.Remove(f); b.Add(new)
    p.SaveBoard(str(pcb), b)
    if '--strip-tracks' in sys.argv:
        strip_tracks(pcb)


if __name__ == '__main__':
    write()
    if '--apply' in sys.argv:
        apply()
