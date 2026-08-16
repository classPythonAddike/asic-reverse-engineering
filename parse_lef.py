import os
import sys
import logging

from lefdef import C_LefReader
from schema import STDCell, Pin, PinCenter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

def parse_and_insert_lef_pins(cell_record: STDCell) -> int:
    """
    Parses LEF geometry for a cell and creates Pin and PinCenter records directly in the DB.
    Returns the count of pins inserted.
    """
    cell_name = cell_record.cell_type
    pdk_root = os.environ.get("PDK_ROOT", "/usr/local/share/pdk")
    pdk = os.environ.get("PDK", "sky130A")

    cell_lib = cell_name.split("__")[0]

    lef_path = os.path.join(
        pdk_root, pdk, "libs.ref", cell_lib, "lef", f"{cell_lib}.lef"
    )

    if not os.path.exists(lef_path):
        raise FileNotFoundError(f"LEF file not found at: {lef_path}")

    reader = C_LefReader()
    lef = reader.read(lef_path)

    target_macro = None
    for i in range(lef.c_num_macros):
        if lef.c_macros[i].c_name.decode() == cell_name:
            target_macro = lef.c_macros[i]
            break

    if not target_macro:
        logging.warning(f"Cell '{cell_name}' not found in {lef_path}")
        return 0

    pin_count = target_macro.c_num_pins

    for j in range(pin_count):
        pin_obj = target_macro.c_pins[j]
        pin_name = pin_obj.c_name

        pin_record = Pin.create(
            std_cell=cell_record,
            name=pin_name,
            net="",
        )

        centers_to_insert = []

        for p in range(pin_obj.c_num_ports):
            port = pin_obj.c_ports[p]
            for r in range(port.c_num_rects):
                rect = port.c_rects[r]
                cx = (rect.c_xl + rect.c_xh) / 2.0
                cy = (rect.c_yl + rect.c_yh) / 2.0

                centers_to_insert.append({
                    "pin": pin_record,
                    "x": int(cx * 1000),
                    "y": int(cy * 1000),
                })

        if centers_to_insert:
            PinCenter.insert_many(centers_to_insert).execute()

    return pin_count
