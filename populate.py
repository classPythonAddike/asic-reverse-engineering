import os
import sys
import gdstk
import logging

from parse_lef import parse_and_insert_lef_pins

from schema import initialize_db
from schema import DBMetadata, STDCell, Polygon, Via
from schema import LAYER_MAP, MET_DATATYPE, VIA_DATATYPE


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

output_db_path = sys.argv[1]
gds_file = sys.argv[2]

if os.path.exists(output_db_path):
    os.remove(output_db_path)

logging.info(f"Initializing DB: {output_db_path}")
db = initialize_db(output_db_path)

with db.atomic():
    DBMetadata.create(units=1e-9)

library = gdstk.read_gds(gds_file, 1e-9)
top_cell = library.top_level()[0]


def process_polygon(poly):
    """Processes and inserts a polygon or via directly into the database."""
    if poly.layer not in LAYER_MAP:
        return

    bbox = poly.bounding_box()
    if bbox is None:
        return

    (min_x, min_y), (max_x, max_y) = bbox
    bl_x, bl_y = int(min_x), int(min_y)
    tr_x, tr_y = int(max_x), int(max_y)

    if poly.datatype == MET_DATATYPE:
        met_name = LAYER_MAP[poly.layer].get("MET")
        if met_name:
            Polygon.create(
                bl_x=bl_x,
                bl_y=bl_y,
                tr_x=tr_x,
                tr_y=tr_y,
                layer=met_name,
                net="",
            )

    elif poly.datatype == VIA_DATATYPE:
        via_name = LAYER_MAP[poly.layer].get("VIA")
        if via_name:
            center_x = (bl_x + tr_x) // 2
            center_y = (bl_y + tr_y) // 2
            Via.create(
                center_x=center_x,
                center_y=center_y,
                layer=via_name,
                net="",
            )


total_count = len(top_cell.polygons)
logging.info(f"Starting polygon processing. Total: {total_count}")
for count, poly in enumerate(top_cell.polygons, 1):
    process_polygon(poly)
    if count % (total_count // 10) == 0:
        logging.info(f"Processed {count} / {total_count} top-level polygons")
logging.info(f"Finished polygon processing.")

total_count = len(top_cell.references)
logging.info(f"Starting std cell processing. Total: {total_count}")
for i, ref in enumerate(top_cell.references):
    cell_name = ref.cell.name

    if (
        "via" in cell_name.lower()
        or "mcon" in cell_name.lower()
        or "licon" in cell_name.lower()
    ):
        with db.atomic():
            for poly in ref.get_polygons(include_paths=True):
                process_polygon(poly)

    elif cell_name.startswith("sky130"):
        bbox = ref.bounding_box()
        if bbox is not None:
            min_x, min_y = bbox[0]
            loc_x, loc_y = int(min_x), int(min_y)
        else:
            loc_x, loc_y = int(ref.origin[0]), int(ref.origin[1])

        inst_name = f"{cell_name}_{i}"

        with db.atomic():
            cell_record = STDCell.create(
                name=inst_name,
                cell_type=cell_name,
                loc_x=loc_x,
                loc_y=loc_y,
                num_pins=0,
            )

            num_pins = parse_and_insert_lef_pins(cell_record)
            cell_record.num_pins = num_pins
            cell_record.save()

    else:
        logging.warning(f"Ignoring cell: {cell_name}")

    if (i + 1) % (total_count // 10) == 0:
        logging.info(f"Processed {i} / {total_count} std cells")

logging.info(f"Finished std cell processing.")

logging.info("Database population complete!")
logging.info(f"Standard Cells: {STDCell.select().count()}")
logging.info(f"Polygons: {Polygon.select().count()}")
logging.info(f"Vias: {Via.select().count()}")

db.close()
