#!/usr/bin/env python3
"""Build the HTML documentation (docs/html/index.html) from the same data as docs/plan-r0.5.md.

The markdown plan stays the source of truth for prose and the Mermaid diagrams; this script
only produces a browsable copy. Needs: mmdc (Mermaid CLI) and kicad-cli on PATH.
Usage: python3 scripts/build_docs_r05.py
"""
import csv, html, json, re, shutil, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HW = ROOT / 'hardware/split-r0.5'
OUT = ROOT / 'docs/html'
ASSETS = OUT / 'assets'
ASSETS.mkdir(parents=True, exist_ok=True)
D = json.load(open(HW / 'design-master.json'))
AUDIT = json.load(open(HW / 'reports/completion-audit.json'))
SCAN = list(csv.DictReader(open(HW / 'scan.csv')))
e = html.escape
GH = 'https://github.com/maakleerplek/MooMoog/blob/main/'   # Markdown opens rendered on GitHub; Pages would serve it raw


def table(head, rows, cls=''):
    h = ''.join(f'<th>{e(str(x))}</th>' for x in head)
    b = ''.join('<tr>' + ''.join(f'<td>{c if str(c).startswith("<") else e(str(c))}</td>' for c in r) + '</tr>' for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def mermaid_svgs():
    md = (ROOT / 'docs/plan-r0.5.md').read_text()
    blocks = re.findall(r'```mermaid\n(.*?)```', md, re.S)
    names = ['diagram-power.svg', 'diagram-signal.svg']
    with tempfile.TemporaryDirectory() as td:
        for blk, name in zip(blocks, names):
            src = Path(td) / (name + '.mmd')
            src.write_text(blk)
            subprocess.run(['mmdc', '-i', str(src), '-o', str(ASSETS / name), '-b', 'white', '-w', '1100'], check=True, capture_output=True)
    return names


def schematic_svgs():
    with tempfile.TemporaryDirectory() as td:
        for b in ('control', 'core'):
            subprocess.run(['kicad-cli', 'sch', 'export', 'svg', '-o', td, str(HW / b / f'{b}.kicad_sch')], check=True, capture_output=True)
            shutil.copy(Path(td) / f'{b}.svg', ASSETS / f'schematic-{b}.svg')


def ports():
    pots = [c for c in D['controls'] if c['kind'] == 'pot']
    encs = [c for c in D['controls'] if c['kind'] == 'encoder']
    t_pots = table(['Pot', 'Function', 'Mux', 'Channel', 'Net'], [(c['ref'], f"{c['label']} ({c['param']})", c['mux'], c['channel'], c['net']) for c in pots])
    t_enc = table(['Encoder', 'Function', 'A / B / push &rarr; MCP port'.replace('&rarr;', '→')],
                  [(c['ref'], f"{c['label']} ({c['param']})", ', '.join(f"{s['pin']}→{s['module']}.{s['port']}" for s in SCAN if s['control'] == c['ref'])) for c in encs])
    t_sw = table(['Switch', 'Function', 'Net', 'MCP port'],
                 [(s['ref'], f"{s['label']} ({s['param']})", s['ref'] + '_ON', next(f"{x['module']}.{x['port']}" for x in SCAN if x['control'] == s['ref'])) for s in D['switches']])
    t_io = table(['Module', 'I²C address', 'Strap A0 / A1 / A2', 'GPA7 / GPB7 outputs'],
                 [('IO1', '0x20', 'GND / GND / GND', 'MUX_S0 / MUX_S1'), ('IO2', '0x21', '3V3 / GND / GND', 'MUX_S2 / MUX_S3'), ('IO3', '0x22', 'GND / 3V3 / GND', 'unused (low)')])
    t_rib = table(['Wire', 'Net', 'Role'], [(1, '3V3', 'control board supply'), (2, 'GND', 'return'), (3, 'I2C_SDA', 'ESP GPIO1 ↔ MCP SDA'), (4, 'GND', 'return'),
                  (5, 'I2C_SCL', 'ESP GPIO2 ↔ MCP SCL'), (6, 'GND', 'return'), (7, 'POT_ADC1', 'MX1 SIG → filter → GPIO4'), (8, 'GND', 'return'),
                  (9, 'POT_ADC2', 'MX2 SIG → filter → GPIO5'), (10, 'GND', 'return'), (11, 'PANEL_IRQ', 'MCP INTA (wire-OR) → GPIO10'), (12, 'GND', 'return')])
    t_mcu = table(['ESP32-S3 pin', 'Net', 'Goes to', 'Direction'], [
        ('5V (USB)', 'SYS_5V', 'DAC VIN, CC2 bulk cap', 'power in from USB-UART port'), ('3V3', '3V3', 'ribbon 1, HP1 VCC, CC1', 'power out (module regulator)'),
        ('GPIO1', 'I2C_SDA', 'ribbon 3 → MCP SDA', 'I²C data'), ('GPIO2', 'I2C_SCL', 'ribbon 5 → MCP SCL', 'I²C clock'),
        ('GPIO4', 'POT_ADC1_FILTER', 'RA1/CA1 ← ribbon 7 ← MX1', 'ADC in'), ('GPIO5', 'POT_ADC2_FILTER', 'RA2/CA2 ← ribbon 9 ← MX2', 'ADC in'),
        ('GPIO10', 'PANEL_IRQ', 'ribbon 11 ← MCP INTA (RP5 pull-up)', 'interrupt in'), ('GPIO15', 'I2S_BCLK', 'DAC BCK', 'I²S out'),
        ('GPIO16', 'I2S_LRCLK', 'DAC LCK', 'I²S out'), ('GPIO17', 'I2S_TX', 'DAC DIN', 'I²S out'), ('GPIO40', 'HP_EN', 'HP1 CTRL (RA7 pull-down)', 'output'),
        ('GPIO41', 'DAC_MUTE_N', 'DAC XSMT (RA6 pull-down)', 'output'), ('native USB', '—', 'USB-MIDI keyboard (host mode), power OPEN', 'USB host')])
    return t_pots, t_enc, t_sw, t_io, t_rib, t_mcu


CSS = """
:root{--bg:#fafaf7;--fg:#1b1d1f;--mut:#5d636a;--line:#d9dbd5;--card:#fff;--acc:#1f4fbf;--warn:#b45309;--warnbg:#fff4e0;--head:#eef0ea}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14161a;--fg:#e8e9e6;--mut:#9aa1a9;--line:#2c3038;--card:#1b1e24;--acc:#8fb1ff;--warn:#f0b35c;--warnbg:#2a2113;--head:#20242b}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,'Segoe UI',sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px 80px}
header{padding:36px 0 12px}h1{font-size:2rem;margin:0 0 4px}h2{font-size:1.5rem;margin:48px 0 12px;padding-top:8px;border-top:1px solid var(--line)}h3{font-size:1.15rem;margin:28px 0 8px}
p,li{max-width:75ch}.lead{font-size:1.1rem;color:var(--mut)}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);z-index:5;margin:0 -16px;padding:8px 16px;display:flex;gap:6px 16px;flex-wrap:wrap;font-size:.9rem}
nav a{color:var(--acc);text-decoration:none}nav a:hover{text-decoration:underline}
.banner{background:var(--warnbg);border-left:4px solid var(--warn);padding:12px 16px;border-radius:6px;margin:16px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.card b{display:block;font-size:1.6rem;line-height:1.2}
.tw{overflow-x:auto;margin:12px 0}table{border-collapse:collapse;width:100%;font-size:.92rem;background:var(--card)}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}th{background:var(--head);position:sticky;top:0}
code{background:var(--head);padding:1px 5px;border-radius:4px;font-size:.88em}
.fig{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px;margin:16px 0;text-align:center}.fig img{max-width:100%;height:auto}
.fig.dark{background:var(--card)}.cap{color:var(--mut);font-size:.9rem;margin:4px 0 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.btn{display:inline-block;padding:6px 12px;border:1px solid var(--line);border-radius:6px;color:var(--acc);text-decoration:none;margin:2px 6px 2px 0;background:var(--card)}
details{margin:10px 0}summary{cursor:pointer;font-weight:600}.sw{display:flex;flex-wrap:wrap;gap:6px 16px;margin:8px 0}
footer{margin-top:60px;color:var(--mut);font-size:.85rem}
@media(max-width:600px){h1{font-size:1.6rem}}
"""


def page():
    t_pots, t_enc, t_sw, t_io, t_rib, t_mcu = ports()
    cb, cc = AUDIT['boards']['control'], AUDIT['boards']['core']
    miss = AUDIT['missing_terminal_count']
    pad = AUDIT['padless_component_count']
    nav = [('overview', 'Overview'), ('power', 'Power'), ('signals', 'Signals'), ('ribbon', 'Ribbon'), ('core-ports', 'Core ports'), ('control-ports', 'Control ports'),
           ('schematics', 'Schematics'), ('renders', '3D &amp; CAD'), ('status', 'Status'), ('files', 'Files')]
    nav_html = ''.join(f'<a href="#{i}">{n}</a>' for i, n in nav)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Compact D R0.5 documentation</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>Compact D R0.5</h1><p class="lead">Two-board sloped digital synthesizer: ESP32-S3 sound engine, 19 pots, 8 encoders, 17 switches.</p>
<div class="banner"><b>Detailed design, not production-ready.</b> {miss} functional terminals still lack matching PCB pads across {pad} padless components
(pots, many module headers, ESP, DAC, headphone amp, main jack). No Gerbers or milling release.</div>
<nav>{nav_html}</nav></header>

<h2 id="overview">1. Overview</h2>
<p>A <b>control board</b> (220&nbsp;×&nbsp;150&nbsp;mm) sits under a 15° aluminium panel and carries every knob, encoder and switch.
A flat <b>core board</b> (210&nbsp;×&nbsp;90&nbsp;mm) carries the ESP32-S3, the DAC and the headphone amplifier. A single soldered
12-wire ribbon joins them. Both boards are intended to be milled from copper-clad plate.</p>
<div class="cards">
<div class="card"><b>Control board</b>19 pots (B10K) · 8 EC11 encoders · 17 slide switches · 3× MCP23017 · 2× CD74HC4067 · power LED</div>
<div class="card"><b>Core board</b>ESP32-S3 N16R8 · PCM5102 DAC · TPA6132 headphone amp · main output jack · filters and pull-ups</div>
<div class="card"><b>Link</b>12-wire ribbon: 3V3, I²C, two pot analog lines, interrupt, and a ground between every signal. No audio or USB on it.</div></div>
<div class="grid2"><figure class="fig"><img src="../../hardware/split-r0.5/previews/assembled-front.png" alt="Assembled front view"><p class="cap">Assembled, front</p></figure>
<figure class="fig"><img src="../../hardware/split-r0.5/previews/exploded.png" alt="Exploded assembly"><p class="cap">Exploded: panel, control PCB, rails, electronics PCB</p></figure></div>

<h2 id="power">2. Power</h2>
<p>Power enters at <b>one point</b>: the USB-C port of the ESP32 module that is wired to the USB-UART chip (core board).</p>
<figure class="fig"><a href="assets/diagram-power.svg"><img src="assets/diagram-power.svg" alt="Power block diagram"></a><p class="cap">Power distribution (click for full size)</p></figure>
<ol><li>USB 5&nbsp;V becomes <code>SYS_5V</code> and feeds the ESP module and the DAC; CC2 (10&nbsp;µF) buffers it.</li>
<li>The ESP module's regulator makes <code>3V3</code> for the headphone amp, CC1, and, through ribbon wire 1, the whole control board.</li>
<li>Ground returns on ribbon wires 2, 4, 6, 8, 10 and 12.</li>
<li>Budget: pots about 6.3&nbsp;mA at 3.3&nbsp;V; control board allowance 50&nbsp;mA (an estimate, not a measurement).</li></ol>
<div class="banner"><b>Open:</b> a bus-powered USB keyboard needs 5&nbsp;V. The module's native port may not supply it, and regulator headroom is unchecked (open points O03, O11).</div>

<h2 id="signals">3. Signal flow</h2>
<figure class="fig"><a href="assets/diagram-signal.svg"><img src="assets/diagram-signal.svg" alt="Signal block diagram"></a><p class="cap">Signal flow (click for full size)</p></figure>
<h3>Controls → ESP</h3>
<ul><li><b>Pots:</b> each sits between 3V3 and GND; the wiper (<code>RVn_W</code>) goes to one mux input. Four select lines <code>MUX_S0..S3</code> (MCP outputs on IO1 and IO2) choose the channel for both muxes. The selected wiper leaves on <code>POT_ADC1</code> or <code>POT_ADC2</code>, crosses the ribbon, passes a 1&nbsp;kΩ/1&nbsp;nF filter and enters GPIO4 or GPIO5.</li>
<li><b>Switches and encoders:</b> each contact pulls an MCP input to GND against the chip's internal pull-up. A change pulls the shared open-drain <code>PANEL_IRQ</code> low (10&nbsp;kΩ pull-up RP5), so the firmware only reads I²C when something moved.</li>
<li><b>I²C:</b> GPIO1/GPIO2 at 100&nbsp;kHz (400&nbsp;kHz after testing). RP3/RP4 pull-ups are DNP.</li></ul>
<h3>Audio</h3>
<ol><li>ESP → DAC over I²S (GPIO15 BCLK, GPIO16 LRCLK, GPIO17 TX); PLL mode, I²S format.</li>
<li>DAC left → <code>MAIN_RAW</code> → RA3 100&nbsp;Ω → rear jack (tip and ring tied, sleeve GND).</li>
<li>DAC right → <code>PHONES_RAW</code> → RA4/RA5 divider → <code>HP_FEED</code> → TPA6132 inputs → the module's own headphone jack.</li>
<li>GPIO41 <code>DAC_MUTE_N</code> drives XSMT; GPIO40 <code>HP_EN</code> drives the amp CTRL. Both have 100&nbsp;kΩ pull-downs.</li></ol>

<h2 id="ribbon">4. Ribbon (JPANEL ↔ JCORE)</h2>
<p>Pin 1 to pin 1; both ends are identical.</p>{t_rib}

<h2 id="core-ports">5. Core board port map</h2>{t_mcu}
<p>Module pin names are functional. Physical header positions are <b>unverified</b>.</p>

<h2 id="control-ports">6. Control board port map</h2>
<h3>I/O expanders (MCP23017 modules)</h3>{t_io}
<p>Contacts use GPA0–GPA6 and GPB0–GPB6. INTA of each chip goes to <code>PANEL_IRQ</code>, INTB is unused, RESET goes to <code>IO_RESET</code>.</p>
<details open><summary>Potentiometers (19) → analog multiplexers</summary>{t_pots}<p>Unused MX2 inputs C3–C15 are grounded. EN is tied low on both muxes.</p></details>
<details><summary>Encoders (8)</summary>{t_enc}</details>
<details><summary>Switches (17)</summary>{t_sw}</details>

<h2 id="schematics">7. Schematics</h2>
<p>Generated from the design data with standard KiCad symbols; the netlist matches the design data. Module pin numbers are placeholders until the headers are measured.</p>
<p><a class="btn" href="assets/schematic-control.svg">Control (SVG)</a><a class="btn" href="../../hardware/split-r0.5/reports/control-schematic.pdf">Control (PDF)</a>
<a class="btn" href="assets/schematic-core.svg">Core (SVG)</a><a class="btn" href="../../hardware/split-r0.5/reports/core-schematic.pdf">Core (PDF)</a></p>
<figure class="fig"><a href="assets/schematic-control.svg"><img src="assets/schematic-control.svg" alt="Control board schematic" loading="lazy"></a><p class="cap">Control board</p></figure>
<figure class="fig"><a href="assets/schematic-core.svg"><img src="assets/schematic-core.svg" alt="Core board schematic" loading="lazy"></a><p class="cap">Core board</p></figure>

<h2 id="renders">8. 3D and CAD</h2>
<div class="grid2"><figure class="fig"><img src="../../hardware/split-r0.5/previews/3d/control-iso.png" alt="Control PCB 3D" loading="lazy"><p class="cap">Control PCB</p></figure>
<figure class="fig"><img src="../../hardware/split-r0.5/previews/3d/core-iso.png" alt="Core PCB 3D" loading="lazy"><p class="cap">Core PCB</p></figure>
<figure class="fig"><img src="../../hardware/split-r0.5/previews/assembled-rear.png" alt="Rear view" loading="lazy"><p class="cap">Rear: jacks and USB</p></figure>
<figure class="fig"><img src="../../hardware/split-r0.5/previews/interior-cable.png" alt="Interior" loading="lazy"><p class="cap">Interior: sloped control board above the flat core board</p></figure></div>
<p>Downloads: <a class="btn" href="../../hardware/split-r0.5/stl/control-board.stl">control-board.stl</a><a class="btn" href="../../hardware/split-r0.5/stl/control-assembly.stl">control-assembly.stl</a>
<a class="btn" href="../../hardware/split-r0.5/stl/core-board.stl">core-board.stl</a><a class="btn" href="../../hardware/split-r0.5/stl/core-assembly.stl">core-assembly.stl</a>
<a class="btn" href="../../mechanical/split-r0.5/split-enclosure-and-boards.step">Full CAD (STEP)</a></p>
<p>Renders use reconstructed component models, not certified vendor CAD.</p>

<h2 id="status">9. Status and open work</h2>
<div class="cards"><div class="card"><b>{cb['terminals_with_matching_pads']} / {cb['required_connected_terminals']}</b>control terminals with pads</div>
<div class="card"><b>{cc['terminals_with_matching_pads']} / {cc['required_connected_terminals']}</b>core terminals with pads</div>
<div class="card"><b>{pad}</b>components without footprints</div></div>
<ul><li><b>Footprints:</b> done for EC11 encoders and the slide switches (4.7&nbsp;mm pitch). The pot footprint is next, using the Alpha RD901F datasheet as a proxy. The ESP, DAC, headphone amp, MCP and mux modules and the main jack still need measurements.</li>
<li><b>Layout:</b> the new switch pads expose conflicts for S4, S10 and S13 (a GND track through pads, mounting-hole overlap). The routed tracks pre-date the real pads.</li>
<li><b>Electrical:</b> keyboard VBUS source, 3.3&nbsp;V regulator headroom, module pull-ups and straps, audio coupling and gain.</li>
<li><b>Milling:</b> process rules (bit size, clearances) and the plated-through-hole substitute are not yet checked against the layout.</li></ul>

<h2 id="files">10. Files</h2>
{table(['What', 'Where'], [
    ('Plan (Markdown, source of this page)', f'<a href="{GH}docs/plan-r0.5.md"><code>docs/plan-r0.5.md</code></a>'),
    ('Architecture and ribbon detail', f'<a href="{GH}hardware/split-r0.5/architecture.md"><code>hardware/split-r0.5/architecture.md</code></a>'),
    ('Unverified items to measure', f'<a href="{GH}hardware/split-r0.5/remaining-verification.md"><code>hardware/split-r0.5/remaining-verification.md</code></a>'),
    ('Decisions (Dutch)', f'<a href="{GH}docs/decisions.md"><code>docs/decisions.md</code></a>'),
    ('KiCad projects', '<code>hardware/split-r0.5/control/</code>, <code>hardware/split-r0.5/core/</code>'),
    ('Reports (audit, DRC, ERC)', '<code>hardware/split-r0.5/reports/</code>'),
    ('Enclosure', f'<a href="{GH}mechanical/split-r0.5/README.md"><code>mechanical/split-r0.5/README.md</code></a>'),
    ('Rebuild this page', '<code>python3 scripts/build_docs_r05.py</code>'),
    ('Rebuild schematics / STLs / switch footprint', '<code>scripts/build_schematics_r05.py</code>, <code>scripts/export_stl_r05.py</code>, <code>scripts/build_switch_footprint_r05.py</code>')])}
<footer>Generated from the repository data. The Markdown plan is the source for the prose and diagrams.</footer>
</div></body></html>
"""


def main():
    mermaid_svgs()
    schematic_svgs()
    (OUT / 'index.html').write_text(page())
    print('wrote', (OUT / 'index.html').relative_to(ROOT), 'with', len(list(ASSETS.iterdir())), 'assets')


if __name__ == '__main__':
    main()
