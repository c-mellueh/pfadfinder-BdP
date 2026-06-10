from build123d import BuildPart,extrude,Locations,Cylinder,Mode,Vector,Text,FontStyle,Align
from build123d import Mesher, Color,BuildSketch,Plane,RectangleRounded
from build123d.build_enums import MeshType
import pandas as pd
import copy as _copy, os, re
import lib3mf   # je nach Install heißt das Paket lib3mf
import zipfile
from pathlib import Path
MODEL_SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="{obj_id}">
    <metadata key="name" value="{name}"/>
    <part id="{plate_id}" subtype="normal_part">
      <metadata key="name" value="plate"/>
      <metadata key="extruder" value="1"/>
    </part>
    <part id="{text_id}" subtype="normal_part">
      <metadata key="name" value="text"/>
      <metadata key="extruder" value="2"/>
    </part>
  </object>
</config>
"""




# --- parameters ---
PLATE_W, PLATE_H, PLATE_T = 40, 12, 0.5    # mm
TEXT_T    = 0.2                           # raised text height
FONT      = "Nimbus Mono PS"              # monospace, plain zeros
FONT_SIZE = 7
HOLE_D    = 6.0                           # hanging hole diameter
CORNER_R  = 6.0  




def make_mesh(mesher, shape, color: Color):
    mesh_3mf = mesher.model.AddMeshObject()
    verts, tris = Mesher._mesh_shape(_copy.deepcopy(shape), 0.001, 0.1)
    verts_3mf, tris_3mf = Mesher._create_3mf_mesh(verts, tris)
    mesh_3mf.SetGeometry(verts_3mf, tris_3mf)
    mesh_3mf.SetType(Mesher._map_b3d_mesh_type_3mf[MeshType.MODEL])

    grp = mesher.model.AddColorGroup()
    color_id = grp.AddColor(mesher.wrapper.FloatRGBAToColor(*tuple(color)))

    # Object-Level (schadet nicht) ...
    mesh_3mf.SetObjectLevelProperty(grp.GetResourceID(), color_id)

    # ... und zusätzlich pro Dreieck — das liest Orca tatsächlich
    props = lib3mf.TriangleProperties()
    props.ResourceID = grp.GetResourceID()
    props.PropertyIDs[0] = color_id
    props.PropertyIDs[1] = color_id
    props.PropertyIDs[2] = color_id
    for i in range(mesh_3mf.GetTriangleCount()):
        mesh_3mf.SetTriangleProperties(i, props)

    mesher.meshes.append(mesh_3mf)
    return mesh_3mf

def add_assembly(mesher, *meshes):
    comp = mesher.model.AddComponentsObject()
    identity = mesher.wrapper.GetIdentityTransform()
    for mesh in meshes:
        comp.AddComponent(mesh, identity)
    mesher.model.AddBuildItem(comp, identity)
    return comp


def make_sign(label: str):
    hole_r = HOLE_D / 2
    hole_x = -PLATE_W / 2 + hole_r + 2.0  # 2 mm edge margin

    corner_r = min(CORNER_R, min(PLATE_W, PLATE_H) / 2 - 0.01)
    with BuildPart() as plate:
        with BuildSketch(Plane.XY.offset(-PLATE_T / 2)):
            RectangleRounded(PLATE_W, PLATE_H, corner_r)
        extrude(amount=PLATE_T)
        with Locations([(hole_x, 0, 0)]):
            Cylinder(radius=hole_r, height=PLATE_T + 1, mode=Mode.SUBTRACT)

    text_anchor_x = PLATE_W / 2 - 4.0  # 2 mm padding from right edge
    text_anchor_x_bottom = -PLATE_W / 2 + 4.0  # 2 mm padding from right edge

    # x_dir=-1 pre-mirrors each character so the flip when reading from below cancels it out
    bottom_plane = Plane(
        origin=Vector(0, 0, -PLATE_T / 2),
        x_dir=Vector(-1, 0, 0),
        z_dir=Vector(0, 0, -1),
    )
    with BuildPart() as text:
        #Top Text
        with BuildSketch(Plane.XY.offset(PLATE_T / 2)):
            with Locations([(text_anchor_x, 0)]):
                Text(label, font=FONT, font_size=FONT_SIZE,
                     font_style=FontStyle.BOLD,
                     align=(Align.MAX, Align.CENTER))
        extrude(amount=-TEXT_T)
        #Bottom Text
        with BuildSketch(bottom_plane):
            with Locations([(text_anchor_x_bottom, 0)]):
                Text(label, font=FONT, font_size=FONT_SIZE,
                     font_style=FontStyle.BOLD,
                     align=(Align.MIN, Align.CENTER))
        extrude(amount=-TEXT_T)
    return plate.part, text.part


df = pd.read_csv("Daten.csv")
df_filter = df["Modell"] == "Kothenplane für Hochkothe (S45/59)"
labels = list(df[df_filter]["Asset Tag"])
urls = list(df[df_filter]["URL"])
#labels = ["#00001", "#00002", "#00003", "#00004", "#00005", "#00006", "#00007", "#00008", "#00009", "#00010"]
OUTDIR    = Path("Schilder/Kothenplane für Hochkothe")
os.makedirs(OUTDIR, exist_ok=True)

for label,url in zip(labels, urls):
    plate, text = make_sign(label)
    m = Mesher()
    plate_mesh = make_mesh(m, plate, Color("white"))
    text_mesh  = make_mesh(m, text,  Color("black"))
    comp = add_assembly(m, plate_mesh, text_mesh)

    safe = re.sub(r"[^0-9A-Za-z_-]", "", label)
    path = os.path.join(OUTDIR, f"{safe}.3mf")
    m.write(path)

    settings = MODEL_SETTINGS.format(
        obj_id=comp.GetResourceID(),
        plate_id=plate_mesh.GetResourceID(),
        text_id=text_mesh.GetResourceID(),
        name=safe,
    )
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("Metadata/model_settings.config", settings)
    print("wrote", safe)