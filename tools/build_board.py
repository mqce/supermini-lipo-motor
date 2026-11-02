# Generates the KiCad schematic, PCB, and JLCPCB assembly files.
import csv
import heapq
import re
import uuid
from pathlib import Path

import pcbnew

ROOT = Path(r"C:\repos\konnect-test\supermini-lipo-motor")
KICAD = Path(r"C:\Program Files\KiCad\10.0\share\kicad")
PROJECT = "supermini-lipo-motor"
ROOT_UUID = "4c1a6e2b-7d44-4a1e-9c31-8b0e5f6a2d10"

BOARD_W = 18.0
BOARD_H = 24.0


def uid():
    return str(uuid.uuid4())


def extract_symbol(path, name):
    text = path.read_text(encoding="utf-8")
    key = f'\t(symbol "{name}"\n'
    i = text.find(key)
    if i < 0:
        raise SystemExit(f"symbol not found: {name}")
    i += 1
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    raise SystemExit(f"unclosed symbol: {name}")


def rename_symbol(body, old_name, new_name):
    return re.sub(r'^\(symbol "[^"]+"', f'(symbol "{new_name}"', body, count=1)


def parse_pins(body):
    pins = []
    for match in re.finditer(
        r'\(pin\s+(\w+)\s+\w+\s+\(at\s+([-\d.]+)\s+([-\d.]+)\s+(\d+).*?\(number\s+"([^"]+)"',
        body,
        re.S,
    ):
        pins.append(
            {
                "type": match.group(1),
                "x": float(match.group(2)),
                "y": float(match.group(3)),
                "angle": int(match.group(4)),
                "number": match.group(5),
            }
        )
    return pins


def fmt(value):
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def rotate(x, y, deg):
    deg %= 360
    if deg == 0:
        return x, y
    if deg == 90:
        return -y, x
    if deg == 180:
        return -x, -y
    if deg == 270:
        return y, -x
    raise ValueError(deg)


VEC = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}


def pin_symbol(number, name, etype, x, y, angle, length=2.54):
    return f"""\t\t\t(pin {etype} line
\t\t\t\t(at {fmt(x)} {fmt(y)} {angle})
\t\t\t\t(length {fmt(length)})
\t\t\t\t(name "{name}"
\t\t\t\t\t(effects
\t\t\t\t\t\t(font
\t\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t\t)
\t\t\t\t\t)
\t\t\t\t)
\t\t\t\t(number "{number}"
\t\t\t\t\t(effects
\t\t\t\t\t\t(font
\t\t\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t\t\t)
\t\t\t\t\t)
\t\t\t\t)
\t\t\t)"""


def boxed_symbol(lib_name, ref, value, footprint, pins, description, in_bom=True):
    xs = [p[3] for p in pins]
    ys = [p[4] for p in pins]
    left = min(xs) + 2.54
    right = max(xs) - 2.54
    top = max(ys) + 1.27
    bottom = min(ys) - 1.27
    pin_text = "\n".join(pin_symbol(*p) for p in pins)
    bom = "yes" if in_bom else "no"
    short = lib_name.split(":")[-1]
    return f"""\t(symbol "{lib_name}"
\t\t(pin_numbers (hide yes))
\t\t(pin_names (offset 0.254))
\t\t(exclude_from_sim no)
\t\t(in_bom {bom})
\t\t(on_board yes)
\t\t(in_pos_files {bom})
\t\t(duplicate_pin_numbers_are_jumpers no)
\t\t(property "Reference" "{ref}"
\t\t\t(at 0 {fmt(top + 1.27)} 0)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Value" "{value}"
\t\t\t(at 0 {fmt(bottom - 1.27)} 0)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Footprint" "{footprint}"
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Datasheet" ""
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(property "Description" "{description}"
\t\t\t(at 0 0 0)
\t\t\t(hide yes)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects (font (size 1.27 1.27)))
\t\t)
\t\t(symbol "{short}_0_1"
\t\t\t(rectangle (start {fmt(left)} {fmt(bottom)}) (end {fmt(right)} {fmt(top)})
\t\t\t\t(stroke (width 0.254) (type default))
\t\t\t\t(fill (type background))
\t\t\t)
\t\t)
\t\t(symbol "{short}_1_1"
{pin_text}
\t\t)
\t\t(embedded_fonts no)
\t)"""


def right_pins(items, x=7.62, y0=8.89):
    pins = []
    for index, (number, name, etype) in enumerate(items):
        pins.append((number, name, etype, x, y0 - index * 2.54, 0))
    return pins


def build_custom_symbols():
    esp_l = boxed_symbol(
        "supermini:ESP_L",
        "J",
        "ESP_L",
        "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
        right_pins(
            [
                ("1", "5V", "passive"),
                ("2", "GND", "passive"),
                ("3", "3V3", "passive"),
                ("4", "GPIO4", "output"),
                ("5", "GPIO3", "output"),
                ("6", "GPIO2", "passive"),
                ("7", "GPIO1", "passive"),
                ("8", "GPIO0", "passive"),
            ]
        ),
        "5V column. Component side with USB up: left side, USB edge toward the antenna",
        in_bom=False,
    )
    esp_r = boxed_symbol(
        "supermini:ESP_R",
        "J",
        "ESP_R",
        "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
        right_pins(
            [
                ("1", "GPIO5", "passive"),
                ("2", "GPIO6", "passive"),
                ("3", "GPIO7", "output"),
                ("4", "GPIO8", "passive"),
                ("5", "GPIO9", "passive"),
                ("6", "GPIO10", "output"),
                ("7", "GPIO20", "passive"),
                ("8", "GPIO21", "passive"),
            ]
        ),
        "GPIO5 column. Component side with USB up: right side, USB edge toward the antenna",
        in_bom=False,
    )
    wires = boxed_symbol(
        "supermini:WIRES",
        "J",
        "WIRES",
        "WirePads:WirePads_1x08_P1.50mm",
        right_pins(
            [
                ("1", "BAT+", "passive"),
                ("2", "BAT-", "passive"),
                ("3", "SW_BAT", "passive"),
                ("4", "SW_LOAD", "passive"),
                ("5", "M1+", "passive"),
                ("6", "M1-", "passive"),
                ("7", "M2+", "passive"),
                ("8", "M2-", "passive"),
            ]
        ),
        "Hand-solder pads, 1.5 mm pitch, left to right",
        in_bom=False,
    )
    tc = boxed_symbol(
        "supermini:TC118S",
        "U",
        "TC118S",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        [
            ("1", "NC", "no_connect", -10.16, 7.62, 180),
            ("2", "INA", "input", -10.16, 5.08, 180),
            ("3", "INB", "input", -10.16, 2.54, 180),
            ("4", "VDD", "power_in", -10.16, 0, 180),
            ("8", "OUTA", "output", 10.16, 5.08, 0),
            ("5", "OUTB", "output", 10.16, 2.54, 0),
            ("6", "GND", "power_in", 10.16, 0, 0),
            ("7", "GND", "power_in", 10.16, -2.54, 0),
        ],
        "Fuman TC118S single H-bridge, LCSC C88308",
    )
    tp = boxed_symbol(
        "supermini:TP4056",
        "U",
        "TP4056",
        "Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm",
        [
            ("1", "TEMP", "input", -10.16, 7.62, 180),
            ("2", "PROG", "passive", -10.16, 5.08, 180),
            ("3", "GND", "power_in", -10.16, 2.54, 180),
            ("4", "VCC", "power_in", -10.16, 0, 180),
            ("8", "CE", "input", 10.16, 7.62, 0),
            ("7", "CHRG", "open_collector", 10.16, 5.08, 0),
            ("6", "STDBY", "open_collector", 10.16, 2.54, 0),
            ("5", "BAT", "passive", 10.16, 0, 0),
            ("9", "EP", "power_in", 0, -7.62, 270),
        ],
        "TP4056 linear charger, LCSC C382139. CE tied to VCC. TEMP tied to GND.",
    )
    return "\n".join([esp_l, esp_r, wires, tc, tp])


