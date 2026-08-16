import os
import sys

from lefdef import C_LefReader

from schema import Coordinate, Pin


def parse_lef_pins(cell_name: str) -> dict[str, Pin]:
    pdk_root = os.environ.get("PDK_ROOT", "/usr/local/share/pdk")
    pdk = os.environ.get("PDK", "sky130A")

    cell_lib = cell_name.split("__")[0]

    lef_path = os.path.join(
        pdk_root, pdk, "libs.ref", cell_lib, "lef", f"{cell_lib}.lef"
    )

    if not os.path.exists(lef_path):
        raise FileNotFoundError(f"LEF file not found at: {lef_path}")

    # Initialize and read the LEF file
    reader = C_LefReader()
    lef = reader.read(lef_path)

    # Locate the macro matching cell_name
    target_macro = None
    for i in range(lef.c_num_macros):
        if lef.c_macros[i].c_name.decode() == cell_name:
            target_macro = lef.c_macros[i]
            break

    if not target_macro:
        print(f"Cell '{cell_name}' not found in {lef_path}")
        return {}

    pins: dict[str, Pin] = {}

    # Iterate through macro pins
    for j in range(target_macro.c_num_pins):
        pin_obj = target_macro.c_pins[j]
        pin_name = pin_obj.c_name

        centers = []

        # Iterate over pin ports and their geometry rectangles
        for p in range(pin_obj.c_num_ports):
            port = pin_obj.c_ports[p]
            for r in range(port.c_num_rects):
                rect = port.c_rects[r]
                # Calculate rectangle center
                cx = (rect.c_xl + rect.c_xh) / 2.0
                cy = (rect.c_yl + rect.c_yh) / 2.0
                centers.append(Coordinate(x=int(cx * 1000), y=int(cy * 1000)))

        pins[pin_name] = Pin(
            name=pin_name,
            centers=centers,
            net="",
        )

    return pins


if __name__ == "__main__":
    target_cell = sys.argv[1]
    extracted_pins = parse_lef_pins(target_cell)

    print(f"Found {len(extracted_pins)} pins for {target_cell}:")
    for name, pin_data in extracted_pins.items():
        print(
            f"  - Pin '{name}': Center(s) = ({pin_data.centers})"
        )
