"""
01_extract_netlist.py
----------------------
Runs INSIDE KLayout (needs the `pya` module), either:

  klayout -b -r 01_extract_netlist.py \
      -rd gds_file=puzzle.gds \
      -rd top_cell=TOP \
      -rd out_json=netlist.json

or paste into Tools > Macro Development > Python and hit run
(edit the CONFIG block below if you're not passing -rd args).

What it does
------------
This is scripting the exact same engine the "Trace Nets" GUI feature
uses: db.LayoutToNetlist. We declare the SKY130A routing-stack layers
and how they connect (li1 -> mcon -> met1 -> via1 -> met2 -> ... -> met5),
run extract_netlist() over the WHOLE hierarchy (no flattening), and
KLayout automatically:
  - recognizes every std-cell instance as a SubCircuit
  - builds one Circuit (with named Pins) per *unique* cell it sees,
    derived from the pin-label text shapes inside each std cell
  - resolves every net to the instance/pin pairs it connects

We deliberately do NOT include poly/diff/nwell here: since we only
want the inter-cell connectivity (who connects to whom), the interface
of every std cell is already fully described by its li1/met1 pin
labels. If you also want to verify a cell's *internal* transistor
netlist (e.g. to confirm it really is an INV and not a relabeled cell),
add the device-extraction layers/rules -- that's a separate, heavier
step (see note at the bottom).

Output: a JSON file with one entry per circuit (std cell type, plus
the top-level circuit), each with its pins, its subcircuit instances,
and its nets (and which instance/pin each net touches).
"""

import pya
import json
import os

# ---------------- CONFIG ----------------
gds_file  = globals().get("gds_file",  "puzzle.gds")
top_cell  = globals().get("top_cell",  None)   # None -> layout.top_cell()
out_json  = globals().get("out_json",  "netlist.json")
# -----------------------------------------

ly = pya.Layout()
ly.read(gds_file)

top = ly.cell(top_cell) if top_cell else ly.top_cell()
if top is None:
    raise RuntimeError("Could not find top cell '%s' in %s" % (top_cell, gds_file))

print("Top cell: %s   (gds: %s)" % (top.name, gds_file))

# SKY130A layer/datatype map (from the sky130A.lyt tech file), routing stack
# plus pin/label layers. Confirmed against the actual layer palette for this
# file -- li1/met1/met2 "pin" vs "label" datatypes are swapped from KLayout's
# own naming convention (pin=X/16, label=X/5) vs what I originally guessed;
# doesn't change behavior here since we connect both to their shape layer
# regardless, but listed correctly below for clarity.
layer_defs = {
    "li1":      (67, 20), "li1_pin":  (67, 16), "li1_label":  (67, 5),
    "mcon":     (67, 44),
    "met1":     (68, 20), "met1_pin": (68, 16), "met1_label": (68, 5),
    "via1":     (68, 44),
    "met2":     (69, 20), "met2_pin": (69, 16), "met2_label": (69, 5),
    "via2":     (69, 44),
    "met3":     (70, 20), "met3_pin": (70, 16), "met3_label": (70, 5),
    "via3":     (70, 44),
    "met4":     (71, 20), "met4_pin": (71, 16), "met4_label": (71, 5),
    "via4":     (71, 44),
    "met5":     (72, 20), "met5_pin": (72, 16), "met5_label": (72, 5),
}

# Resolve every layer index FIRST, then build the RecursiveShapeIterator
# with that explicit list of indices. Passing [] here previously scoped
# the iterator to zero layers, which is why extraction found 0 circuits --
# make_polygon_layer()/make_text_layer() pull from `ly` directly, but the
# iterator's own layer scope still gates what LayoutToNetlist actually sees.
layer_idx = {name: ly.layer(*ld) for name, ld in layer_defs.items()}

it = pya.RecursiveShapeIterator(ly, top, list(layer_idx.values()))
l2n = pya.LayoutToNetlist(it)

def poly_layer(name):
    return l2n.make_polygon_layer(layer_idx[name], name)

def text_layer(name):
    return l2n.make_text_layer(layer_idx[name], name)

li1       = poly_layer("li1")
li1_pin   = text_layer("li1_pin")
li1_label = text_layer("li1_label")
mcon      = poly_layer("mcon")
met1      = poly_layer("met1")
met1_pin  = text_layer("met1_pin")
met1_label = text_layer("met1_label")
via1      = poly_layer("via1")
met2      = poly_layer("met2")
met2_pin  = text_layer("met2_pin")
met2_label = text_layer("met2_label")
via2      = poly_layer("via2")
met3      = poly_layer("met3")
met3_pin  = text_layer("met3_pin")
met3_label = text_layer("met3_label")
via3      = poly_layer("via3")
met4      = poly_layer("met4")
met4_pin  = text_layer("met4_pin")
met4_label = text_layer("met4_label")
via4      = poly_layer("via4")
met5      = poly_layer("met5")
met5_pin  = text_layer("met5_pin")
met5_label = text_layer("met5_label")