def load_library_symbols():
    pairs = [
        (KICAD / "symbols" / "Device.kicad_sym", "R", "Device:R"),
        (KICAD / "symbols" / "Device.kicad_sym", "C", "Device:C"),
        (KICAD / "symbols" / "Device.kicad_sym", "LED", "Device:LED"),
        (KICAD / "symbols" / "Device.kicad_sym", "D_Schottky", "Device:D_Schottky"),
        (KICAD / "symbols" / "power.kicad_sym", "GND", "power:GND"),
        (KICAD / "symbols" / "power.kicad_sym", "PWR_FLAG", "power:PWR_FLAG"),
    ]
    bodies = []
    pins = {}
    for path, name, lib_name in pairs:
        body = rename_symbol(extract_symbol(path, name), name, lib_name)
        bodies.append("\t" + body.replace("\n", "\n\t"))
        pins[lib_name] = parse_pins(body)
    return "\n".join(bodies), pins


def effects(hidden=False, size=1.27):
    hide = " (hide yes)" if hidden else ""
    return f"(effects (font (size {size} {size})){hide})"


def property_block(name, value, x, y, hidden=False):
    hide = "\t\t\t(hide yes)\n" if hidden else ""
    return (
        f'\t\t(property "{name}" "{value}"\n'
        f"\t\t\t(at {fmt(x)} {fmt(y)} 0)\n"
        f"{hide}"
        "\t\t\t(show_name no)\n"
        "\t\t\t(do_not_autoplace no)\n"
        "\t\t\t(effects (font (size 1.27 1.27)))\n"
        "\t\t)"
    )


class Schematic:
    def __init__(self, pin_defs):
        self.pin_defs = pin_defs
        self.symbols = []
        self.wires = []
        self.labels = []
        self.noconnects = []
        self.texts = []

    def add_symbol(self, lib_id, ref, value, footprint, x, y, rot=0, bom=True, pos=True, extra=None):
        sym_uuid = uid()
        pin_lines = []
        world = {}
        for pin in self.pin_defs[lib_id]:
            px, py = rotate(pin["x"], pin["y"], rot)
            wx, wy = x + px, y + py
            ang = (pin["angle"] + rot) % 360
            world[pin["number"]] = (wx, wy, ang)
            pin_lines.append(f'\t\t(pin "{pin["number"]}" (uuid "{uid()}"))')
        props = [
            property_block("Reference", ref, x, y + 5.08, hidden=ref.startswith("#")),
            property_block("Value", value, x, y - 5.08),
            property_block("Footprint", footprint, x, y, hidden=True),
            property_block("Datasheet", "", x, y, hidden=True),
        ]
        for key, val in (extra or {}).items():
            props.append(property_block(key, val, x, y, hidden=True))
        bom_s = "yes" if bom else "no"
        pos_s = "yes" if pos else "no"
        block = "\n".join(
            [
                "\t(symbol",
                f'\t\t(lib_id "{lib_id}")',
                f"\t\t(at {fmt(x)} {fmt(y)} {rot})",
                "\t\t(unit 1)",
                "\t\t(body_style 1)",
                "\t\t(exclude_from_sim no)",
                f"\t\t(in_bom {bom_s})",
                f"\t\t(on_board {pos_s})",
                f"\t\t(in_pos_files {pos_s})",
                "\t\t(dnp no)",
                f'\t\t(uuid "{sym_uuid}")',
                *props,
                *pin_lines,
                "\t\t(instances",
                f'\t\t\t(project "{PROJECT}"',
                f'\t\t\t\t(path "/{ROOT_UUID}"',
                f'\t\t\t\t\t(reference "{ref}")',
                "\t\t\t\t\t(unit 1)",
                "\t\t\t\t)",
                "\t\t\t)",
                "\t\t)",
                "\t)",
            ]
        )
        self.symbols.append(block)
        return world

    def wire(self, x1, y1, x2, y2):
        if (x1, y1) == (x2, y2):
            return
        self.wires.append(
            "\t(wire\n"
            f"\t\t(pts (xy {fmt(x1)} {fmt(y1)}) (xy {fmt(x2)} {fmt(y2)}))\n"
            "\t\t(stroke (width 0) (type solid))\n"
            f'\t\t(uuid "{uid()}")\n'
            "\t)"
        )

    def label(self, name, x, y, angle=0):
        self.labels.append(
            f'\t(label "{name}"\n'
            f"\t\t(at {fmt(x)} {fmt(y)} {angle})\n"
            f"\t\t{effects()}\n"
            f'\t\t(uuid "{uid()}")\n'
            "\t)"
        )

    def nc(self, x, y):
        self.noconnects.append(f'\t(no_connect (at {fmt(x)} {fmt(y)}) (uuid "{uid()}"))')

    def connect(self, world, number, net):
        x, y, ang = world[number]
        if net == "NC":
            self.nc(x, y)
            return
        dx, dy = VEC[ang]
        x2, y2 = x + dx * 2.54, y + dy * 2.54
        self.wire(x, y, x2, y2)
        self.label(net, x2, y2, ang)

    def text(self, value, x, y):
        self.texts.append(
            "\t(text \"" + value + "\"\n"
            "\t\t(exclude_from_sim no)\n"
            f"\t\t(at {fmt(x)} {fmt(y)} 0)\n"
            "\t\t(effects (font (size 1.27 1.27)))\n"
            f'\t\t(uuid "{uid()}")\n'
            "\t)"
        )


