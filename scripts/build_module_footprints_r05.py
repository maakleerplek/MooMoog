#!/usr/bin/env python3
"""Generate footprints for purchased modules (R0.5). Currently: ESP32-S3-DevKitC-1 (ARCELI clone).

ESP32-S3-DevKitC-1 source: Espressif v1.1 dimension drawing (docs/sources/esp32-s3-devkitc-1/DXF_*.pdf/.dxf):
board 25.40 mm wide, 62.74 mm long, header pins 1.27 mm from the long edges -> rows 22.86 mm apart, 2.54 mm pitch,
22 pins per row, pin 1 centre 1.27 mm from the antenna-end edge, USB ports at the other end (about 8 mm beyond the
last pin). Pin names from the Espressif user guide (J1 left, J3 right, antenna up, USB down, seen from the top).
The USB-C outlines are read off the drawing (+/-0.5 mm) and are only used for keep-out / fab layers.
The ARCELI clone is assumed to match; verify the row spacing with a caliper before milling.
Origin = board centre. Usage: python3 build_module_footprints_r05.py [--apply]
"""
import sys, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / 'hardware/split-r0.5'
FONT = '(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)'
U = lambda s: str(uuid.uuid5(uuid.NAMESPACE_URL, 'split-r05/module/' + s))


def line(a, b, layer, w, tag):
    return f'\t(fp_line\n\t\t(start {a[0]:.3f} {a[1]:.3f})\n\t\t(end {b[0]:.3f} {b[1]:.3f})\n\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type default)\n\t\t)\n\t\t(layer "{layer}")\n\t\t(uuid "{U(tag)}")\n\t)\n'


def rect(x1, y1, x2, y2, layer, w, tag):
    p = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    return ''.join(line(p[i], p[(i + 1) % 4], layer, w, f'{tag}{i}') for i in range(4))


def prop(k, v, layer, tag):
    return f'\t(property "{k}" "{v}"\n\t\t(at 0 0 0)\n\t\t(layer "{layer}")\n\t\t(hide yes)\n\t\t(uuid "{U(tag + k)}")\n\t\t{FONT}\n\t)\n'


def pad(n, x, y, tag, d=1.0, s=1.7, shape='circle'):
    return f'\t(pad "{n}" thru_hole {shape}\n\t\t(at {x:.3f} {y:.3f})\n\t\t(size {s} {s})\n\t\t(drill {d})\n\t\t(layers "*.Cu" "*.Mask")\n\t\t(remove_unused_layers no)\n\t\t(uuid "{U(tag)}")\n\t)\n'


def head(name, desc, ref='U', val=''):
    return (f'(footprint "{name}"\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n\t(layer "F.Cu")\n'
            + prop('Reference', ref, 'F.SilkS', name) + prop('Value', val or name, 'F.Fab', name) + prop('Datasheet', '', 'F.Fab', name) + prop('Description', desc, 'F.Fab', name))


ESP = 'ESP32-S3-DevKitC-1_Module'
J1 = ['3V3', '3V3', 'RST', 'GPIO4', 'GPIO5', 'GPIO6', 'GPIO7', 'GPIO15', 'GPIO16', 'GPIO17', 'GPIO18', 'GPIO8', 'GPIO3', 'GPIO46',
      'GPIO9', 'GPIO10', 'GPIO11', 'GPIO12', 'GPIO13', 'GPIO14', '5V', 'GND']
J3 = ['GND', 'TX', 'RX', 'GPIO1', 'GPIO2', 'GPIO42', 'GPIO41', 'GPIO40', 'GPIO39', 'GPIO38', 'GPIO37', 'GPIO36', 'GPIO35', 'GPIO0',
      'GPIO45', 'GPIO48', 'GPIO47', 'GPIO21', 'GPIO20', 'GPIO19', 'GND', 'GND']
W, L, PITCH, ROWS, EDGE = 25.4, 62.74, 2.54, 22.86, 1.27


def esp32():
    cy = L / 2
    top = -cy + EDGE                      # y of pin 1 relative to the board centre
    s = head(ESP, 'ESP32-S3-DevKitC-1 (Espressif v1.1 drawing): rows 22.86 mm apart, 22 pins/row, 2.54 pitch. Antenna up, USB down.', 'MCU', 'ESP32-S3 DevKitC-1')
    s += rect(-W / 2, -cy, W / 2, cy, 'F.Fab', 0.1, 'board')
    s += rect(-W / 2 - 0.3, -cy - 0.3, W / 2 + 0.3, cy + 0.3, 'F.CrtYd', 0.05, 'crt')
    s += rect(-W / 2, -cy, W / 2, cy, 'F.SilkS', 0.12, 'silk')
    s += rect(-4.5 - 4.5, cy - 7.5, -4.5 + 4.5, cy + 0.0, 'F.Fab', 0.1, 'usb1') + rect(5.6 - 4.5, cy - 7.5, 5.6 + 4.5, cy, 'F.Fab', 0.1, 'usb2')
    for i, n in enumerate(J1):
        s += pad(n, -ROWS / 2, top + i * PITCH, f'j1{i}', shape='rect' if i == 0 else 'circle')
    for i, n in enumerate(J3):
        s += pad(n, ROWS / 2, top + i * PITCH, f'j3{i}')
    s += line((-ROWS / 2 - 1.5, top - 1.4), (-ROWS / 2 + 1.5, top - 1.4), 'F.SilkS', 0.12, 'pin1')
    return s + ')\n'


def write():
    for b in ('core',):
        d = ROOT / b / 'libraries/Compact.pretty'
        d.mkdir(parents=True, exist_ok=True)
        (d / (ESP + '.kicad_mod')).write_text(esp32())


def apply_esp():
    import json, pcbnew as p
    pcb = ROOT / 'core/core.kicad_pcb'
    b = p.LoadBoard(str(pcb))
    comp = next(c for c in json.load(open(ROOT / 'design-master.json'))['components'] if c['ref'] == 'MCU1')
    nets = {q['number']: q['net'] for q in comp['pins']}
    for f in list(b.GetFootprints()):
        if f.GetReference() != 'MCU1':
            continue
        new = p.FootprintLoad(str(ROOT / 'core/libraries/Compact.pretty'), ESP)
        new.SetReference('MCU1'); new.SetValue(f.GetValue()); new.Reference().SetVisible(False); new.Value().SetVisible(False)
        new.SetPosition(f.GetPosition()); new.SetOrientation(f.GetOrientation())
        for pd in new.Pads():
            n = nets.get(pd.GetNumber())
            if n:
                ni = b.FindNet(n)
                if ni is None:
                    ni = p.NETINFO_ITEM(b, n); b.Add(ni)
                pd.SetNet(ni)
        b.Remove(f); b.Add(new)
    p.SaveBoard(str(pcb), b)


if __name__ == '__main__':
    write()
    if '--apply' in sys.argv:
        apply_esp()
