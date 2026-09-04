"""
04_netlist_to_verilog.py
--------------------------
Standalone. Turns netlist.json (from 01_extract_netlist.py) into
structural Verilog -- i.e. it reconstructs something close to your
warmup's 02_netlist_with_power_rails.v, but for the puzzle GDS.

This is useful as a second, independent path to the same answer:
instead of (or in addition to) 03_build_expressions.py's symbolic
substitution, hand this to Yosys + the sky130 liberty and let a real
synthesis/optimization tool (ABC) simplify it and print the logic.

Usage:
  python3 04_netlist_to_verilog.py netlist.json TOP_CIRCUIT_NAME out.v [cell_functions.json]

Passing cell_functions.json (from 02_parse_liberty.py) is strongly
recommended: any instance whose cell type is NOT a key in that file has
no Liberty entry at all, meaning Yosys will have no module definition
for it and error out with "not part of the design" -- this covers ANY
physical-only cell (vias, taps, decaps, fill cells, antenna diodes,
endcaps, etc.) generically, rather than guessing by name. Without it,
the script falls back to a hardcoded name-pattern list which is not
guaranteed to catch every physical-only cell type in every design.
"""

import sys
import json
import re


def sanitize(name):
    n = re.sub(r"\W", "_", name)
    if re.match(r"^\d", n):
        n = "n_" + n
    return n


POWER_PINS = {"VPWR", "VGND", "VPB", "VNB", "VDD", "VSS"}

# Fallback only -- used when no cell_functions.json is provided. Not
# exhaustive; prefer passing cell_functions.json so the check is driven by
# what the Liberty file actually declares instead of name guesses.
KNOWN_PHYSICAL_ONLY_PATTERNS = ("via_", "tapvpwrvgnd", "decap", "fill", "endcap", "diode")


