import pydantic
from pydantic import BaseModel

from typing import List, Dict

class Coordinate(BaseModel):
    x: int
    y: int

class Pin(BaseModel):
    name: str
    center: Coordinate # Relative to the bottom-left coordinate of the cell
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

class Vias(BaseModel):
    center: Coordinate
    layer: str
    net: str

class DB(BaseModel):
    std_cells: Dict[str, STDCell] # name: Cell()
    polygons: List[Polygon]
    vias: List[Vias]

