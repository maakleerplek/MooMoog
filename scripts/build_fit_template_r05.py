#!/usr/bin/env python3
"""1:1 fit template: pads, drill holes and body outlines of the verified-in-progress footprints.
Print at 100 % (no scaling) on paper, push the real part's pins through the drill circles, and check
pin pitch, tab slots and body outline. Writes hardware/split-r0.5/reports/fit-template-controls.pdf.
Needs KiCad's pcbnew and kicad-cli."""
import subprocess
from pathlib import Path
import pcbnew as p
R = Path(__file__).resolve().parents[1] / 'hardware/split-r0.5'
LIB = str(R / 'control/libraries/Compact.pretty')
V = lambda x, y: p.VECTOR2I(p.FromMM(x), p.FromMM(y))

def main():
    b = p.BOARD()
    items = [('Pot_B10K_RD901F_Vertical', 'RV', 25, 25), ('SS12D10_Slide_3P_P4.7', 'S', 70, 25), ('E1', 'E', 115, 25)]
    for name, ref, x, y in items:
        fp = p.FootprintLoad(LIB, name)
        fp.SetReference(ref); fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
        fp.SetPosition(V(x, y)); b.Add(fp)
        lab = p.PCB_TEXT(b); lab.SetText(name); lab.SetPosition(V(x, y + 17)); lab.SetLayer(p.F_SilkS); lab.SetTextSize(V(1.2, 1.2)); b.Add(lab)
    for a, z in [((0, 0), (150, 0)), ((150, 0), (150, 55)), ((150, 55), (0, 55)), ((0, 55), (0, 0))]:
        s = p.PCB_SHAPE(); s.SetShape(p.SHAPE_T_SEGMENT); s.SetStart(V(*a)); s.SetEnd(V(*z)); s.SetLayer(p.Edge_Cuts); s.SetWidth(p.FromMM(0.1)); b.Add(s)
    # 10 mm scale bar to verify the print is 100 %
    s = p.PCB_SHAPE(); s.SetShape(p.SHAPE_T_SEGMENT); s.SetStart(V(10, 50)); s.SetEnd(V(30, 50)); s.SetLayer(p.F_SilkS); s.SetWidth(p.FromMM(0.3)); b.Add(s)
    t = p.PCB_TEXT(b); t.SetText('20 mm scale bar - must measure 20 mm'); t.SetPosition(V(22, 46.5)); t.SetLayer(p.F_SilkS); t.SetTextSize(V(1.2, 1.2)); b.Add(t)
    tmp = R / 'reports/fit-template.kicad_pcb'
    p.SaveBoard(str(tmp), b)
    subprocess.run(['kicad-cli', 'pcb', 'export', 'pdf', '--layers', 'F.Cu,F.SilkS,F.Fab,Edge.Cuts', '--black-and-white', '--drill-shape-opt', '2',
                    '-o', str(R / 'reports/fit-template-controls.pdf'), str(tmp)], check=True, capture_output=True)
    tmp.unlink()

if __name__ == '__main__':
    main()
