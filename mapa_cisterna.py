"""Mapa esquemático de la comuna de La Cisterna con sus cuadrantes.

IMPORTANTE: es un esquema referencial, no cartografía oficial. Los límites de la comuna
(Lo Ovalle al norte, Santa Rosa al oriente, Lo Espejo / Riquelme al sur y Autopista Central
al poniente) están dibujados de forma aproximada, y la división en 6 cuadrantes es una grilla
de 3 x 2 provisoria. Para usar los polígonos reales de cada cuadrante, edite CUADRANTES_POLIGONOS:
cada punto es (x, y) entre 0 y 1 dentro del recuadro del mapa (0,0 = arriba a la izquierda).
"""

# Orden de lectura: fila norte (1, 2, 3) y fila sur (4, 5, 6)
CUADRANTES_POLIGONOS = {
    "Cuadrante 1": [(0.00, 0.00), (0.34, 0.00), (0.33, 0.46), (0.02, 0.46)],
    "Cuadrante 2": [(0.34, 0.00), (0.67, 0.00), (0.66, 0.46), (0.33, 0.46)],
    "Cuadrante 3": [(0.67, 0.00), (1.00, 0.00), (0.98, 0.46), (0.66, 0.46)],
    "Cuadrante 4": [(0.02, 0.46), (0.33, 0.46), (0.34, 1.00), (0.06, 1.00)],
    "Cuadrante 5": [(0.33, 0.46), (0.66, 0.46), (0.67, 1.00), (0.34, 1.00)],
    "Cuadrante 6": [(0.66, 0.46), (0.98, 0.46), (0.94, 1.00), (0.67, 1.00)],
}

# Referencias viales: (texto, (x, y), líneas [(x1, y1, x2, y2)], anclaje del texto)
REFERENCIAS_LINEAS = [
    ("Av. Gran Avenida", (0.625, 0.08), [(0.64, 0.0, 0.64, 1.0)], "e"),
    ("Américo Vespucio", (0.02, 0.405), [(0.0, 0.36, 1.0, 0.36)], "w"),
    ("Av. El Parrón", (0.04, 0.655), [(0.03, 0.61, 0.97, 0.61)], "w"),
]

# Bordes de la comuna: (texto, posición)
REFERENCIAS_BORDES = [
    ("Lo Ovalle (norte · San Miguel)", (0.50, -0.06)),
    ("Av. Santa Rosa (oriente · San Ramón)", (1.04, 0.50)),
    ("Lo Espejo / Riquelme (sur · El Bosque)", (0.50, 1.07)),
    ("Autopista Central (poniente · Lo Espejo)", (-0.04, 0.50)),
]


def dibujar_mapa(canvas, resaltado=None, colores=None, ancho=None, alto=None):
    """Dibuja el mapa en un tk.Canvas. `resaltado` es el nombre del cuadrante activo."""
    c = {
        "fondo": "#FFFFFF", "borde": "#3F1D61", "cuad": "#EDE4F5", "cuad_sel": "#2E9E5B",
        "texto": "#3F1D61", "texto_sel": "#FFFFFF", "via": "#8E5BC0", "ref": "#6B6B7B",
    }
    if colores:
        c.update(colores)
    canvas.delete("all")
    ancho = ancho or int(canvas["width"])
    alto = alto or int(canvas["height"])
    mx, my = 150, 28  # márgenes para los textos de borde
    w, h = ancho - 2 * mx, alto - 2 * my

    def p(x, y):
        return mx + x * w, my + y * h

    for nombre, pts in CUADRANTES_POLIGONOS.items():
        activo = nombre == resaltado
        plano = [v for pt in pts for v in p(*pt)]
        canvas.create_polygon(
            plano, fill=c["cuad_sel"] if activo else c["cuad"],
            outline=c["borde"], width=2 if activo else 1,
        )
        cx = sum(pt[0] for pt in pts) / len(pts)
        cy = sum(pt[1] for pt in pts) / len(pts)
        x, y = p(cx, cy)
        canvas.create_text(
            x, y, text=nombre.replace("Cuadrante ", "C"),
            fill=c["texto_sel"] if activo else c["texto"],
            font=("Segoe UI", 16 if activo else 13, "bold"),
        )
    for texto, (tx, ty), lineas, ancla in REFERENCIAS_LINEAS:
        for x1, y1, x2, y2 in lineas:
            a, b = p(x1, y1), p(x2, y2)
            canvas.create_line(*a, *b, fill=c["via"], width=2, dash=(6, 3))
        x, y = p(tx, ty)
        canvas.create_text(x, y, text=texto, fill=c["via"], font=("Segoe UI", 8, "italic"), anchor=ancla)
    for texto, (tx, ty) in REFERENCIAS_BORDES:
        x, y = p(tx, ty)
        ancla = "e" if tx < 0 else "w" if tx > 1 else "center"
        canvas.create_text(x, y, text=texto, fill=c["ref"], font=("Segoe UI", 8), anchor=ancla)
    canvas.create_text(
        ancho - 6, alto - 4, anchor="se", fill=c["ref"], font=("Segoe UI", 7),
        text="Esquema referencial · no es cartografía oficial",
    )
