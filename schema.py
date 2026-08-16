import pydantic
from pydantic import BaseModel

from typing import List, Dict

# Map SkyWater 130 GDS layer numbers to metal layer names
LAYER_MAP = {
    66: {"MET": "poly", "VIA": "licon"},
    67: {"MET": "li1", "VIA": "mcon"},
    68: {"MET": "met1", "VIA": "via"},
    69: {"MET": "met2", "VIA": "via2"},
    70: {"MET": "met3", "VIA": "via3"},
    71: {"MET": "met4", "VIA": "via4"},
    72: {"MET": "met5"},
}

MET_DATATYPE = 20
VIA_DATATYPE = 44

class Coordinate(BaseModel):
    x: int
    y: int

    def __add__(self, other):
        return Coordinate(x=(self.x + other.x), y=(self.y + other.y))

    def __sub__(self, other):
        return Coordinate(x=(self.x - other.x), y=(self.y - other.y))

    def __floordiv__(self, other):
        return Coordinate(x=self.x // other, y=self.y // other)

class Pin(BaseModel):
    name: str
    centers: List[Coordinate] # Relative to the bottom-left coordinate of the cell
    net: str

class STDCell(BaseModel):
    name: str
    cell_type: str
    pins: Dict[str, Pin] # name: Pin()
    loc: Coordinate # Bottom-left coordinate
    num_pins: int

class Polygon(BaseModel):
    bottom_left: Coordinate
    top_right: Coordinate
    layer: str
    net: str

class Via(BaseModel):
    center: Coordinate
    layer: str
    net: str

class DB(BaseModel):
    units: float # DB units
    std_cells: Dict[str, STDCell] # name: Cell()
    polygons: List[Polygon]
    vias: List[Via]

