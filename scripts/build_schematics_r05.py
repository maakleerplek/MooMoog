#!/usr/bin/env python3
"""Generate readable KiCad schematics for R0.5 (control + core) from design-master.json.

Follows docs/plan-r0.5.md: one section frame per function, standard KiCad symbols for
R/C/LED/pot/encoder/SPDT/jack/connector, block symbols (functional pin names) for purchased
modules, named net labels between sections.  Net names are identical to the PCB netlist
(power symbols carry the net name as their Value, e.g. "3V3").

Usage: python3 scripts/build_schematics_r05.py        (writes <board>/<board>.kicad_sch)
"""
import copy, json, math, re, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HW = ROOT / 'hardware/split-r0.5'
SYMDIR = Path('/usr/share/kicad/symbols')
DESIGN = json.load(open(HW / 'design-master.json'))
COMP = {c['ref']: c for c in DESIGN['components']}
CTRL = {c['ref']: c for c in DESIGN['controls']}
SWITCH = {s['ref']: s for s in DESIGN['switches']}


# ---------------------------------------------------------------- s-expression helpers
def parse(s):
    st = [[]]
    for m in re.finditer(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+)', s):
        t = m.group(1)
        if t == '(':
            st.append([])
        elif t == ')':
            x = st.pop(); st[-1].append(x)
        else:
            st[-1].append(t)
    return st[0][0]


def dump(x):
    return '(' + ' '.join(dump(y) if isinstance(y, list) else y for y in x) + ')'


def find(x, k):
    return [y for y in x if isinstance(y, list) and y and y[0] == k]


def sym_pins(x):
    out = []
    for y in x:
        if isinstance(y, list) and y:
            if y[0] == 'pin':
                a = find(y, 'at')[0]
                out.append(dict(name=find(y, 'name')[0][1].strip('"'), number=find(y, 'number')[0][1].strip('"'),
                                x=float(a[1]), y=float(a[2]), ang=int(float(a[3])) % 360))
            else:
                out += sym_pins(y)
    return out


_libs = {}


def libsym(lib, name):
    if lib not in _libs:
        t = parse((SYMDIR / f'{lib}.kicad_sym').read_text())
        _libs[lib] = {x[1].strip('"'): x for x in find(t, 'symbol')}
    s = copy.deepcopy(_libs[lib][name]); s[1] = f'"{lib}:{name}"'
    return s


def U(tag):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'split-r05/sch/' + tag))


def q(s):
    return '"' + str(s).replace('"', "'") + '"'


def snap(v):
    return round(round(v / 1.27) * 1.27, 3)


def r3(v):
    return round(v + 0.0, 3)


FONT = '(font (size 1.27 1.27))'
POWER = {'GND': ('GND', 270), '3V3': ('+3V3', 90), 'SYS_5V': ('+5V', 90)}


def block_symbol(name, left, right, w=35.56, ref='U'):
    """Rectangular module symbol. left/right: lists of pin names or None (gap)."""
    n = max(len(left), len(right)) + 1
    h = math.ceil(n * 2.54 / 5.08) * 5.08
    hw = w / 2
    pins = []
    for side, lst in ((0, left), (1, right)):
        for i, nm in enumerate(lst):
            if nm is None:
                continue
            y = h / 2 - 2.54 * (i + 1)
            x, ang = (-(hw + 5.08), 0) if side == 0 else (hw + 5.08, 180)
            pins.append(f'(pin passive line (at {r3(x)} {r3(y)} {ang}) (length 5.08) (name {q(nm)} (effects {FONT})) (number {q(nm)} (effects {FONT})))')
    txt = (f'(symbol {q("Compact:" + name)} (pin_numbers (hide yes)) (pin_names (offset 0.762)) (exclude_from_sim no) (in_bom yes) (on_board yes)'
           f'(property "Reference" {q(ref)} (at 0 {r3(h / 2 + 2.54)} 0) (effects {FONT}))'
           f'(property "Value" {q(name)} (at 0 {r3(-h / 2 - 2.54)} 0) (effects {FONT}))'
           f'(property "Footprint" "" (at 0 0 0) (effects {FONT} (hide yes)))'
           f'(property "Datasheet" "" (at 0 0 0) (effects {FONT} (hide yes)))'
           f'(symbol {q(name + "_0_1")} (rectangle (start {r3(-hw)} {r3(h / 2)}) (end {r3(hw)} {r3(-h / 2)}) (stroke (width 0.254) (type default)) (fill (type background))))'
           f'(symbol {q(name + "_1_1")} {" ".join(pins)}))')
    return parse(txt), h


