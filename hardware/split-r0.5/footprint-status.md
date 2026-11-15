# Footprint status (control and core boards)

Order of work agreed for R0.5: **1) footprints verified, 2) placement matched to the CAD, 3) routing.**
Routing is deliberately not started; the old tracks were removed from the control board because they
pre-dated the real pads. `scripts/audit_completion_r05.py` counts terminals without pads.

| Part | Board | Footprint | Status | Basis | Needed to close |
|---|---|---|---|---|---|
| Slide switch (17) | control | `SS12D10_Slide_3P_P4.7` | **measured** | caliper: 10.25 mm edge to edge, 0.7 mm pins → 4.7 mm pitch, ø1.1 hole | body size, lever height, travel, mounting (for panel slot and caps) |
| B10K pot (19) | control | `Pot_B10K_RD901F_Vertical` | **datasheet proxy** | Alpha RD901F drawing: 2.5 mm pitch, pins 6.4 mm from axis, tabs ±5.7 mm | check against the real Youmile part with `reports/fit-template-controls.pdf`; tab line offset |
| EC11 encoder (8) | control | `E1`..`E8` | seller drawing | contacts verified, mount slot variant open | which tab variant was supplied |
| MCP23017 module (3) | control | none | **missing** | 65 × 19 mm body, 2.54 mm pitch known | offset of the dual 7-pin header to the 20-pin header, hole positions |
| CD74HC4067 module (2) | control | none | **missing** | HW-178 | distance and offset between the 8- and 16-pin header rows |
| ESP32-S3 module | core | `ESP32-S3-DevKitC-1_Module` | **vendor drawing** | Espressif v1.1 dimension drawing in `docs/sources/esp32-s3-devkitc-1/`: 25.4 × 62.74 mm, rows 22.86 mm apart, 2.54 pitch, 22 pins/row | confirm the ARCELI clone matches (caliper on row spacing); USB-C outline positions are ±0.5 mm |
| PCM5102 DAC module | core | none | **missing** | | header positions, hole positions, body height |
| TPA6132 module | core | none | **missing** | | header positions, jack position, hole positions |
| Main output jack | core | `SameSky_SJ1-3523N` candidate (not installed) | candidate | datasheet | final part choice and panel/edge fit |
| Ribbon pads, R, C, LED | both | KiCad standard / generated | ok | | none |

Pad numbering: pot pads 1/2/3 = LOW/WIPER/HIGH and switch pads 1/2/3 = ON/COM/OFF, matching the KiCad
symbol pin numbers used by the schematics. The audit maps the design pin names accordingly.

## Verification method

Print `reports/fit-template-controls.pdf` at **100 %** (check the 20 mm scale bar), push the real part's
pins through the drill circles and compare pitch, tab slots and body outline. Record the result here.
