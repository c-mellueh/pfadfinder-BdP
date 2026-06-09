from build123d import *
from build123d import Mesher, Color
from build123d.build_enums import MeshType
import pandas as pd
import copy as _copy, os, re

# --- parameters ---
PLATE_W, PLATE_H, PLATE_T = 40, 12, 1    # mm
TEXT_T    = 0.4                           # raised text height
FONT      = "Nimbus Mono PS"              # monospace, plain zeros
FONT_SIZE = 7
HOLE_D    = 6.0                           # hanging hole diameter
CORNER_R  = 6.0                           # corner fillet radius



def _add_merged(mesher, shape, color: Color):
    """Add shape as a single 3MF mesh object, even when shape is a Compound.

    build123d's Mesher.add_shape flattens Compounds into one object per solid.
    Here we pass the whole shape directly to _mesh_shape, which walks all faces
    regardless of nesting, producing one combined mesh.
    """
    mesh_3mf = mesher.model.AddMeshObject()
    verts, tris = Mesher._mesh_shape(_copy.deepcopy(shape), 0.001, 0.1)
    verts_3mf, tris_3mf = Mesher._create_3mf_mesh(verts, tris)
    mesh_3mf.SetGeometry(verts_3mf, tris_3mf)
    mesh_3mf.SetType(Mesher._map_b3d_mesh_type_3mf[MeshType.MODEL])
    grp = mesher.model.AddColorGroup()
    color_id = grp.AddColor(mesher.wrapper.FloatRGBAToColor(*tuple(color)))
    mesh_3mf.SetObjectLevelProperty(grp.GetResourceID(), color_id)
    mesher.meshes.append(mesh_3mf)
    mesher.model.AddBuildItem(mesh_3mf, mesher.wrapper.GetIdentityTransform())
    components = mesher.model.AddComponentsObject()
    components.AddComponent(mesh_3mf, mesher.wrapper.GetIdentityTransform())


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
    # Bottom plane mirrors X so text is readable when the tag is flipped over
    bottom_plane = Plane(
        origin=Vector(0, 0, -PLATE_T / 2),
        x_dir=Vector(-1, 0, 0),
        z_dir=Vector(0, 0, 1),
    )
    with BuildPart() as text:
        with BuildSketch(Plane.XY.offset(PLATE_T / 2)):
            with Locations([(text_anchor_x, 0)]):
                Text(label, font=FONT, font_size=FONT_SIZE,
                     font_style=FontStyle.BOLD,
                     align=(Align.MAX, Align.CENTER))
        extrude(amount=-TEXT_T)
        with BuildSketch(bottom_plane):
            with Locations([(text_anchor_x, 0)]):
                Text(label, font=FONT, font_size=FONT_SIZE,
                     font_style=FontStyle.BOLD,
                     align=(Align.MAX, Align.CENTER))
        extrude(amount=TEXT_T)
    return plate.part, text.part


df = pd.read_csv("Daten.csv")
labels = sorted(list(df[df["Modell"] == "Kothenplane für Hochkothe (S45/59)"]["Asset Tag"]))

OUTDIR    = "Kothenplane für Hochkothe"
os.makedirs(OUTDIR, exist_ok=True)

for label in labels:
    plate, text = make_sign(label)
    m = Mesher()
    _add_merged(m, plate, Color("white"))
    _add_merged(m, text,  Color("black"))
    safe = re.sub(r"[^0-9A-Za-z_-]", "", label)        # "#00001" -> "00001"
    m.write(os.path.join(OUTDIR, f"{safe}.3mf"))
    print("wrote", safe)