class Placed:
    def __init__(self, sheet, sym, x, y, rot):
        self.x, self.y, self.rot = x, y, rot
        self.pins = {}
        for p in sym_pins(sym):
            c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            rx, ry = p['x'] * c - p['y'] * s, p['x'] * s + p['y'] * c
            ang = (p['ang'] + rot) % 360
            out = (-round(math.cos(math.radians(ang))), round(math.sin(math.radians(ang))))  # y-down outward
            d = dict(x=r3(x + rx), y=r3(y - ry), out=out, number=p['number'], name=p['name'])
            self.pins.setdefault(p['number'], d)
            self.pins.setdefault('name:' + p['name'], d)

    def pin(self, key):
        return self.pins[key] if key in self.pins else self.pins['name:' + key]


class Sheet:
    def __init__(self, board, title, rev='0.5'):
        self.board, self.title = board, title
        self.root = U(board)
        self.libs = {}
        self.body = []
        self.n = 0
        self.pwr = 0
        self.xmax = self.ymax = 0

    def _track(self, x, y):
        self.xmax = max(self.xmax, x); self.ymax = max(self.ymax, y)

    def add_lib(self, sym):
        self.libs[sym[1]] = sym

    def uid(self, tag):
        self.n += 1
        return U(f'{self.board}/{tag}/{self.n}')

    # ---- drawing primitives
    def wire(self, a, b):
        if a == b:
            return
        self._track(*a); self._track(*b)
        self.body.append(f'(wire (pts (xy {r3(a[0])} {r3(a[1])}) (xy {r3(b[0])} {r3(b[1])})) (stroke (width 0) (type default)) (uuid {q(self.uid("w"))}))')

    def junction(self, x, y):
        self.body.append(f'(junction (at {r3(x)} {r3(y)}) (diameter 0) (color 0 0 0 0) (uuid {q(self.uid("j"))}))')

    def noconnect(self, x, y):
        self.body.append(f'(no_connect (at {r3(x)} {r3(y)}) (uuid {q(self.uid("nc"))}))')

    def label(self, net, x, y, d):
        rot, just = {(1, 0): (0, 'left'), (-1, 0): (180, 'right'), (0, -1): (90, 'left'), (0, 1): (270, 'left')}[d]
        self.body.append(f'(label {q(net)} (at {r3(x)} {r3(y)} {rot}) (effects {FONT} (justify {just} bottom)) (uuid {q(self.uid("l"))}))')

    def text(self, s, x, y, size=1.27, bold=False, just='left'):
        self._track(x + len(s) * size * 0.6, y)
        b = ' (bold yes)' if bold else ''
        self.body.append(f'(text {q(s)} (exclude_from_sim no) (at {r3(x)} {r3(y)} 0) (effects (font (size {size} {size}){b}) (justify {just} bottom)) (uuid {q(self.uid("t"))}))')

    def frame(self, x1, y1, x2, y2, title, note=None):
        self._track(x2, y2)
        self.body.append(f'(rectangle (start {r3(x1)} {r3(y1)}) (end {r3(x2)} {r3(y2)}) (stroke (width 0.3) (type dash)) (fill (type none)) (uuid {q(self.uid("f"))}))')
        self.text(title, x1 + 3, y1 + 6, 3.0, True)
        if note:
            self.text(note, x1 + 3, y1 + 11, 1.5)

    # ---- symbols
    def place(self, sym, ref, value, x, y, rot=0, ref_at=None, val_at=None, dnp=False, hide_ref=False, hide_val=False, jus='left'):
        x, y = snap(x), snap(y)
        self.add_lib(sym)
        pl = Placed(self, sym, x, y, rot)
        libid = sym[1]
        if rot == 180:
            jus = 'right' if jus == 'left' else 'left'      # KiCad mirrors justification on 180 deg symbols
        ra = ref_at or (x + 3, y - 2.54)
        va = val_at or (x + 3, y + 1.27)
        hr = ' (hide yes)' if hide_ref else ''
        hv = ' (hide yes)' if hide_val else ''
        pa = (-rot) % 360 if rot in (90, 270) else 0
        pins = ' '.join(f'(pin {q(p["number"])} (uuid {q(self.uid("p"))}))' for k, p in pl.pins.items() if not k.startswith('name:'))
        self.body.append(
            f'(symbol (lib_id {libid}) (at {r3(x)} {r3(y)} {rot}) (unit 1) (exclude_from_sim no) (in_bom {"no" if dnp else "yes"}) (on_board yes) (dnp {"yes" if dnp else "no"}) (uuid {q(self.uid("s"))})'
            f'(property "Reference" {q(ref)} (at {r3(ra[0])} {r3(ra[1])} {pa}) (effects {FONT} (justify {jus})){hr})'
            f'(property "Value" {q(value)} (at {r3(va[0])} {r3(va[1])} {pa}) (effects {FONT} (justify {jus})){hv})'
            f'(property "Footprint" "" (at {r3(x)} {r3(y)} 0) (effects {FONT} (hide yes)))'
            f'(property "Datasheet" "~" (at {r3(x)} {r3(y)} 0) (effects {FONT} (hide yes)))'
            f' {pins} (instances (project {q(self.board)} (path "/{self.root}" (reference {q(ref)}) (unit 1)))))')
        return pl

    def power(self, net, x, y, d, hide_value=False):
        name, native = POWER[net]
        sym = libsym('power', name)
        self.add_lib(sym)
        want = round(math.degrees(math.atan2(-d[1], d[0]))) % 360
        rot = (want - native) % 360
        self.pwr += 1
        ref = f'#PWR{self.pwr:03d}'
        off = {(0, -1): (0, -3.4, 'center'), (0, 1): (0, 4.4, 'center'), (1, 0): (4.2, 0, 'left'), (-1, 0): (-4.2, 0, 'right')}[d]
        pa = (-rot) % 360 if rot in (90, 270) else 0
        self.body.append(
            f'(symbol (lib_id {sym[1]}) (at {r3(x)} {r3(y)} {rot}) (unit 1) (exclude_from_sim no) (in_bom no) (on_board yes) (dnp no) (uuid {q(self.uid("s"))})'
            f'(property "Reference" {q(ref)} (at {r3(x)} {r3(y)} 0) (effects {FONT} (hide yes)))'
            f'(property "Value" {q(net)} (at {r3(x + off[0])} {r3(y + off[1])} {pa}) (effects {FONT}{"" if off[2] == "center" else " (justify " + off[2] + ")"}{" (hide yes)" if hide_value else ""}))'
            f'(property "Footprint" "" (at {r3(x)} {r3(y)} 0) (effects {FONT} (hide yes)))'
            f'(property "Datasheet" "" (at {r3(x)} {r3(y)} 0) (effects {FONT} (hide yes)))'
            f' (pin "1" (uuid {q(self.uid("p"))})) (instances (project {q(self.board)} (path "/{self.root}" (reference {q(ref)}) (unit 1)))))')

    def stub(self, pl, key, net, length=5.08, hide_value=False):
        """Wire a pin out to a power symbol (power nets) or a net label (signals); None = no-connect."""
        p = pl.pin(key)
        px, py = p['x'], p['y']
        if net is None:
            self.noconnect(px, py)
            return
        ox, oy = p['out']
        ex, ey = px + ox * length, py + oy * length
        self.wire((px, py), (ex, ey))
        if net in POWER:
            self.power(net, ex, ey, (ox, oy), hide_value)
        elif oy != 0:           # vertical stub: dog-leg so the label reads horizontally
            lx = ex + 3.81
            self.wire((ex, ey), (lx, ey))
            self.label(net, lx, ey, (1, 0))
        else:
            self.label(net, ex, ey, (ox, oy))

    def connect(self, pa, ka, pb, kb):
        a, b = pa.pin(ka), pb.pin(kb)
        self.wire((a['x'], a['y']), (b['x'], b['y']))

    def render(self, paper, extra_title=''):
        libs = ' '.join(dump(s) for s in self.libs.values())
        head = (f'(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (uuid {q(self.root)}) (paper {q(paper)})'
                f' (title_block (title {q(self.title)}) (date "2026-11-15") (rev "0.5") (comment 1 "Functional schematic generated from docs/plan-r0.5.md; NOT FOR MANUFACTURE") (comment 2 "Module pin numbers are placeholders until headers are measured"))'
                f' (lib_symbols {libs}) ')
        return head + ' '.join(self.body) + ' (sheet_instances (path "/" (page "1"))) (embedded_fonts no))'


