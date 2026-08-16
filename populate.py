import sys
import gdstk

from parse_lef import parse_lef_pins
from schema import DB, STDCell, Polygon, Coordinate, Via
from schema import LAYER_MAP, MET_DATATYPE, VIA_DATATYPE


output_json = sys.argv[1]
gds_file = sys.argv[2]

db = DB(std_cells={}, polygons=[], vias=[], units=1e-9)

library = gdstk.read_gds(gds_file, 1e-9)
top_cell = library.top_level()[0]


def process_polygon(poly):
    """Processes and appends a polygon to db.polygons or db.vias if valid."""
    if poly.layer not in LAYER_MAP:
        return

    bbox = poly.bounding_box()
    if bbox is None:
        return

    (min_x, min_y), (max_x, max_y) = bbox
    bl = Coordinate(x=int(min_x), y=int(min_y))
    tr = Coordinate(x=int(max_x), y=int(max_y))

    if poly.datatype == MET_DATATYPE:
        met_name = LAYER_MAP[poly.layer].get("MET")
        if met_name:
            db_poly = Polygon(
                bottom_left=bl,
                top_right=tr,
                layer=met_name,
                net="",
            )
            db.polygons.append(db_poly)

    elif poly.datatype == VIA_DATATYPE:
        via_name = LAYER_MAP[poly.layer].get("VIA")
        if via_name:
            center = (bl + tr) // 2
            db_via = Via(
                center=center,
                layer=via_name,
                net="",
            )
            db.vias.append(db_via)


# 1. Process top-level loose polygons and vias
for poly in top_cell.polygons:
    process_polygon(poly)

# 2. Iterate through top-level references
for i, ref in enumerate(top_cell.references):
    cell_name = ref.cell.name

    # Include via cell instances for inter-cell routing
    if (
        "via" in cell_name.lower()
        or "mcon" in cell_name.lower()
        or "licon" in cell_name.lower()
    ):
        for poly in ref.get_polygons(include_paths=True):
            process_polygon(poly)
    # Populate std_cells for cells starting with sky130_fd
    elif cell_name.startswith("sky130"):
        bbox = ref.bounding_box()
        if bbox is not None:
            min_x, min_y = bbox[0]
            loc = Coordinate(x=int(min_x), y=int(min_y))
        else:
            loc = Coordinate(x=int(ref.origin[0]), y=int(ref.origin[1]))

        # Unique key for std_cells dictionary (instance name)
        inst_name = f"{cell_name}_{i}"

        pins = parse_lef_pins(cell_name)

        std_cell = STDCell(
            name=inst_name,
            cell_type=cell_name,
            pins=pins,
            loc=loc,
            num_pins=0,
        )
        db.std_cells[inst_name] = std_cell
    else:
        print("Ignoring cell:", cell_name)

print("Number of standard cells:", len(db.std_cells))
print("Number of polygons:", len(db.polygons))
print("Number of vias:", len(db.vias))

with open(output_json, "w") as f:
    f.write(db.model_dump_json(indent=4))
