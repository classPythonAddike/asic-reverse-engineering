# ASIC Reverse Engineering Challenge

## Scripts:
- `schema.py`: Database schema written in Pydantic
- `populate.py`: Generate a DB to an SQLITE database
    - Usage: `$ python populate.py SQLITE_DB GDS_LAYOUT`
- `parse_lef.py`: Given a cell name, find the pin locations
    - Requires the `$PDK_ROOT` and `$PDK` env variables to be set

To read the database:
```python
from peewee import fn
from schema import initialize_db, STDCell, Pin, PinCenter, Polygon, Via

db_path = "db.sqlite"
db = initialize_db(db_path)

print("--- Database Summary ---")
print(f"Total Standard Cells: {STDCell.select().count()}")
print(f"Total Pins:           {Pin.select().count()}")
print(f"Total Polygons:       {Polygon.select().count()}")
print(f"Total Vias:           {Via.select().count()}\n")

# Read top 5 Standard Cells along with their related Pins & PinCenters
print("--- Top 5 Standard Cells ---")
cells = STDCell.select().limit(5)

for cell in cells:
    print(f"Cell Instance: {cell.name} (Type: {cell.cell_type}) at ({cell.loc_x}, {cell.loc_y})")
    
    # Query related pins using the Foreign Key relation (backref='pins')
    for pin in cell.pins:
        centers = [(c.x, c.y) for c in pin.centers]
        print(f"  └─ Pin '{pin.name}': Net='{pin.net}', Centers={centers}")

db.close()
```