# ---------------------------------------------------------------- shared part helpers
def design_pins(ref):
    return {p['number']: p['net'] for p in COMP[ref]['pins']}


def vertical_two_pin(sh, lib, name, ref, x, y, top, bot, value=None, dnp=False):
    """Vertical R/C between nets `top` (up) and `bot` (down). Pin nets are taken from the design."""
    pins = design_pins(ref)
    sym = libsym(lib, name)
    rot = 0 if (pins['1'] == top and pins['2'] == bot) else 180
    if rot == 180:
        assert pins['2'] == top and pins['1'] == bot, (ref, pins, top, bot)
    pl = sh.place(sym, ref, value or COMP[ref]['value'], x, y, rot, ref_at=(x + 3.5, y - 1.9), val_at=(x + 3.5, y + 1.9), dnp=dnp)
    sh.stub(pl, '1' if rot == 0 else '2', top)
    sh.stub(pl, '2' if rot == 0 else '1', bot)
    return pl


def module(sh, ref, left, right, title, w=35.56, x=0, y=0):
    """Block symbol for a purchased module; every pin is stubbed to its design net."""
    pins = design_pins(ref)
    name = re.sub(r'[^A-Za-z0-9_+-]', '_', title)
    sym, h = block_symbol(name, left, right, w, ref=ref[:2])
    pl = sh.place(sym, ref, COMP[ref]['value'], x, y, 0, ref_at=(x - w / 2, y - h / 2 - 3.5), val_at=(x - w / 2, y - h / 2 - 1.2))
    for nm in [n for n in left + right if n]:
        sh.stub(pl, nm, pins[nm])
    return pl, h


