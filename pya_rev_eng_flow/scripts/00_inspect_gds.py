"""
00_inspect_gds.py
-------------------
Run INSIDE KLayout:

  klayout -b -r 00_inspect_gds.py -rd gds_file=puzzle.gds

No assumptions about layer numbers or hierarchy -- this just reports
what's actually in the file, so we can figure out why 01_extract_netlist.py
found 0 circuits. Two things it tells you:

1. HIERARCHY: is this a flat GDS (one cell, everything merged/boolean'd
   together) or does it still have distinct standard-cell instances?
   If it's flat, no amount of layer-number-fixing will make the
   hierarchical "treat std cells as black boxes" approach work --
   you'd need full transistor-level device extraction instead.

2. LAYER PROFILE: every (layer, datatype) pair actually used, with a
   shape count and a bounding-box-based guess at which physical layer
   it probably is (based on typical area/shape-count patterns -- diffusion
   and poly tend to be dense with small shapes, top metal/power straps
   are big sparse rectangles, vias/contacts are tiny and extremely
   numerous, text labels have zero area). Treat the guesses as hints,
   not truth -- confirm visually in the KLayout GUI by toggling one
   layer at a time.
"""

import pya

gds_file = globals().get("gds_file", "puzzle.gds")

ly = pya.Layout()
ly.read(gds_file)

print("=" * 70)
print("FILE:", gds_file)
print("dbu:", ly.dbu)
print("=" * 70)

# ---------------- hierarchy ----------------
print("\n--- CELLS ---")
cells = list(ly.each_cell())
print("Total cells in file:", len(cells))

top_cells = list(ly.top_cells())
print("Top cell(s):", [c.name for c in top_cells])

for c in cells:
    n_inst = c.child_instances()
    n_shapes = sum(c.shapes(li).size() for li in ly.layer_indexes())
    print("  cell %-40s  instances(children)=%-6d  own_shapes(all layers)=%d" %
          (c.name, n_inst, n_shapes))

if len(cells) <= 1:
    print("\n*** Only one cell -- this GDS looks FLAT. The hierarchical")
    print("*** std-cell-as-blackbox approach won't find any subcircuits.")
    print("*** You'll need transistor-level device extraction instead.")

# ---------------- layer profile ----------------
print("\n--- LAYERS ---")
top = top_cells[0] if top_cells else ly.top_cell()

rows = []
for li in ly.layer_indexes():
    info = ly.get_info(li)
    it = pya.RecursiveShapeIterator(ly, top, li)
    n_shapes = 0
    n_text = 0
    total_area = 0
    while not it.at_end():
        s = it.shape()
        if s.is_text():
            n_text += 1
        else:
            n_shapes += 1
            try:
                total_area += s.area()
            except Exception:
                pass
        it.next()
    # bbox over the whole cell for this layer (recurses into instances)
    try:
        bbox = top.bbox(li)
    except Exception:
        bbox = pya.Box()
    rows.append((info.layer, info.datatype, info.name, n_shapes, n_text, total_area, bbox))

rows.sort(key=lambda r: -(r[3] + r[4]))

print("%-6s %-6s %-12s %10s %8s %14s %s" %
      ("layer", "dtype", "name", "#polygons", "#texts", "total_area(um^2)", "bbox"))
for layer, dtype, name, n_shapes, n_text, area, bbox in rows:
    area_um2 = area * ly.dbu * ly.dbu
    print("%-6d %-6d %-12s %10d %8d %14.3f %s" %
          (layer, dtype, name or "", n_shapes, n_text, area_um2, bbox.to_s()))

print("""
--- how to read this ---
* A layer/datatype pair with a HUGE polygon count and small individual
  shapes, densely packed = likely diffusion, poly, or a contact/via
  layer (licon/mcon/via*).
* A layer with FEW, LARGE rectangles spanning big X or Y extents =
  likely a power rail / strap (met4/met5) or a well layer.
* A layer with ONLY texts (n_shapes=0, n_text>0) = a label/pin-name
  layer -- these are the ones to pair as the *_pin / *_txt layers in
  01_extract_netlist.py, and the layer immediately below (that
  overlaps them) is what to register as the matching shape layer.
* If NOTHING at all resembles the sky130A numbers I assumed
  (64-72 range with datatypes 20/44/16/5), the puzzle almost certainly
  remapped or renumbered layers -- rebuild the layer set in
  01_extract_netlist.py using the numbers you see here instead.
""")