# same-layer connectivity
for layer in (li1, mcon, met1, via1, met2, via2, met3, via3, met4, via4, met5):
    l2n.connect(layer)

# routing stack, bottom to top
l2n.connect(li1,  mcon)
l2n.connect(mcon, met1)
l2n.connect(met1, via1)
l2n.connect(via1, met2)
l2n.connect(met2, via2)
l2n.connect(via2, met3)
l2n.connect(met3, via3)
l2n.connect(via3, met4)
l2n.connect(met4, via4)
l2n.connect(via4, met5)

# attach labels so nets/pins get real names instead of auto IDs
l2n.connect(li1,  li1_pin)
l2n.connect(li1,  li1_label)
l2n.connect(met1, met1_pin)
l2n.connect(met1, met1_label)
l2n.connect(met2, met2_pin)
l2n.connect(met2, met2_label)
l2n.connect(met3, met3_pin)
l2n.connect(met3, met3_label)
l2n.connect(met4, met4_pin)
l2n.connect(met4, met4_label)
l2n.connect(met5, met5_pin)
l2n.connect(met5, met5_label)

print("Extracting netlist (this walks the whole hierarchy, may take a bit)...")
l2n.extract_netlist()

netlist = l2n.netlist()
print("Circuits extracted:", sum(1 for _ in netlist.each_circuit()))

# NOTE: deliberately NOT calling netlist.make_top_level_pins() or
# purge()/purge_nets() here. All three are LVS-comparison cleanup/prep
# steps (meant for comparing against a reference netlist, which we don't
# have) and empirically they clear out the subcircuit-pin references on
# every net when run on a full-chip top with no declared top pins --
# exactly the data we actually want to read out. Skip them; we want the
# extraction results as-is.

data = {"top": top.name, "circuits": []}

def sc_key(sc):
    # prefer the stable integer id KLayout db objects expose; fall back
    # to python object identity if this binding doesn't have .id()
    # (works fine as long as each_subcircuit() reuses wrapper objects
    # within a single circuit's processing block, which it does here).
    return sc.id() if hasattr(sc, "id") else id(sc)

for circuit in netlist.each_circuit():
    c = {"name": circuit.name, "pins": [], "subcircuits": [], "nets": []}

    for pin in circuit.each_pin():
        c["pins"].append(pin.name())

    inst_id_by_id = {}
    for idx, sc in enumerate(circuit.each_subcircuit()):
        # GDS placements have no instance name (that's a DEF/Verilog-level
        # concept), so sc.name is always "". Synthesize a stable, unique
        # id instead, and grab the placement transform if this binding
        # exposes it, so each instance can be traced back to real GDS
        # coordinates. Key by sc.id() (a stable integer), not the sc
        # object itself -- each_subcircuit() may hand back a fresh Python
        # wrapper per call even for the same underlying object.
        cell_name = sc.circuit_ref().name
        inst_id = "%s#%d" % (cell_name, idx)
        entry = {"instance": inst_id, "cell": cell_name}
        try:
            tr = sc.trans()
            entry["x"] = tr.disp().x * ly.dbu
            entry["y"] = tr.disp().y * ly.dbu
            entry["rot"] = tr.angle if hasattr(tr, "angle") else None
        except Exception:
            pass
        c["subcircuits"].append(entry)
        inst_id_by_id[sc_key(sc)] = inst_id

    for net in circuit.each_net():
        n = {"name": net.expanded_name(), "top_pins": [], "instance_pins": []}
        for pin_ref in net.each_pin():
            n["top_pins"].append(pin_ref.pin().name())
        for pin_ref in net.each_subcircuit_pin():
            sc = pin_ref.subcircuit()
            n["instance_pins"].append({
                "instance": inst_id_by_id.get(sc_key(sc), "?"),
                "cell": sc.circuit_ref().name,
                "pin": pin_ref.pin().name(),
            })
        c["nets"].append(n)

    data["circuits"].append(c)

with open(out_json, "w") as f:
    json.dump(data, f, indent=2)

print("Wrote %s  (%d circuits)" % (out_json, len(data["circuits"])))

# ---------------------------------------------------------------------
# If you also want an internal, transistor-level LVS-style extraction
# (to double check std-cell identity rather than trust cell names),
# that needs MOS device recognition rules registered on l2n, e.g.:
#
#   diff  = poly_layer(l2n, 65, 20, "diff")
#   poly  = poly_layer(l2n, 66, 20, "poly")
#   nwell = poly_layer(l2n, 64, 20, "nwell")
#   pmos = l2n.make_device_class(...)   # or use DeviceExtractorMOS3Transistor
#   l2n.extract_devices(pmos, {"S": diff, "G": poly, "D": diff, "W": nwell})
#
# This is the same setup used by the official SKY130 KLayout LVS deck
# (see the vlsida chip-tutorials "Running LVS" page) -- for your
# purposes (recovering the gate-level netlist) you almost certainly
# don't need this; skip it unless a cell's identity is in doubt.
# ---------------------------------------------------------------------