def write_schematic(pin_defs, custom_symbols, lib_symbols):
    for name, pins in (
        ("supermini:ESP_L", None),
        ("supermini:ESP_R", None),
        ("supermini:WIRES", None),
        ("supermini:TC118S", None),
        ("supermini:TP4056", None),
    ):
        pass
    pin_defs = dict(pin_defs)
    # Custom symbol pin locations match boxed_symbol / right_pins.
    pin_defs["supermini:ESP_L"] = [
        {"number": str(i), "x": 7.62, "y": 8.89 - (i - 1) * 2.54, "angle": 0} for i in range(1, 9)
    ]
    pin_defs["supermini:ESP_R"] = pin_defs["supermini:ESP_L"]
    pin_defs["supermini:WIRES"] = pin_defs["supermini:ESP_L"]
    pin_defs["supermini:TC118S"] = [
        {"number": "1", "x": -10.16, "y": -7.62, "angle": 180},
        {"number": "2", "x": -10.16, "y": -5.08, "angle": 180},
        {"number": "3", "x": -10.16, "y": -2.54, "angle": 180},
        {"number": "4", "x": -10.16, "y": 0, "angle": 180},
        {"number": "8", "x": 10.16, "y": -5.08, "angle": 0},
        {"number": "5", "x": 10.16, "y": -2.54, "angle": 0},
        {"number": "6", "x": 10.16, "y": 0, "angle": 0},
        {"number": "7", "x": 10.16, "y": 2.54, "angle": 0},
    ]
    pin_defs["supermini:TP4056"] = [
        {"number": "1", "x": -10.16, "y": -7.62, "angle": 180},
        {"number": "2", "x": -10.16, "y": -5.08, "angle": 180},
        {"number": "3", "x": -10.16, "y": -2.54, "angle": 180},
        {"number": "4", "x": -10.16, "y": 0, "angle": 180},
        {"number": "8", "x": 10.16, "y": -7.62, "angle": 0},
        {"number": "7", "x": 10.16, "y": -5.08, "angle": 0},
        {"number": "6", "x": 10.16, "y": -2.54, "angle": 0},
        {"number": "5", "x": 10.16, "y": 0, "angle": 0},
        {"number": "9", "x": 0, "y": 7.62, "angle": 270},
    ]

    sch = Schematic(pin_defs)
    header_fp = "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical"
    j1 = sch.add_symbol("supermini:ESP_L", "J1", "ESP_L", header_fp, 40.64, 203.2, bom=False, pos=False)
    j2 = sch.add_symbol("supermini:ESP_R", "J2", "ESP_R", header_fp, 40.64, 127.0, bom=False, pos=False)
    j3 = sch.add_symbol(
        "supermini:WIRES",
        "J3",
        "WIRES",
        "WirePads:WirePads_1x08_P1.50mm",
        40.64,
        50.8,
        bom=False,
        pos=False,
    )
    u1 = sch.add_symbol(
        "supermini:TC118S",
        "U1",
        "TC118S",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        165.1,
        203.2,
        extra={"LCSC": "C88308"},
    )
    u2 = sch.add_symbol(
        "supermini:TC118S",
        "U2",
        "TC118S",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        165.1,
        114.3,
        extra={"LCSC": "C88308"},
    )
    u3 = sch.add_symbol(
        "supermini:TP4056",
        "U3",
        "TP4056",
        "Package_SO:SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm",
        292.1,
        203.2,
        extra={"LCSC": "C382139"},
    )
    r_fp = "Resistor_SMD:R_0402_1005Metric"
    r0603 = "Resistor_SMD:R_0603_1608Metric"
    c0603 = "Capacitor_SMD:C_0603_1608Metric"
    c0402 = "Capacitor_SMD:C_0402_1005Metric"
    c0805 = "Capacitor_SMD:C_0805_2012Metric"

    def two_pin(lib_id, ref, value, footprint, x, y, lcsc, net1, net2):
        world = sch.add_symbol(lib_id, ref, value, footprint, x, y, extra={"LCSC": lcsc})
        sch.connect(world, "1", net1)
        sch.connect(world, "2", net2)

    two_pin("Device:R", "R1", "10k", r0603, 241.3, 165.1, "C25804", "PROG", "GND")
    two_pin("Device:R", "R2", "1k", r_fp, 355.6, 165.1, "C11702", "V5", "LED_A")
    two_pin("Device:R", "R3", "100", r_fp, 114.3, 215.9, "C25076", "GPIO4", "M1_INA")
    two_pin("Device:R", "R4", "100", r_fp, 114.3, 190.5, "C25076", "GPIO3", "M1_INB")
    two_pin("Device:R", "R5", "100", r_fp, 114.3, 139.7, "C25076", "GPIO10", "M2_INA")
    two_pin("Device:R", "R6", "100", r_fp, 114.3, 114.3, "C25076", "GPIO7", "M2_INB")
    two_pin("Device:C", "C1", "10uF", c0603, 355.6, 215.9, "C19702", "V5", "GND")
    two_pin("Device:C", "C2", "10uF", c0603, 355.6, 190.5, "C19702", "VBAT", "GND")
    two_pin("Device:C", "C3", "10uF", c0603, 215.9, 228.6, "C19702", "VSW", "GND")
    two_pin("Device:C", "C4", "100nF", c0402, 215.9, 203.2, "C1525", "VSW", "GND")
    two_pin("Device:C", "C5", "10uF", c0603, 215.9, 139.7, "C19702", "VSW", "GND")
    two_pin("Device:C", "C6", "100nF", c0402, 215.9, 114.3, "C1525", "VSW", "GND")
    two_pin("Device:C", "C7", "100nF", c0402, 215.9, 177.8, "C1525", "M1+", "M1-")
    two_pin("Device:C", "C8", "100nF", c0402, 215.9, 88.9, "C1525", "M2+", "M2-")
    two_pin("Device:C", "C9", "22uF", c0805, 215.9, 63.5, "C45783", "VSW", "GND")

    d1 = sch.add_symbol(
        "Device:D_Schottky",
        "D1",
        "B5819W",
        "Diode_SMD:D_SOD-123",
        292.1,
        127.0,
        extra={"LCSC": "C8598"},
    )
    sch.connect(d1, "1", "V5")
    sch.connect(d1, "2", "VSW")
    led = sch.add_symbol(
        "Device:LED",
        "LED1",
        "RED",
        "LED_SMD:LED_0603_1608Metric",
        368.3,
        139.7,
        extra={"LCSC": "C2286"},
    )
    sch.connect(led, "1", "CHRG")
    sch.connect(led, "2", "LED_A")

    for number, net in {
        "1": "V5",
        "2": "GND",
        "3": "NC",
        "4": "GPIO4",
        "5": "GPIO3",
        "6": "NC",
        "7": "NC",
        "8": "NC",
    }.items():
        sch.connect(j1, number, net)
    for number, net in {
        "1": "NC",
        "2": "NC",
        "3": "GPIO7",
        "4": "NC",
        "5": "NC",
        "6": "GPIO10",
        "7": "NC",
        "8": "NC",
    }.items():
        sch.connect(j2, number, net)
    for number, net in {
        "1": "VBAT",
        "2": "GND",
        "3": "VBAT",
        "4": "VSW",
        "5": "M1+",
        "6": "M1-",
        "7": "M2+",
        "8": "M2-",
    }.items():
        sch.connect(j3, number, net)
    for world, mapping in (
        (
            u1,
            {
                "1": "NC",
                "2": "M1_INA",
                "3": "M1_INB",
                "4": "VSW",
                "5": "M1-",
                "6": "GND",
                "7": "GND",
                "8": "M1+",
            },
        ),
        (
            u2,
            {
                "1": "NC",
                "2": "M2_INA",
                "3": "M2_INB",
                "4": "VSW",
                "5": "M2-",
                "6": "GND",
                "7": "GND",
                "8": "M2+",
            },
        ),
        (
            u3,
            {
                "1": "GND",
                "2": "PROG",
                "3": "GND",
                "4": "V5",
                "5": "VBAT",
                "6": "NC",
                "7": "CHRG",
                "8": "V5",
                "9": "GND",
            },
        ),
    ):
        for number, net in mapping.items():
            sch.connect(world, number, net)

    # One power-output flag on each supply net. KiCad 10 GND symbols are power inputs.
    for index, (net, x, y) in enumerate(
        (("GND", 393.7, 40.64), ("V5", 393.7, 60.96), ("VBAT", 393.7, 81.28), ("VSW", 393.7, 101.6)),
        start=1,
    ):
        flag = sch.add_symbol("power:PWR_FLAG", f"#FLG0{index}", "PWR_FLAG", "", x, y, bom=False, pos=False)
        sch.connect(flag, "1", net)

    sch.text("USB side of the stacked boards is the +Y edge.", 25.4, 215.9)
    sch.text("M1 INA=GPIO4 INB=GPIO3. M2 INA=GPIO10 INB=GPIO7.", 25.4, 210.82)
    sch.text("Do not drive GPIO2, GPIO8 or GPIO9.", 25.4, 205.74)

    content = "\n".join(
        [
            "(kicad_sch",
            "\t(version 20260101)",
            '\t(generator "eeschema")',
            '\t(generator_version "10.0")',
            f'\t(uuid "{ROOT_UUID}")',
            '\t(paper "A3")',
            "\t(title_block",
            '\t\t(title "ESP32-C3 SuperMini 2-motor expander")',
            '\t\t(date "2026-11-01")',
            "\t\t(rev \"1\")",
            "\t)",
            "\t(lib_symbols",
            lib_symbols,
            custom_symbols,
            "\t)",
            *sch.symbols,
            *sch.wires,
            *sch.labels,
            *sch.noconnects,
            *sch.texts,
            "\t(sheet_instances",
            '\t\t(path "/" (page "1"))',
            "\t)",
            ")",
            "",
        ]
    )
    (ROOT / f"{PROJECT}.kicad_sch").write_text(content, encoding="utf-8")
    symbols = ROOT / "symbols"
    symbols.mkdir(exist_ok=True)
    library = "\n".join(
        [
            "(kicad_symbol_lib",
            "\t(version 20251024)",
            '\t(generator "kicad_symbol_editor")',
            '\t(generator_version "10.0")',
            custom_symbols.replace("supermini:", ""),
            ")",
            "",
        ]
    )
    (symbols / "supermini.kicad_sym").write_text(library, encoding="utf-8")


