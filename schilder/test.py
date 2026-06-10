import marimo

__generated_with = "0.23.9"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import pandas as pd


    return mo, pd


@app.cell
def _(pd):
    df = pd.read_csv("Daten.csv")
    df
    return (df,)


@app.cell
def _(df):
    df['Modell'].value_counts()
    return


@app.cell
def _(df):
    df[df["Modell"] == "Kothenplane für Hochkothe (S45/59)"]["Asset Tag"]
    return


@app.cell
def _(mo):
    from build123d import BuildPart,extrude,Locations,Cylinder,Mode,Vector,Text,FontStyle,Align
    from build123d import Mesher, Color,BuildSketch,Plane,RectangleRounded
    from build123d.build_enums import MeshType
    import marimo_cad as cad

    size = mo.ui.slider(10, 50, value=20, label="Size")
    size
    return (
        Align,
        BuildPart,
        BuildSketch,
        Color,
        Cylinder,
        FontStyle,
        Locations,
        MeshType,
        Mesher,
        Mode,
        Plane,
        RectangleRounded,
        Text,
        Vector,
        cad,
        extrude,
    )


@app.cell
def _():
    PLATE_W, PLATE_H, PLATE_T = 40, 12, 0.5    # mm
    TEXT_T    = 0.2                           # raised text height
    FONT      = "Nimbus Mono PS"              # monospace, plain zeros
    FONT_SIZE = 7
    HOLE_D    = 6.0                           # hanging hole diameter
    CORNER_R  = 6.0   
    return CORNER_R, FONT, FONT_SIZE, HOLE_D, PLATE_H, PLATE_T, PLATE_W, TEXT_T


@app.cell
def _(
    Align,
    BuildPart,
    BuildSketch,
    CORNER_R,
    Color,
    Cylinder,
    FONT,
    FONT_SIZE,
    FontStyle,
    HOLE_D,
    Locations,
    MeshType,
    Mesher,
    Mode,
    PLATE_H,
    PLATE_T,
    PLATE_W,
    Plane,
    RectangleRounded,
    TEXT_T,
    Text,
    Vector,
    extrude,
):
    import copy as _copy, os, re

    def make_mesh(mesher, shape, color: Color):
        """Mesh a shape into a single 3MF mesh object with color. Does not add a build item."""
        mesh_3mf = mesher.model.AddMeshObject()
        verts, tris = Mesher._mesh_shape(_copy.deepcopy(shape), 0.001, 0.1)
        verts_3mf, tris_3mf = Mesher._create_3mf_mesh(verts, tris)
        mesh_3mf.SetGeometry(verts_3mf, tris_3mf)
        mesh_3mf.SetType(Mesher._map_b3d_mesh_type_3mf[MeshType.MODEL])
        grp = mesher.model.AddColorGroup()
        color_id = grp.AddColor(mesher.wrapper.FloatRGBAToColor(*tuple(color)))
        mesh_3mf.SetObjectLevelProperty(grp.GetResourceID(), color_id)
        mesher.meshes.append(mesh_3mf)
        return mesh_3mf


    def add_assembly(mesher, *meshes):
        """Add each mesh as its own build item (preserves per-mesh colour in Orca).
        Group the objects in Orca after import: select all → Ctrl+G."""
        for mesh in meshes:
            mesher.model.AddBuildItem(mesh, mesher.wrapper.GetIdentityTransform())


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



    return add_assembly, make_mesh, make_sign


@app.cell
def _(Color, Mesher, add_assembly, cad, make_mesh, make_sign, mo):
    viewer = cad.Viewer()
    plate, text = make_sign("#00001")
    m = Mesher()
    plate_mesh = make_mesh(m, plate, Color("white"))
    text_mesh  = make_mesh(m, text,  Color("black"))
    add_assembly(m, plate_mesh, text_mesh)
    viewer.render([plate,text])
    mo.vstack([viewer])
    return


if __name__ == "__main__":
    app.run()
