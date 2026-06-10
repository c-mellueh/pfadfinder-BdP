from build123d import BuildPart,extrude,Locations,Cylinder,Mode,Vector,Text,FontStyle,Align
from build123d import Mesher, Color,BuildSketch,Plane,RectangleRounded
from build123d.build_enums import MeshType
import pandas as pd
import copy as _copy, ctypes, os, re
import lib3mf   # je nach Install heißt das Paket lib3mf
import segno
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
PLATE_W, PLATE_H, PLATE_T = 100, 35, 1.2    # mm
TEXT_T    = 0.4                           # raised text height
FONT      = "Nimbus Mono PS"              # monospace, plain zeros
FONT_SIZE = 8
FONT_SIZE_NUMBER = 14
HOLE_D    = 6.0                           # hanging hole diameter
HOLDE_DISTANCE = 3.
CORNER_R  = 6.0
QR_SIZE   = 33.0                          # QR side length, mm
QR_VERSION = 3                            # 29x29 modules, fits 36-byte URLs at error level M
QR_EDGE_MARGIN = 3.5                      # from right plate edge, keeps quiet zone clear of corner rounding
QR_TEXT_GAP = 1.5                         # white gap between text and QR

MODEL_TYPE_TEXT = "Hochkothe\n(S45/59)"
FILTER_TEXT = "Kothenplane für Hochkothe (S45/59)"



def make_mesh(mesher, shape, color: Color, extra=None):
    mesh_3mf = mesher.model.AddMeshObject()
    verts, tris = Mesher._mesh_shape(_copy.deepcopy(shape), 0.02, 0.2)
    verts_3mf, tris_3mf = Mesher._create_3mf_mesh(verts, tris)
    if extra is not None:  # pre-triangulated geometry, e.g. the QR boxes
        xverts, xtris = extra
        off = len(verts_3mf)
        c_f3, c_u3 = ctypes.c_float * 3, ctypes.c_uint * 3
        verts_3mf += [lib3mf.Position(c_f3(*v)) for v in xverts]
        tris_3mf += [lib3mf.Triangle(c_u3(a + off, b + off, c + off)) for a, b, c in xtris]
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


def qr_matrix(url: str):
    qr = segno.make(url, error="m", version=QR_VERSION, micro=False)
    return [[bool(v) for v in row] for row in qr.matrix]


def qr_rects(matrix, center_x: float, center_y: float, size: float):
    """Merge horizontal runs of dark modules into (cx, cy, w, h) rectangles."""
    n = len(matrix)
    module = size / n
    x0 = center_x - size / 2
    y_top = center_y + size / 2
    rects = []
    for r, row in enumerate(matrix):
        c = 0
        while c < n:
            if not row[c]:
                c += 1
                continue
            run = c
            while run + 1 < n and row[run + 1]:
                run += 1
            w = (run - c + 1) * module
            cy = y_top - (r + 0.5) * module
            rects.append((x0 + c * module + w / 2, cy, w, module))
            c = run + 1
    return rects


def qr_boxes_mesh(rect_groups):
    """Triangulate (rects, z0, z1) groups into raw mesh data.

    OCCT needs ~16 s to fuse the ~220 QR rectangles per face; emitting the
    boxes directly as triangles is instant. A tiny xy overlap keeps adjacent
    rows fused when the slicer unions the shells.
    """
    eps = 0.02
    verts, tris = [], []
    # per-box faces with outward winding
    faces = [
        (0, 2, 1), (0, 3, 2),  # bottom (-z)
        (4, 5, 6), (4, 6, 7),  # top (+z)
        (0, 1, 5), (0, 5, 4),  # -y
        (1, 2, 6), (1, 6, 5),  # +x
        (2, 3, 7), (2, 7, 6),  # +y
        (3, 0, 4), (3, 4, 7),  # -x
    ]
    for rects, z0, z1 in rect_groups:
        for cx, cy, w, h in rects:
            x0, x1 = cx - (w + eps) / 2, cx + (w + eps) / 2
            y0, y1 = cy - (h + eps) / 2, cy + (h + eps) / 2
            base = len(verts)
            verts += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                      (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            tris += [(base + a, base + b, base + c) for a, b, c in faces]
    return verts, tris


def make_sign(label: str, url: str, model_type):
    hole_r = HOLE_D / 2
    hole_x = -PLATE_W / 2 + hole_r + HOLDE_DISTANCE # 2 mm edge margin

    corner_r = min(CORNER_R, min(PLATE_W, PLATE_H) / 2 - 0.01)
    with BuildPart() as plate:
        with BuildSketch(Plane.XY.offset(-PLATE_T / 2)):
            RectangleRounded(PLATE_W, PLATE_H, corner_r)
        extrude(amount=PLATE_T)
        with Locations([(hole_x, 0, 0)]):
            Cylinder(radius=hole_r, height=PLATE_T + 1, mode=Mode.SUBTRACT)

    qr_center_x = PLATE_W / 2 - QR_EDGE_MARGIN - QR_SIZE / 2
    text_anchor_x = qr_center_x - QR_SIZE / 2 - QR_TEXT_GAP  # text ends left of the QR
    text_anchor_x_bottom = -text_anchor_x

    # QR as raw mesh boxes, no OCCT involved; the bottom copy is x-mirrored
    # about its center so it reads correctly from below (like the text)
    rects = qr_rects(qr_matrix(url), qr_center_x, 0, QR_SIZE)
    rects_bottom = [(2 * qr_center_x - cx, cy, w, h) for cx, cy, w, h in rects]
    qr_data = qr_boxes_mesh([
        (rects, PLATE_T / 2 - TEXT_T, PLATE_T / 2),
        (rects_bottom, -PLATE_T / 2, -PLATE_T / 2 + TEXT_T),
    ])

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
                Text(label, font=FONT, font_size=FONT_SIZE_NUMBER,
                     font_style=FontStyle.BOLD,
                     align=(Align.MAX, Align.CENTER))
        extrude(amount=-TEXT_T)
        #Bottom Text
        with BuildSketch(bottom_plane):
            with Locations([(text_anchor_x_bottom, 0)]):
                Text(model_type, font=FONT, font_size=FONT_SIZE,
                     font_style=FontStyle.BOLD,
                     align=(Align.MIN, Align.CENTER))
        extrude(amount=-TEXT_T)
    return plate.part, text.part, qr_data



if __name__ == "__main__":
    df = pd.read_csv("Daten.csv")
    df_filter = df["Modell"] == FILTER_TEXT
    labels = list(df[df_filter]["Asset Tag"])
    urls = list(df[df_filter]["URL"])
    #labels = ["#00001", "#00002", "#00003", "#00004", "#00005", "#00006", "#00007", "#00008", "#00009", "#00010"]
    OUTDIR    = Path("Schilder/Kothenplane für Hochkothe")
    os.makedirs(OUTDIR, exist_ok=True)

    for label,url in zip(labels, urls):
        print("processing", label)
        plate, text, qr_data = make_sign(label, url,MODEL_TYPE_TEXT)
        m = Mesher()
        plate_mesh = make_mesh(m, plate, Color("white"))
        text_mesh  = make_mesh(m, text,  Color("black"), extra=qr_data)
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