def main():
    if len(sys.argv) < 4:
        print("usage: python3 04_netlist_to_verilog.py netlist.json TOP_NAME out.v [cell_functions.json]")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        data = json.load(f)
    top_name = sys.argv[2]
    out_path = sys.argv[3]

    known_logic_cells = None
    cell_functions = None
    if len(sys.argv) > 4:
        with open(sys.argv[4]) as f:
            cell_functions = json.load(f)
        known_logic_cells = set(cell_functions.keys())
        print("Loaded %d known logic-cell types from %s" % (len(known_logic_cells), sys.argv[4]))

    def is_physical_only(cell_name):
        if known_logic_cells is not None:
            # authoritative: if Liberty never declared this cell, Yosys has
            # no module for it, full stop -- regardless of what it's named.
            return cell_name not in known_logic_cells
        # fallback: name-pattern guess only, used when cell_functions.json
        # wasn't supplied.
        low = cell_name.lower()
        return any(pat in low for pat in KNOWN_PHYSICAL_ONLY_PATTERNS)

    top = None
    for c in data["circuits"]:
        if c["name"] == top_name:
            top = c
            break
    if top is None:
        print("Available circuits:", [c["name"] for c in data["circuits"]])
        raise SystemExit("Top circuit %r not found" % top_name)

    # net -> list of (instance, pin)
    net_pins = {}
    for net in top["nets"]:
        net_pins[net["name"]] = net["instance_pins"]

    # instance -> {pin: net}
    inst_conn = {}
    inst_cell = {}
    for sc in top["subcircuits"]:
        inst_conn[sc["instance"]] = {}
        inst_cell[sc["instance"]] = sc["cell"]
    for net in top["nets"]:
        for ip in net["instance_pins"]:
            inst_conn.setdefault(ip["instance"], {})[ip["pin"]] = net["name"]

    all_nets = sorted(net_pins.keys())

    # NOTE: top["pins"] is ALWAYS empty for a genuine top-level circuit (see
    # earlier debug session -- KLayout's model only creates Pin objects for
    # circuits that get instantiated as a subcircuit somewhere, and "puzzle"
    # isn't). Using it as the module port list produces a module with ZERO
    # ports, which makes every internal net invisible from the outside --
    # Yosys's opt_clean then (correctly, from its point of view) deletes the
    # entire design as unobserved dead logic and ABC has nothing to map.
    #
    # Instead: any net with a real, surviving label (not an auto-generated
    # $N id) and that isn't a power net is a design-boundary signal worth
    # keeping visible. Classify each as input/output using the same
    # driver-detection approach as 03_build_expressions.py when
    # cell_functions.json is available; otherwise fall back to `inout`,
    # which is directionally vague but still prevents opt_clean from
    # pruning the logic (any port, regardless of direction, counts as an
    # externally-observed signal).
    def find_driver(net_name):
        drivers = []
        if cell_functions is None:
            return drivers
        for ip in net_pins.get(net_name, []):
            info = cell_functions.get(ip["cell"], {}).get(ip["pin"])
            if info and info.get("function"):
                drivers.append(ip)
        return drivers

    port_nets = []
    for n in all_nets:
        if re.match(r"^\$\d+$", n):
            continue
        if n.upper() in POWER_PINS:
            continue
        port_nets.append(n)

    port_dirs = {}
    for n in port_nets:
        if cell_functions is not None:
            drivers = find_driver(n)
            if len(drivers) == 1:
                port_dirs[n] = "output"
            elif len(drivers) == 0:
                port_dirs[n] = "input"
            else:
                port_dirs[n] = "inout"  # ambiguous multi-driver, flag via direction
        else:
            port_dirs[n] = "inout"

    print("Identified %d boundary (labeled, non-power) net(s) as module ports" % len(port_nets))
    if cell_functions is None:
        print("(no cell_functions.json given -- ports declared as `inout` rather than "
              "input/output; pass cell_functions.json as the 4th arg for correct directions)")

    lines = []
    lines.append("module %s (" % sanitize(top_name))
    lines.append(",\n".join("    " + sanitize(p) for p in port_nets))
    lines.append(");")
    for p in port_nets:
        lines.append("  %s %s;" % (port_dirs[p], sanitize(p)))
    lines.append("")
    for n in all_nets:
        if n not in port_nets:
            lines.append("  wire %s;" % sanitize(n))
    lines.append("")

    dropped_cells = {}
    emitted_count = 0

    for inst, conns in inst_conn.items():
        cell = inst_cell.get(inst, "UNKNOWN_CELL")

        # Any cell type Liberty never declared (or that name-pattern-matches
        # a known physical-only cell, if no cell_functions.json was given)
        # has no module Yosys can resolve -- drop the instance entirely.
        # This is electrically safe: the net(s) it sits on already include
        # the real logic cells on both sides directly, since KLayout merges
        # electrically-connected shapes into one net regardless of which
        # cell hosts them.
        if is_physical_only(cell):
            dropped_cells[cell] = dropped_cells.get(cell, 0) + 1
            continue

        lines.append("  %s %s (" % (sanitize(cell), sanitize(inst)))
        conn_strs = []
        for pin, net in conns.items():
            if not pin:
                continue
            # Liberty .lib files generally only declare logic pins in their
            # pin() groups, not power/ground -- Yosys's imported blackbox
            # module for this cell has no VPWR/VGND port to connect to, and
            # ABC doesn't need power connectivity to resynthesize logic
            # anyway, so drop these.
            if pin.upper() in POWER_PINS:
                continue
            conn_strs.append("    .%s(%s)" % (sanitize(pin), sanitize(net)))
        if not conn_strs:
            # No logic pins left after filtering -- catches any physical-only
            # cell that slipped past is_physical_only() (e.g. a Liberty-known
            # cell type that nonetheless has zero non-power pins).
            lines.pop()
            dropped_cells[cell] = dropped_cells.get(cell, 0) + 1
            continue
        lines.append(",\n".join(conn_strs))
        lines.append("  );")
        emitted_count += 1
    lines.append("endmodule")

    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("Wrote %s" % out_path)
    print("Emitted %d cell instances" % emitted_count)
    if dropped_cells:
        print("Dropped %d physical-only instance(s) across %d cell type(s):" %
              (sum(dropped_cells.values()), len(dropped_cells)))
        for cell, count in sorted(dropped_cells.items(), key=lambda x: -x[1]):
            print("    %-40s x%d" % (cell, count))
        if known_logic_cells is None:
            print("(no cell_functions.json was given -- this list is name-pattern-based, "
                  "not guaranteed complete; re-run with cell_functions.json as the 4th arg "
                  "for an authoritative check against the actual Liberty file)")
    print("""
Next: run it through Yosys with the sky130 liberty, e.g.

  yosys -p '
    read_verilog %s
    read_liberty -lib -ignore_miss_dir sky130_fd_sc_hd__tt_025C_1v80.lib
    hierarchy -check -top %s
    flatten
    techmap
    opt
    abc -liberty sky130_fd_sc_hd__tt_025C_1v80.lib
    opt_clean
    write_verilog -noattr resynth.v
  '

Module ports above are now derived from labeled boundary nets (see
"Identified N boundary net(s)" above), not from top["pins"] (which is
always empty for a genuine top circuit -- KLayout only creates Pin
objects for circuits that get instantiated as a subcircuit somewhere).
If a port came out as `inout` because cell_functions.json wasn't
passed, or because a net had more than one driver (flagged as
ambiguous), you may want to fix the direction by hand before reading
resynth.v.
""" % (out_path, sanitize(top_name)))


if __name__ == "__main__":
    main()