def mm(x, y=None):
    if y is None:
        return pcbnew.FromMM(x)
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def load_fp(lib, name, count=1):
    pretty = KICAD / "footprints" / lib
    loaded = pcbnew.FootprintLoad(str(pretty), name)
    copies = []
    for _ in range(count):
        copies.append(pcbnew.Cast_to_FOOTPRINT(loaded.Duplicate(False)))
    return copies[0] if count == 1 else copies


def strip_marks(fp):
    ref = fp.Reference()
    ref.SetLayer(pcbnew.F_Fab)
    ref.SetVisible(False)
    val = fp.Value()
    val.SetLayer(pcbnew.F_Fab)
    val.SetVisible(False)
    for item in list(fp.GraphicalItems()):
        if item.GetClass() == "PCB_FIELD":
            continue
        if item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS, pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            fp.Remove(item)


def place(board, fp, ref, value, x, y, rot, exclude):
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(mm(x, y))
    fp.SetOrientation(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    if exclude and hasattr(fp, "SetExcludedFromPosFiles"):
        fp.SetExcludedFromPosFiles(True)
        fp.SetExcludedFromBOM(True)
    board.Add(fp)
    return fp


def make_wire_fp():
    fp = pcbnew.FOOTPRINT(None)
    fp.SetReference("REF**")
    fp.SetValue("WirePads_1x08_P1.50mm")
    for index in range(8):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(index + 1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(mm(1.2, 1.2))
        pad.SetDrillSize(mm(0.7, 0.7))
        pad.SetPosition(mm(index * 1.5, 0))
        pad.SetLayerSet(pad.PTHMask())
        fp.Add(pad)
    return fp


def add_net(board, nets, name):
    if name in nets:
        return nets[name]
    item = pcbnew.NETINFO_ITEM(board, name)
    board.Add(item)
    nets[name] = item
    return item


def set_pad_net(fp, number, net):
    for pad in fp.Pads():
        if pad.GetNumber() == str(number):
            pad.SetNet(net)


def pad_xy(fp, number):
    for pad in fp.Pads():
        if pad.GetNumber() == str(number):
            pos = pad.GetPosition()
            return pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
    raise KeyError(number)


def add_track(board, net, layer, width, x1, y1, x2, y2):
    if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
        return
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(mm(x1, y1))
    track.SetEnd(mm(x2, y2))
    track.SetWidth(mm(width))
    track.SetLayer(layer)
    track.SetNet(net)
    board.Add(track)


def route(board, net, layer, width, points):
    for start, end in zip(points, points[1:]):
        add_track(board, net, layer, width, start[0], start[1], end[0], end[1])


def add_via(board, net, x, y, drill=0.3, size=0.6):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(mm(x, y))
    via.SetDrill(mm(drill))
    via.SetWidth(mm(size))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net)
    board.Add(via)


def add_line(board, x1, y1, x2, y2, layer):
    shape = pcbnew.PCB_SHAPE(board)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(mm(x1, y1))
    shape.SetEnd(mm(x2, y2))
    shape.SetLayer(layer)
    shape.SetWidth(mm(0.05))
    board.Add(shape)


def add_text(board, text, x, y):
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(mm(x, y))
    item.SetLayer(pcbnew.F_SilkS)
    item.SetTextSize(mm(0.9, 0.9))
    item.SetTextThickness(mm(0.15))
    item.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    item.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    board.Add(item)


def stitch_ground(board):
    gnd = N("GND")
    for x, y, size in (
        (2.50, 21.45, 0.55),
        (4.67, 5.50, 0.55),
        (11.20, 7.18, 0.50),
        (11.20, 5.92, 0.50),
        (14.60, 18.60, 0.55),
        (15.30, 21.00, 0.55),
        (16.00, 6.18, 0.50),
        (12.97, 7.15, 0.50),
    ):
        add_via(board, gnd, x, y, drill=0.3, size=size)
    for layer, width, x1, y1, x2, y2 in (
        (pcbnew.B_Cu, 0.2, 14.60, 18.60, 14.70, 20.80),
        (pcbnew.B_Cu, 0.2, 14.70, 20.80, 15.30, 20.80),
        (pcbnew.B_Cu, 0.2, 15.30, 20.80, 15.30, 21.00),
        (pcbnew.F_Cu, 0.16, 14.05, 4.35, 14.40, 4.50),
        (pcbnew.F_Cu, 0.16, 14.40, 4.50, 14.40, 5.00),
        (pcbnew.F_Cu, 0.16, 14.40, 5.00, 15.50, 5.00),
        (pcbnew.F_Cu, 0.16, 15.50, 5.00, 15.50, 6.18),
        (pcbnew.F_Cu, 0.16, 15.50, 6.18, 16.00, 6.18),
        (pcbnew.B_Cu, 0.2, 16.00, 6.18, 12.97, 7.15),
        (pcbnew.F_Cu, 0.2, 12.97, 7.15, 12.20, 7.15),
    ):
        add_track(board, gnd, layer, width, x1, y1, x2, y2)


def add_zone(board, net, layer, points):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(net)
    zone.SetAssignedPriority(0)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetThermalReliefGap(mm(0.2))
    zone.SetThermalReliefSpokeWidth(mm(0.4))
    zone.SetMinThickness(mm(0.2))
    zone.SetLocalClearance(mm(0.16))
    zone.SetIsFilled(False)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in points:
        outline.Append(mm(x), mm(y))
    board.Add(zone)
    return zone


def ortho(a, b):
    if abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6:
        return [a, b]
    return [a, (b[0], a[1]), b]


def clean_saved_board(path):
    board = pcbnew.LoadBoard(path)
    for fp in board.GetFootprints():
        ref = fp.Reference()
        ref.SetLayer(pcbnew.F_Fab)
        ref.SetVisible(False)
        val = fp.Value()
        val.SetLayer(pcbnew.F_Fab)
        val.SetVisible(False)
        for item in list(fp.GraphicalItems()):
            if item.GetClass() == "PCB_FIELD":
                continue
            if item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS, pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                fp.Remove(item)
    board.Save(path)


def _rect_gap(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(ax0 - bx1, bx0 - ax1)
    dy = max(ay0 - by1, by0 - ay1)
    if dx > 0 and dy > 0:
        return (dx * dx + dy * dy) ** 0.5
    return max(dx, dy)


def _point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def _dist_to_segment(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    length = dx * dx + dy * dy
    if length <= 1e-12:
        return ((px - x0) ** 2 + (py - y0) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length))
    qx, qy = x0 + t * dx, y0 + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def _board_poly():
    return [
        (0, 0),
        (5, 0),
        (5, 4),
        (13, 4),
        (13, 0),
        (18, 0),
        (18, BOARD_H),
        (0, BOARD_H),
    ]


def _on_board(x, y, margin):
    poly = _board_poly()
    if not _point_in_poly(x, y, poly):
        return False
    pts = poly + [poly[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if _dist_to_segment(x, y, x0, y0, x1, y1) < margin:
            return False
    return True


def _pad_box(pad):
    box = pad.GetBoundingBox()
    left = pcbnew.ToMM(box.GetLeft())
    right = pcbnew.ToMM(box.GetRight())
    bottom = pcbnew.ToMM(box.GetBottom())
    top = pcbnew.ToMM(box.GetTop())
    return (min(left, right), min(bottom, top), max(left, right), max(bottom, top))


def _pad_layers(pad):
    layers = []
    if pad.IsOnLayer(pcbnew.F_Cu):
        layers.append(0)
    if pad.IsOnLayer(pcbnew.B_Cu):
        layers.append(1)
    return tuple(layers)


def report_pad_conflicts(board):
    pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if not _pad_layers(pad):
                continue
            pads.append((fp.GetReference(), pad.GetNumber(), pad.GetNetname(), _pad_box(pad)))
    conflicts = []
    for i, a in enumerate(pads):
        for b in pads[i + 1 :]:
            gap = _rect_gap(a[3], b[3])
            if gap < 0.16 and a[2] != b[2]:
                conflicts.append((gap, a[0], a[1], a[2], b[0], b[1], b[2]))
    conflicts.sort(key=lambda item: item[0])
    for gap, ra, na, neta, rb, nb, netb in conflicts[:30]:
        print(f"pad gap {gap:.3f} {ra}.{na}/{neta} vs {rb}.{nb}/{netb}")
    if conflicts:
        raise SystemExit(f"{len(conflicts)} pad clearance conflicts")


def autoroute(board, only=None):
    cell = 0.1
    clearance = 0.16
    via_size = 0.55
    via_drill = 0.3
    via_r = via_size / 2
    layers = (pcbnew.F_Cu, pcbnew.B_Cu)
    poly = _board_poly()

    pads = []
    for fp in board.GetFootprints():
        if not hasattr(fp, "Pads"):
            fp = pcbnew.Cast_to_FOOTPRINT(fp)
        for pad in fp.Pads():
            if not _pad_layers(pad):
                continue
            pads.append(
                {
                    "net": pad.GetNetname(),
                    "box": _pad_box(pad),
                    "layers": _pad_layers(pad),
                    "x": pcbnew.ToMM(pad.GetPosition().x),
                    "y": pcbnew.ToMM(pad.GetPosition().y),
                    "ref": fp.GetReference(),
                    "num": pad.GetNumber(),
                }
            )

    obstacles = []
    for pad in pads:
        for layer in pad["layers"]:
            obstacles.append((pad["net"], layer, pad["box"]))
    for track in board.GetTracks():
        if track.GetClass() == "PCB_VIA":
            radius = pcbnew.ToMM(track.GetWidth(pcbnew.F_Cu)) / 2
            x = pcbnew.ToMM(track.GetPosition().x)
            y = pcbnew.ToMM(track.GetPosition().y)
            box = (x - radius, y - radius, x + radius, y + radius)
            obstacles.append((track.GetNetname(), 0, box))
            obstacles.append((track.GetNetname(), 1, box))
        else:
            half = pcbnew.ToMM(track.GetWidth()) / 2
            x0 = pcbnew.ToMM(track.GetStart().x)
            y0 = pcbnew.ToMM(track.GetStart().y)
            x1 = pcbnew.ToMM(track.GetEnd().x)
            y1 = pcbnew.ToMM(track.GetEnd().y)
            layer = 0 if track.GetLayer() == pcbnew.F_Cu else 1
            obstacles.append(
                (
                    track.GetNetname(),
                    layer,
                    (min(x0, x1) - half, min(y0, y1) - half, max(x0, x1) + half, max(y0, y1) + half),
                )
            )

    def cell_of(x, y):
        return int(round(x / cell)), int(round(y / cell))

    def mm_of(ix, iy):
        return ix * cell, iy * cell

    def blocked_set(net, width):
        margin = clearance + width / 2
        blocked = set()
        ix_max = int(BOARD_W / cell) + 2
        iy_max = int(BOARD_H / cell) + 2
        for owner, layer, (x0, y0, x1, y1) in obstacles:
            if owner == net:
                continue
            ex0, ey0, ex1, ey1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
            for ix in range(max(0, int(ex0 / cell)), min(ix_max, int(ex1 / cell) + 1)):
                cx = ix * cell
                if cx < ex0 or cx > ex1:
                    continue
                for iy in range(max(0, int(ey0 / cell)), min(iy_max, int(ey1 / cell) + 1)):
                    cy = iy * cell
                    if ey0 <= cy <= ey1:
                        blocked.add((ix, iy, layer))
        return blocked

    def own_cells(pad):
        cells = set()
        x0, y0, x1, y1 = pad["box"]
        cx, cy = pad["x"], pad["y"]
        wide_x = x1 - x0
        wide_y = y1 - y0
        circular = abs(wide_x - wide_y) < 0.05
        radius = min(wide_x, wide_y) / 2
        for layer in pad["layers"]:
            for ix in range(int(x0 / cell), int(x1 / cell) + 1):
                for iy in range(int(y0 / cell), int(y1 / cell) + 1):
                    x, y = mm_of(ix, iy)
                    if circular:
                        if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                            cells.add((ix, iy, layer))
                    elif x0 <= x <= x1 and y0 <= y <= y1:
                        cells.add((ix, iy, layer))
        return cells

    def on_edge(ix, iy, margin):
        x, y = mm_of(ix, iy)
        return _on_board(x, y, margin)

    def foreign_hit_circle(net, x, y, radius):
        for owner, _layer, (x0, y0, x1, y1) in obstacles:
            if owner == net:
                continue
            cx = min(max(x, x0), x1)
            cy = min(max(y, y0), y1)
            if (x - cx) ** 2 + (y - cy) ** 2 < radius * radius:
                return True
        return False

    def add_segment_obstacle(net, layer, x0, y0, x1, y1, width):
        half = width / 2
        obstacles.append((net, layer, (min(x0, x1) - half, min(y0, y1) - half, max(x0, x1) + half, max(y0, y1) + half)))

    def add_via_obstacle(net, x, y):
        box = (x - via_r, y - via_r, x + via_r, y + via_r)
        obstacles.append((net, 0, box))
        obstacles.append((net, 1, box))

    def search(net, width, sources, goals):
        blocked = blocked_set(net, width)
        margin = width / 2 + 0.2
        via_margin = via_r + 0.2
        heap = []
        best = {}
        came = {}
        tie = 0
        for state in sources:
            heapq.heappush(heap, (0, tie, state))
            best[state] = 0
            came[state] = None
            tie += 1
        while heap:
            cost, _, state = heapq.heappop(heap)
            if cost != best.get(state):
                continue
            if state in goals:
                path = []
                cursor = state
                while cursor is not None:
                    path.append(cursor)
                    cursor = came[cursor]
                path.reverse()
                return path
            ix, iy, layer = state
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (ix + dx, iy + dy, layer)
                if nxt in blocked and nxt not in goals:
                    continue
                if not on_edge(nxt[0], nxt[1], margin) and nxt not in goals and nxt not in sources:
                    continue
                new_cost = cost + 1
                if new_cost < best.get(nxt, 1e18):
                    best[nxt] = new_cost
                    came[nxt] = state
                    heapq.heappush(heap, (new_cost, tie, nxt))
                    tie += 1
            other = (ix, iy, 1 - layer)
            if other in blocked and other not in goals:
                continue
            x, y = mm_of(ix, iy)
            if not on_edge(ix, iy, via_margin):
                continue
            if foreign_hit_circle(net, x, y, via_r + clearance):
                continue
            new_cost = cost + 7
            if new_cost < best.get(other, 1e18):
                best[other] = new_cost
                came[other] = state
                heapq.heappush(heap, (new_cost, tie, other))
                tie += 1
        return None

    def emit(net_name, width, path):
        net = board.FindNet(net_name)
        points = []
        for ix, iy, layer in path:
            x, y = mm_of(ix, iy)
            points.append((x, y, layer))
        simplified = [points[0]]
        for point in points[1:]:
            prev = simplified[-1]
            if len(simplified) >= 2 and prev[2] == point[2] == simplified[-2][2]:
                a, b = simplified[-2], prev
                if (a[0] == b[0] == point[0]) or (a[1] == b[1] == point[1]):
                    simplified[-1] = point
                    continue
            simplified.append(point)
        layer_id = {0: pcbnew.F_Cu, 1: pcbnew.B_Cu}
        for start, end in zip(simplified, simplified[1:]):
            if start[2] != end[2]:
                add_via(board, net, start[0], start[1], drill=via_drill, size=via_size)
                add_via_obstacle(net_name, start[0], start[1])
                continue
            add_track(board, net, layer_id[start[2]], width, start[0], start[1], end[0], end[1])
            add_segment_obstacle(net_name, start[2], start[0], start[1], end[0], end[1], width)

    wide = {"VBAT", "VSW", "V5", "M1+", "M1-", "M2+", "M2-"}
    groups = {}
    for pad in pads:
        if pad["net"]:
            groups.setdefault(pad["net"], []).append(pad)
    early = {"GPIO3", "GPIO4", "GPIO7", "GPIO10", "M1_INA", "M1_INB", "M2_INA", "PROG"}

    def rank(name):
        if name in early:
            return 0
        if name == "M2+":
            return 1
        if name in wide or name == "GND":
            return 2
        return 3

    order = sorted(groups, key=lambda name: (rank(name), name))
    if only is not None:
        order = [name for name in order if name in only]
    for name in order:
        width = 0.3 if name in wide else 0.2
        pending = groups[name]
        print(f"routing {name} {len(pending)} pads", flush=True)
        connected = own_cells(pending[0])
        for pad in pending[1:]:
            goals = own_cells(pad)
            if not goals:
                print(f"UNROUTED {name} {pad['ref']}.{pad['num']} empty target")
                continue
            if goals & connected:
                connected |= goals
                continue
            path = search(name, width, connected, goals)
            used = width
            if path is None and width > 0.2:
                path = search(name, 0.2, connected, goals)
                used = 0.2
            if path is None:
                print(f"UNROUTED {name} {pad['ref']}.{pad['num']}")
                continue
            end_layer = path[-1][2]
            path.append(cell_of(pad["x"], pad["y"]) + (end_layer,))
            emit(name, used, path)
            connected |= goals
            connected.update(path)
        print(f"routed {name}")


def write_pcb():
    board = pcbnew.BOARD()
    design = board.GetDesignSettings()
    design.SetBoardThickness(mm(1.6))
    design.m_MinClearance = mm(0.16)
    design.m_TrackMinWidth = mm(0.16)
    design.m_CopperEdgeClearance = mm(0.2)
    design.m_SilkClearance = mm(0.1)
    design.m_MinThroughDrill = mm(0.3)
    try:
        netclass = design.m_NetSettings.GetDefaultNetclass()
        netclass.SetClearance(mm(0.16))
        netclass.SetTrackWidth(mm(0.2))
        netclass.SetViaDiameter(mm(0.55))
        netclass.SetViaDrill(mm(0.3))
    except Exception as error:
        print("netclass", error)
    for attr, value in (
        ("m_HoleClearance", 0.2),
        ("m_HoleToHoleMin", 0.25),
        ("m_MinThroughHoleDiameter", 0.3),
        ("m_ViasMinSize", 0.45),
        ("m_ViasMinDrill", 0.3),
    ):
        if hasattr(design, attr):
            setattr(design, attr, mm(value))

    # Load library footprints before other board objects. The footprint plugin
    # wrapper is easy to invalidate if it is touched later in the same run.
    headers = load_fp("Connector_PinHeader_2.54mm.pretty", "PinHeader_1x08_P2.54mm_Vertical", 2)
    soics = load_fp("Package_SO.pretty", "SOIC-8_3.9x4.9mm_P1.27mm", 2)
    soic_ep = load_fp("Package_SO.pretty", "SOIC-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.3mm")
    diode = load_fp("Diode_SMD.pretty", "D_SOD-123")
    r0603 = load_fp("Resistor_SMD.pretty", "R_0603_1608Metric")
    r0402 = load_fp("Resistor_SMD.pretty", "R_0402_1005Metric", 5)
    c0603 = load_fp("Capacitor_SMD.pretty", "C_0603_1608Metric", 4)
    c0402 = load_fp("Capacitor_SMD.pretty", "C_0402_1005Metric", 4)
    c0805 = load_fp("Capacitor_SMD.pretty", "C_0805_2012Metric")
    led_fp = load_fp("LED_SMD.pretty", "LED_0603_1608Metric")

    outline = [
        (0, 0),
        (5, 0),
        (5, 4),
        (13, 4),
        (13, 0),
        (18, 0),
        (18, BOARD_H),
        (0, BOARD_H),
        (0, 0),
    ]
    for start, end in zip(outline, outline[1:]):
        add_line(board, start[0], start[1], end[0], end[1], pcbnew.Edge_Cuts)

    nets = {}

    def N(name):
        return add_net(board, nets, name)

    for name in (
        "GND",
        "V5",
        "VBAT",
        "VSW",
        "PROG",
        "CHRG",
        "LED_A",
        "M1+",
        "M1-",
        "M2+",
        "M2-",
        "M1_INA",
        "M1_INB",
        "M2_INA",
        "M2_INB",
        "GPIO4",
        "GPIO3",
        "GPIO10",
        "GPIO7",
    ):
        N(name)

    j1 = place(board, headers[0], "J1", "ESP_L", 16.62, 20.15, 180, True)
    j2 = place(board, headers[1], "J2", "ESP_R", 1.38, 20.15, 180, True)
    j3 = place(board, make_wire_fp(), "J3", "WIRES", 3.75, 23.12, 0, True)
    u1 = place(board, soics[0], "U1", "TC118S", 9.0, 11.95, 0, False)
    u2 = place(board, soics[1], "U2", "TC118S", 9.0, 6.55, 0, False)
    u3 = place(board, soic_ep, "U3", "TP4056", 9.0, 17.35, 0, False)
    d1 = place(board, diode, "D1", "B5819W", 5.50, 20.75, 0, False)
    r1 = place(board, r0603, "R1", "10k", 3.50, 16.715, 180, False)
    r2 = place(board, r0402[0], "R2", "1k", 14.15, 17.80, 0, False)
    r3 = place(board, r0402[1], "R3", "100", 4.00, 11.315, 0, False)
    r4 = place(board, r0402[2], "R4", "100", 4.00, 12.585, 0, False)
    r5 = place(board, r0402[3], "R5", "100", 14.20, 7.45, 0, False)
    r6 = place(board, r0402[4], "R6", "100", 14.20, 13.95, 0, False)
    c1 = place(board, c0603[0], "C1", "10uF", 3.85, 19.10, 0, False)
    c2 = place(board, c0603[1], "C2", "10uF", 14.00, 19.40, 0, False)
    c3 = place(board, c0603[2], "C3", "10uF", 3.90, 15.45, 0, False)
    c4 = place(board, c0402[0], "C4", "100nF", 4.20, 13.855, 0, False)
    c5 = place(board, c0603[3], "C5", "10uF", 3.90, 5.50, 0, False)
    c6 = place(board, c0402[1], "C6", "100nF", 4.20, 8.455, 0, False)
    c7 = place(board, c0402[2], "C7", "100nF", 14.20, 11.75, 0, False)
    c8 = place(board, c0402[3], "C8", "100nF", 14.20, 9.75, 0, False)
    c9 = place(board, c0805, "C9", "22uF", 14.05, 5.30, 90, False)
    led = place(board, led_fp, "LED1", "RED", 14.15, 16.715, 0, False)

    j1_nets = ["V5", "GND", None, "GPIO4", "GPIO3", None, None, None]
    j2_nets = [None, None, "GPIO7", None, None, "GPIO10", None, None]
    j3_nets = ["VBAT", "GND", "VBAT", "VSW", "M1+", "M1-", "M2+", "M2-"]
    for index, net_name in enumerate(j1_nets, start=1):
        if net_name:
            set_pad_net(j1, index, N(net_name))
    for index, net_name in enumerate(j2_nets, start=1):
        if net_name:
            set_pad_net(j2, index, N(net_name))
    for index, net_name in enumerate(j3_nets, start=1):
        set_pad_net(j3, index, N(net_name))

    for fp, mapping in (
        (u1, {"2": "M1_INA", "3": "M1_INB", "4": "VSW", "5": "M1-", "6": "GND", "7": "GND", "8": "M1+"}),
        (u2, {"2": "M2_INA", "3": "M2_INB", "4": "VSW", "5": "M2-", "6": "GND", "7": "GND", "8": "M2+"}),
        (
            u3,
            {
                "1": "GND",
                "2": "PROG",
                "3": "GND",
                "4": "V5",
                "5": "VBAT",
                "7": "CHRG",
                "8": "V5",
                "9": "GND",
            },
        ),
    ):
        for number, net_name in mapping.items():
            set_pad_net(fp, number, N(net_name))
    for pad in u3.Pads():
        if pad.GetNumber() in ("", "9"):
            pad.SetNet(N("GND"))

    set_pad_net(d1, "1", N("V5"))
    set_pad_net(d1, "2", N("VSW"))
    set_pad_net(r1, "1", N("PROG"))
    set_pad_net(r1, "2", N("GND"))
    set_pad_net(r2, "1", N("V5"))
    set_pad_net(r2, "2", N("LED_A"))
    set_pad_net(led, "2", N("LED_A"))
    set_pad_net(led, "1", N("CHRG"))
    for fp, a, b in (
        (r3, "GPIO4", "M1_INA"),
        (r4, "GPIO3", "M1_INB"),
        (r5, "GPIO10", "M2_INA"),
        (r6, "GPIO7", "M2_INB"),
    ):
        set_pad_net(fp, "1", N(a))
        set_pad_net(fp, "2", N(b))
    for fp in (c1,):
        set_pad_net(fp, "1", N("V5"))
        set_pad_net(fp, "2", N("GND"))
    set_pad_net(c2, "1", N("VBAT"))
    set_pad_net(c2, "2", N("GND"))
    for fp in (c3, c4, c5, c6, c9):
        set_pad_net(fp, "1", N("VSW"))
        set_pad_net(fp, "2", N("GND"))
    set_pad_net(c7, "1", N("M1+"))
    set_pad_net(c7, "2", N("M1-"))
    set_pad_net(c8, "1", N("M2+"))
    set_pad_net(c8, "2", N("M2-"))

    report_pad_conflicts(board)
    for dx, dy in ((-0.55, -0.8), (0.55, -0.8), (-0.55, 0.8), (0.55, 0.8)):
        add_via(board, N("GND"), 9.0 + dx, 17.35 + dy, drill=0.3, size=0.5)
    autoroute(board)
    stitch_ground(board)

    zone_pts = outline[:-1]
    add_zone(board, N("GND"), pcbnew.B_Cu, zone_pts)
    add_zone(board, N("GND"), pcbnew.F_Cu, zone_pts)

    for text, x in (("+", 3.75), ("-", 5.25), ("+", 9.75), ("-", 11.25), ("+", 12.75), ("-", 14.25)):
        add_text(board, text, x, 21.95)

    board_path = str(ROOT / f"{PROJECT}.kicad_pcb")
    board.Save(board_path)
    clean_saved_board(board_path)


def write_project_files():
    pro = {
        "board": {"design_settings": {"rules": {"min_clearance": 0.16, "min_track_width": 0.16}}},
        "boards": [],
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 1},
        "net_settings": {"classes": [], "meta": {"version": 0}},
        "pcbnew": {"page_layout_descr_file": ""},
        "sheets": [],
        "text_variables": {},
    }
    import json

    (ROOT / f"{PROJECT}.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n", encoding="utf-8")
    (ROOT / "fp-lib-table").write_text(
        "\n".join(
            [
                "(fp_lib_table",
                '  (version 7)',
                '  (lib (name "WirePads")(type "KiCad")(uri "${KIPRJMOD}/footprints/WirePads.pretty")(options "")(descr "Hand solder pads"))',
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (ROOT / "sym-lib-table").write_text(
        "\n".join(
            [
                "(sym_lib_table",
                "  (version 7)",
                '  (lib (name "supermini")(type "KiCad")(uri "${KIPRJMOD}/symbols/supermini.kicad_sym")(options "")(descr "Board symbols"))',
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )
    pretty = ROOT / "footprints" / "WirePads.pretty"
    pretty.mkdir(parents=True, exist_ok=True)
    pads = []
    for index in range(8):
        shape = "circle"
        pads.append(
            f"""\t(pad "{index + 1}" thru_hole {shape}
\t\t(at {fmt(index * 1.5)} 0)
\t\t(size 1.2 1.2)
\t\t(drill 0.7)
\t\t(layers "*.Cu" "*.Mask")
\t\t(remove_unused_layers no)
\t)"""
        )
    mod = "\n".join(
        [
            '(footprint "WirePads_1x08_P1.50mm"',
            "\t(version 20260206)",
            '\t(generator "pcbnew")',
            '\t(layer "F.Cu")',
            '\t(descr "8 hand-solder holes, 1.5 mm pitch, 0.7 mm drill")',
            '\t(attr through_hole)',
            "\t(property \"Reference\" \"REF**\" (at 0 -1.8 0) (layer \"F.Fab\") (hide yes) (effects (font (size 0.6 0.6) (thickness 0.1))))",
            "\t(property \"Value\" \"WirePads_1x08_P1.50mm\" (at 0 1.8 0) (layer \"F.Fab\") (hide yes) (effects (font (size 0.6 0.6) (thickness 0.1))))",
            *pads,
            ")",
            "",
        ]
    )
    (pretty / "WirePads_1x08_P1.50mm.kicad_mod").write_text(mod, encoding="utf-8")


def write_bom():
    rows = [
        ("TC118S", "U1,U2", "SOP-8", "C88308", "Extended"),
        ("TP4056", "U3", "ESOP-8", "C382139", "Extended"),
        ("B5819W", "D1", "SOD-123", "C8598", "Basic"),
        ("KT-0603R", "LED1", "LED0603", "C2286", "Basic"),
        ("0603WAF1002T5E", "R1", "R0603", "C25804", "Basic"),
        ("0402WGF1001TCE", "R2", "R0402", "C11702", "Basic"),
        ("0402WGF1000TCE", "R3,R4,R5,R6", "R0402", "C25076", "Basic"),
        ("10uF 10V", "C1,C2,C3,C5", "C0603", "C19702", "Basic"),
        ("100nF 16V", "C4,C6,C7,C8", "C0402", "C1525", "Basic"),
        ("22uF 25V", "C9", "C0805", "C45783", "Basic"),
    ]
    out = ROOT / "fabrication"
    out.mkdir(exist_ok=True)
    with (out / "bom.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for comment, designator, footprint, lcsc, _library in rows:
            writer.writerow([comment, designator, footprint, lcsc])
    with (out / "part-library.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Comment", "Designator", "LCSC Part #", "JLCPCB library"])
        for comment, designator, _footprint, lcsc, library in rows:
            writer.writerow([comment, designator, lcsc, library])


def main():
    write_project_files()
    lib_symbols, pin_defs = load_library_symbols()
    custom = build_custom_symbols()
    # Parse custom symbols too so Device pins come from the libraries.
    write_schematic(pin_defs, custom, lib_symbols)
    write_pcb()
    write_bom()
    print("wrote project")


if __name__ == "__main__":
    main()
