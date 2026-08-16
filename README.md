# ASIC Reverse Engineering Challenge

## Scripts:
- `schema.py`: Database schema written in Pydantic
- `populate.py`: Generate a DB from a JSON
    - Usage: `$ python populate.py JSON_DB GDS_LAYOUT`
- `parse_lef.py`: Given a cell name, find the pin locations
    - Usage: Use the `parse_lef_pins(cell_name: str)` function
    - Usage: `$python parse_lef.py CELL_NAME`
    - Requires the `$PDK_ROOT` and `$PDK` env variables to be set

To load the DB from a json file:
```py
from schema import DB

with open("db.json", "r") as file:
    json_data = file.read()
    db = DB.model_validate_json(json_data)

print(len(db.std_cells))
```
