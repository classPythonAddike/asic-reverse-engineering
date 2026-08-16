import peewee

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

db_proxy = peewee.DatabaseProxy()


class BaseModel(peewee.Model):
    class Meta:
        database = db_proxy


class DBMetadata(BaseModel):
    units = peewee.FloatField(default=1e-9)


class STDCell(BaseModel):
    name = peewee.CharField(unique=True)  # Instance name (e.g., cell_name_0)
    cell_type = peewee.CharField()
    loc_x = peewee.IntegerField()
    loc_y = peewee.IntegerField()
    num_pins = peewee.IntegerField(default=0)


class Pin(BaseModel):
    std_cell = peewee.ForeignKeyField(STDCell, backref="pins", on_delete="CASCADE")
    name = peewee.CharField()
    net = peewee.CharField(default="")


class PinCenter(BaseModel):
    pin = peewee.ForeignKeyField(Pin, backref="centers", on_delete="CASCADE")
    x = peewee.IntegerField()
    y = peewee.IntegerField()


class Polygon(BaseModel):
    bl_x = peewee.IntegerField()
    bl_y = peewee.IntegerField()
    tr_x = peewee.IntegerField()
    tr_y = peewee.IntegerField()
    layer = peewee.CharField()
    net = peewee.CharField(default="")


class Via(BaseModel):
    center_x = peewee.IntegerField()
    center_y = peewee.IntegerField()
    layer = peewee.CharField()
    net = peewee.CharField(default="")


def initialize_db(db_path: str):
    database = peewee.SqliteDatabase(db_path)
    db_proxy.initialize(database)
    database.connect()
    database.create_tables(
        [DBMetadata, STDCell, Pin, PinCenter, Polygon, Via], safe=True
    )
    return database
