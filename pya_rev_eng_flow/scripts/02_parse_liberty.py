"""
02_parse_liberty.py
--------------------
Standalone, no pya/KLayout needed. Parses a SKY130 Liberty (.lib) file
and pulls out, for every cell, its output pin(s) and the `function`
attribute -- this is the Boolean equation the foundry itself publishes
for that cell, in terms of its input pin names. That's what turns
"instance X4 is a sky130_fd_sc_hd__nand2_2" into an actual equation,
with zero polygon-level Boolean derivation needed.

You need a .lib file from the SKY130 PDK, e.g. one of:
  $PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
  (any corner works -- function strings don't change across corners,
   only timing/power numbers do)

If your puzzle only uses a handful of cells and you don't have the PDK
installed, it's also fine to skip this script and hand-fill
CELL_FUNCTIONS below (or in 03_build_expressions.py) for just the
cells that show up in your netlist.json's "cell" fields.

Usage:
  python3 02_parse_liberty.py sky130_fd_sc_hd__tt_025C_1v80.lib cell_functions.json
"""

import re
import sys
import json

def parse_liberty(path):
    text = open(path, "r", errors="ignore").read()

    cells = {}

    # crude but effective brace-matched block extraction for `cell (name) { ... }`
    for m in re.finditer(r'\bcell\s*\(\s*"?([A-Za-z0-9_]+)"?\s*\)\s*\{', text):
        name = m.group(1)
        start = m.end() - 1  # position of the opening brace
        depth = 0
        i = start
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = text[start:i + 1]

        pins = {}
        for pm in re.finditer(r'\bpin\s*\(\s*"?([A-Za-z0-9_\[\]]+)"?\s*\)\s*\{', block):
            pname = pm.group(1)
            pstart = pm.end() - 1
            pdepth = 0
            j = pstart
            while j < len(block):
                if block[j] == '{':
                    pdepth += 1
                elif block[j] == '}':
                    pdepth -= 1
                    if pdepth == 0:
                        break
                j += 1
            pblock = block[pstart:j + 1]

            fm = re.search(r'function\s*:\s*"([^"]*)"', pblock)
            dirm = re.search(r'direction\s*:\s*(\w+)', pblock)
            if fm:
                pins[pname] = {
                    "function": fm.group(1),
                    "direction": dirm.group(1) if dirm else None,
                }

        if pins:
            cells[name] = pins

    return cells


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python3 02_parse_liberty.py <file.lib> <out.json>  [more.lib ...]")
        sys.exit(1)

    out_path = sys.argv[2]
    all_cells = {}

    lib_files = [sys.argv[1]] + sys.argv[3:]
    for lib in lib_files:
        cells = parse_liberty(lib)
        print("%s: found %d cells with function attrs" % (lib, len(cells)))
        all_cells.update(cells)

    with open(out_path, "w") as f:
        json.dump(all_cells, f, indent=2)

    print("Wrote %s (%d cells total)" % (out_path, len(all_cells)))