def paper_for(w, h):
    for name, pw, ph in (('A4', 297, 210), ('A3', 420, 297), ('A2', 594, 420), ('A1', 841, 594), ('A0', 1189, 841)):
        if w + 15 <= pw and h + 25 <= ph:
            return name
    return 'A0'


def ribbon(sh, ref, x, y):
    """12-way ribbon pads, pins on the right, one label/power symbol per wire."""
    pins = design_pins(ref)
    sym = libsym('Connector_Generic', 'Conn_01x12')
    pl = sh.place(sym, ref, COMP[ref]['value'], x, y, 180, ref_at=(x - 8, y - 20), val_at=(x - 8, y - 17.5))
    for i in range(1, 13):
        sh.stub(pl, str(i), pins[str(i)], 3.81 if pins[str(i)] == 'GND' else 7.62, hide_value=pins[str(i)] == 'GND')
        p = pl.pin(str(i))
        sh.text(f'wire {i}', p['x'] - 13.5, p['y'] + 0.6, 1.0, False, 'right')
    return pl


# ---------------------------------------------------------------- control board
def control():
    sh = Sheet('control', 'Compact D R0.5 - CONTROL board (sloped, under panel)')

    # 1. ribbon, power, bus
    sh.frame(10, 10, 205, 150, '1  Ribbon, power and bus', 'Only link to the core board. 3V3 in, GND returns on even wires.')
    ribbon(sh, 'JPANEL', 45, 68)
    vertical_two_pin(sh, 'Device', 'C', 'CP1', 120, 50, '3V3', 'GND')
    vertical_two_pin(sh, 'Device', 'C_Polarized', 'CP2', 138, 50, '3V3', 'GND')
    sh.text('decoupling 100 nF + 10 uF', 112, 33, 1.27)
    vertical_two_pin(sh, 'Device', 'R', 'RP2', 165, 50, '3V3', 'IO_RESET')
    sh.text('MCP reset pull-up', 158, 33, 1.27)
    vertical_two_pin(sh, 'Device', 'R', 'RP3', 120, 100, '3V3', 'I2C_SDA', dnp=True)
    vertical_two_pin(sh, 'Device', 'R', 'RP4', 138, 100, '3V3', 'I2C_SCL', dnp=True)
    sh.text('optional I2C pull-ups (DNP)', 112, 83, 1.27)
    # power LED: 3V3 -> LED (anode up) -> RP1 -> GND
    led = sh.place(libsym('Device', 'LED'), 'LED2', 'Power LED', 175, 98, 90, ref_at=(179, 97), val_at=(179, 99.5))
    sh.stub(led, '2', '3V3')
    rp1 = sh.place(libsym('Device', 'R'), 'RP1', '1k', 175, 116, 0, ref_at=(178, 114.5), val_at=(178, 117.5))
    sh.connect(led, '1', rp1, '1')
    kp = led.pin('1')
    sh.label('PWR_LED', kp['x'], kp['y'] + 5.08, (1, 0))
    sh.wire((kp['x'], kp['y']), (kp['x'], kp['y'] + 5.08))
    sh.stub(rp1, '2', 'GND')
    sh.text('power LED', 168, 83, 1.27)

    # 2. I/O expanders
    sh.frame(215, 10, 560, 150, '2  I/O expanders (MCP23017 modules)',
             'Contacts on GPA0-6 / GPB0-6, INTA -> PANEL_IRQ, GPA7/GPB7 drive the mux select lines.')
    left = ['VDD', 'VSS', None, 'SDA', 'SCL', 'RESET', 'INTA', 'INTB', None, 'A0', 'A1', 'A2']
    right = [f'GPA{i}' for i in range(8)] + [None] + [f'GPB{i}' for i in range(8)]
    for i, ref in enumerate(('IO1', 'IO2', 'IO3')):
        addr = COMP[ref]['value'].split('/')[-1].strip()
        module(sh, ref, left, right, 'MCP23017_module', x=275 + i * 105, y=85)
        sh.text(f'I2C address {addr}', 275 + i * 105 - 17, 122, 1.27)

    # 3. analog multiplexers
    sh.frame(570, 10, 810, 150, '3  Analog multiplexers (CD74HC4067 modules)',
             'Pot wipers in, one selected wiper out (SIG). Selects are shared.')
    left = [f'C{i}' for i in range(16)]
    right = ['SIG', None, 'S0', 'S1', 'S2', 'S3', None, 'EN', None, 'VCC', 'GND']
    for i, ref in enumerate(('MX1', 'MX2')):
        module(sh, ref, left, right, 'CD74HC4067_module', w=30.48, x=625 + i * 100, y=85)

    # 4. potentiometers
    sh.frame(10, 160, 330, 322, '4  Potentiometers (B10K) - 3V3 / GND / wiper',
             'RVn_W goes to the mux input named in docs/plan-r0.5.md.')
    pots = [c for c in DESIGN['controls'] if c['kind'] == 'pot']
    for i, c in enumerate(pots):
        col, row = i % 5, i // 5
        x, y = 38 + col * 60, 196 + row * 32
        pl = sh.place(libsym('Device', 'R_Potentiometer'), c['ref'], f'B10K {c["label"]}', x, y, 180,
                      ref_at=(x + 6, y - 2.2), val_at=(x + 6, y + 1.4))
        pins = design_pins(c['ref'])
        sh.stub(pl, '3', pins['HIGH'], 3.81)
        sh.stub(pl, '1', pins['LOW'], 3.81)
        sh.stub(pl, '2', pins['WIPER'], 5.08)

    # 5. encoders
    sh.frame(340, 160, 580, 272, '5  Rotary encoders (EC11 with push switch)',
             'A/B quadrature to MCP inputs; common and push return to GND.')
    encs = [c for c in DESIGN['controls'] if c['kind'] == 'encoder']
    for i, c in enumerate(encs):
        col, row = i % 4, i // 4
        x, y = 375 + col * 58, 205 + row * 38
        pl = sh.place(libsym('Device', 'RotaryEncoder_Switch'), c['ref'], f'EC11 {c["label"]}', x, y, 0,
                      ref_at=(x - 8, y - 7.5), val_at=(x - 8, y + 8.5))
        pins = design_pins(c['ref'])
        sh.stub(pl, 'A', pins['A'], 5.08)
        sh.stub(pl, 'C', pins['C'], 5.08)
        sh.stub(pl, 'B', pins['B'], 5.08)
        sh.stub(pl, 'S1', pins['SW1'], 5.08)
        sh.stub(pl, 'S2', pins['SW2'], 5.08)

    # 6. switches
    sh.frame(340, 282, 810, 380, '6  Slide switches (SPDT, ON contact to MCP)',
             'Common to GND; the ON throw pulls the MCP input low, the other throw is unused.')
    for i, s in enumerate(DESIGN['switches']):
        col, row = i % 6, i // 6
        x, y = 375 + col * 75, 315 + row * 30
        pl = sh.place(libsym('Switch', 'SW_SPDT'), s['ref'], s['label'], x, y, 0, ref_at=(x - 6, y - 5.5), val_at=(x - 6, y + 7))
        pins = design_pins(s['ref'])
        sh.stub(pl, '2', pins['COM'], 5.08)
        sh.stub(pl, '1', pins['ON'], 5.08)
        sh.stub(pl, '3', pins['OFF'])
    return sh


