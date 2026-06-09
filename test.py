import marimo

__generated_with = "0.23.9"
app = marimo.App()


@app.cell
def _():
    import marimo as mo
    import pandas as pd

    return (pd,)


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


if __name__ == "__main__":
    app.run()
