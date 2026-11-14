"""Pasa una hoja de acordes .txt (editada a mano) a PDF, tal cual, en fuente monoespaciada.

Uso:  python txt_a_pdf.py "<hoja.txt>"      -> crea "<hoja>.pdf" al lado
La 1ra linea es el titulo; las lineas que empiezan con "[" o "==" van en negrita.
"""
import sys
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ruta = sys.argv[1]
lineas = open(ruta, encoding="utf-8").read().splitlines()
salida = ruta[:-4] + ".pdf"
ancho, alto = A4
c = canvas.Canvas(salida, pagesize=A4)
c.setTitle(lineas[0])
MARGEN, PASO = 40, 13.5
y = alto - 50


def texto(s):
    # las fuentes estandar del PDF son Latin-1
    return s.replace("—", "-").replace("–", "-").replace("→", "->").replace("…", "...")


for i, l in enumerate(lineas):
    if y < 45:
        c.showPage()
        y = alto - 50
    if i == 0:
        c.setFont("Helvetica-Bold", 17)
        c.drawString(MARGEN, y, texto(l))
        y -= 22
        continue
    negrita = l.startswith("[") or l.startswith("==")
    if negrita and y < 90:  # no dejar un titulo de seccion solo al pie
        c.showPage()
        y = alto - 50
    c.setFont("Courier-Bold" if negrita else "Courier", 9)
    c.drawString(MARGEN, y, texto(l))
    y -= PASO
c.save()
print("PDF:", salida)