# ---------------------------------------------------------------- core board
def core():
    sh = Sheet('core', 'Compact D R0.5 - CORE board (flat electronics)')

    # 1. ribbon & power rails
    sh.frame(10, 10, 150, 135, '1  Ribbon and rails', 'Mirror of the control ribbon, pin 1 to pin 1.')
    ribbon(sh, 'JCORE', 45, 68)
    vertical_two_pin(sh, 'Device', 'C', 'CC1', 85, 110, '3V3', 'GND')
    vertical_two_pin(sh, 'Device', 'C_Polarized', 'CC2', 105, 110, 'SYS_5V', 'GND')
    sh.text('3V3 decoupling / 5 V bulk', 78, 92, 1.27)
    vertical_two_pin(sh, 'Device', 'R', 'RP5', 130, 110, '3V3', 'PANEL_IRQ')
    sh.text('IRQ pull-up', 123, 92, 1.27)

    # 2. pot filters
    sh.frame(160, 10, 270, 100, '2  Pot analog filters', '1 kOhm + 1 nF at the ADC pins.')
    for i, (rr, cc, a, b) in enumerate((('RA1', 'CA1', 'POT_ADC1', 'POT_ADC1_FILTER'), ('RA2', 'CA2', 'POT_ADC2', 'POT_ADC2_FILTER'))):
        x, y = 195, 38 + i * 30
        r = sh.place(libsym('Device', 'R'), rr, COMP[rr]['value'], x, y, 90, ref_at=(x - 4, y - 5.5), val_at=(x - 4, y + 7))
        sh.stub(r, '1', a)
        p2 = r.pin('2')
        jx = p2['x'] + 5.08
        sh.wire((p2['x'], p2['y']), (jx, p2['y']))
        sh.wire((jx, p2['y']), (jx + 5.08, p2['y']))
        sh.label(b, jx + 5.08, p2['y'], (1, 0))
        sh.junction(jx, p2['y'])
        c = sh.place(libsym('Device', 'C'), cc, COMP[cc]['value'], jx, p2['y'] + 7.62, 0, ref_at=(jx + 3, p2['y'] + 5.7), val_at=(jx + 3, p2['y'] + 9.5))
        sh.wire((jx, p2['y']), (c.pin('1')['x'], c.pin('1')['y']))
        sh.stub(c, '2', 'GND', 2.54)

    # 3. ESP32
    sh.frame(280, 10, 410, 135, '3  ESP32-S3 module', 'ARCELI N16R8: synth engine, panel scan, I2S audio.')
    left = ['5V', '3V3', 'GND', None, 'GPIO1', 'GPIO2', None, 'GPIO4', 'GPIO5', None, 'GPIO10']
    right = ['GPIO15', 'GPIO16', 'GPIO17', None, 'GPIO41', 'GPIO40']
    module(sh, 'MCU1', left, right, 'ESP32-S3_module', w=30.48, x=345, y=85)
    sh.text('USB-UART port: power + programming', 285, 118, 1.27)
    sh.text('native USB: keyboard (host mode)', 285, 123, 1.27)
    sh.text('keyboard VBUS path: OPEN', 285, 128, 1.27)

    # 4. DAC
    sh.frame(420, 10, 570, 135, '4  PCM5102 DAC module', 'L = main, R = headphones. PLL mode (SCK low), I2S format.')
    left = ['VIN', 'GND', None, 'BCK', 'LCK', 'DIN', None, 'SCK', 'FMT', None, 'XSMT']
    right = ['OUTL', 'OUTR']
    module(sh, 'DAC1', left, right, 'PCM5102_DAC_module', w=30.48, x=480, y=85)
    vertical_two_pin(sh, 'Device', 'R', 'RA6', 440, 112, 'DAC_MUTE_N', 'GND')
    sh.text('mute default', 433, 92, 1.27)

    # 5. outputs
    sh.frame(10, 145, 570, 275, '5  Outputs', 'Main: 100 R series to the rear jack.  Phones: attenuator into the TPA6132 module.')
    ra3 = sh.place(libsym('Device', 'R'), 'RA3', '100R', 75, 178, 90, ref_at=(71, 172.5), val_at=(71, 184))
    sh.stub(ra3, '1', 'MAIN_RAW')
    p2 = ra3.pin('2')
    sh.stub(ra3, '2', 'MAIN_LINE')
    jack = sh.place(libsym('Connector_Audio', 'AudioJack3'), 'JMAIN', COMP['JMAIN']['value'], 200, 178, 180, ref_at=(185, 167), val_at=(185, 189.5))
    jp = design_pins('JMAIN')
    sh.stub(jack, 'S', jp['SLEEVE'])
    sh.stub(jack, 'R', jp['RING'])
    sh.stub(jack, 'T', jp['TIP'])
    sh.text('main output: tip and ring tied (mono)', 160, 196, 1.27)
    ra4 = sh.place(libsym('Device', 'R'), 'RA4', '10k', 75, 228, 90, ref_at=(71, 222.5), val_at=(71, 234))
    sh.stub(ra4, '1', 'PHONES_RAW')
    p2 = ra4.pin('2')
    jx = p2['x'] + 5.08
    sh.wire((p2['x'], p2['y']), (jx, p2['y']))
    sh.wire((jx, p2['y']), (jx + 7.62, p2['y']))
    sh.label('HP_FEED', jx + 7.62, p2['y'], (1, 0))
    sh.junction(jx, p2['y'])
    ra5 = sh.place(libsym('Device', 'R'), 'RA5', '4k7', jx, p2['y'] + 8, 0, ref_at=(jx + 3, p2['y'] + 6.1), val_at=(jx + 3, p2['y'] + 9.9))
    sh.wire((jx, p2['y']), (ra5.pin('1')['x'], ra5.pin('1')['y']))
    sh.stub(ra5, '2', 'GND', 2.54)
    sh.text('phones attenuator', 55, 210, 1.27)
    left = ['VCC', 'GND', None, 'L-', 'R-', 'L+', 'R+', None, 'CTRL', 'DET']
    right = ['OUTL', 'OUTR']
    module(sh, 'HP1', left, right, 'TPA6132_headphone_module', w=30.48, x=360, y=228)
    sh.text('onboard 3.5 mm headphone jack', 330, 258, 1.27)
    vertical_two_pin(sh, 'Device', 'R', 'RA7', 470, 240, 'HP_EN', 'GND')
    sh.text('enable default', 463, 222, 1.27)
    return sh


def main():
    for name, fn in (('control', control), ('core', core)):
        sh = fn()
        paper = paper_for(sh.xmax, sh.ymax)
        out = HW / name / f'{name}.kicad_sch'
        out.write_text(sh.render(paper))
        print(name, paper, int(sh.xmax), int(sh.ymax), len(sh.body), 'items ->', out.relative_to(ROOT))


if __name__ == '__main__':
    main()
