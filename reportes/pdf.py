from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.templatetags.core_extras import moneda

ACENTO = colors.HexColor("#e8843f")
TINTA = colors.HexColor("#1f2328")
GRIS = colors.HexColor("#6b7280")
FONDO = colors.HexColor("#f6f4f1")
LINEA = colors.HexColor("#e5e1dc")

_base = getSampleStyleSheet()
TITULO = ParagraphStyle("titulo", parent=_base["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=TINTA, alignment=0, spaceAfter=4)
SUBTITULO = ParagraphStyle("subtitulo", parent=_base["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=GRIS)
SECCION = ParagraphStyle("seccion", parent=_base["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=TINTA, spaceBefore=14, spaceAfter=6)
TEXTO = ParagraphStyle("texto", parent=_base["Normal"], fontName="Helvetica", fontSize=9.5, leading=12, textColor=TINTA)
VACIO = ParagraphStyle("vacio", parent=TEXTO, textColor=GRIS)


def _fecha(valor):
    return valor.strftime("%d/%m/%Y")


def _tabla(encabezados, filas, anchos, columnas_numericas=()):
    datos = [encabezados] + filas
    tabla = Table(datos, colWidths=anchos, repeatRows=1)
    estilo = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), TINTA),
        ("TEXTCOLOR", (0, 1), (-1, -1), TINTA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FONDO]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for columna in columnas_numericas:
        estilo.append(("ALIGN", (columna, 0), (columna, -1), "RIGHT"))
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _indicadores(datos, ancho):
    celdas = [
        ("Ventas", moneda(datos["ventas"])),
        ("Propinas", moneda(datos["propinas"])),
        ("Órdenes", str(datos["ordenes"])),
        ("Ticket promedio", moneda(datos["ticket_promedio"])),
    ]
    etiqueta = ParagraphStyle("etiqueta", parent=TEXTO, fontSize=8.5, textColor=GRIS)
    valor = ParagraphStyle("valor", parent=TEXTO, fontName="Helvetica-Bold", fontSize=15, leading=19)
    fila = [[Paragraph(nombre, etiqueta), Paragraph(cifra, valor)] for nombre, cifra in celdas]
    tabla = Table([fila], colWidths=[ancho / 4] * 4)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FONDO),
        ("LINEABOVE", (0, 0), (-1, 0), 2, ACENTO),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return tabla


def _pie_de_pagina(lienzo, documento):
    lienzo.saveState()
    lienzo.setFont("Helvetica", 8)
    lienzo.setFillColor(GRIS)
    lienzo.drawString(documento.leftMargin, 1.2 * cm, "Smart Bite · Reporte de ventas")
    lienzo.drawRightString(documento.pagesize[0] - documento.rightMargin, 1.2 * cm, f"Página {lienzo.getPageNumber()}")
    lienzo.restoreState()


def generar_pdf(datos):
    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm,
        title="Reporte de ventas — Smart Bite", author="Smart Bite",
    )
    ancho = documento.width
    restaurante = escape(datos["restaurante"].nombre) if datos["restaurante"] else "Todos los restaurantes"

    historia = [
        Paragraph(f"Reporte de ventas · {restaurante}", TITULO),
        Paragraph(
            f"Periodo: {_fecha(datos['desde'])} a {_fecha(datos['hasta'])} · "
            f"Generado el {datos['generado_en'].strftime('%d/%m/%Y %H:%M')} por {escape(datos['generado_por'])}",
            SUBTITULO,
        ),
        Spacer(1, 12),
        _indicadores(datos, ancho),
        Spacer(1, 4),
        Paragraph(
            f"{datos['numero_pagos']} pagos aprobados en {datos['ordenes_cobradas']} órdenes cobradas. "
            "Las ventas no incluyen propinas.",
            VACIO,
        ),
    ]

    historia.append(Paragraph("Ventas por método de pago", SECCION))
    if datos["ventas_por_metodo"]:
        historia.append(_tabla(
            ["Método", "Pagos", "Total"],
            [[f["metodo_pago__nombre"], str(f["pagos"]), moneda(f["total"])] for f in datos["ventas_por_metodo"]],
            [ancho * 0.56, ancho * 0.18, ancho * 0.26], columnas_numericas=(1, 2),
        ))
    else:
        historia.append(Paragraph("No hubo pagos aprobados en este periodo.", VACIO))

    historia.append(Paragraph("Ventas por día", SECCION))
    if datos["ventas_por_dia"]:
        historia.append(_tabla(
            ["Día", "Pagos", "Total"],
            [[_fecha(f["dia"]), str(f["pagos"]), moneda(f["total"])] for f in datos["ventas_por_dia"]],
            [ancho * 0.56, ancho * 0.18, ancho * 0.26], columnas_numericas=(1, 2),
        ))
    else:
        historia.append(Paragraph("No hubo ventas en este periodo.", VACIO))

    historia.append(Paragraph("Órdenes por estado", SECCION))
    historia.append(_tabla(
        ["Estado", "Órdenes"],
        [[f["nombre"], str(f["cantidad"])] for f in datos["ordenes_por_estado"]],
        [ancho * 0.74, ancho * 0.26], columnas_numericas=(1,),
    ))

    historia.append(Paragraph("Platillos más vendidos", SECCION))
    if datos["productos_mas_vendidos"]:
        historia.append(_tabla(
            ["Platillo", "Unidades", "Total"],
            [[Paragraph(escape(f["producto__nombre"]), TEXTO), str(f["unidades"]), moneda(f["total"])] for f in datos["productos_mas_vendidos"]],
            [ancho * 0.56, ancho * 0.18, ancho * 0.26], columnas_numericas=(1, 2),
        ))
    else:
        historia.append(Paragraph("No se vendieron platillos en este periodo.", VACIO))

    historia.append(Paragraph("Inventario con stock bajo (hoy)", SECCION))
    if datos["stock_bajo"]:
        historia.append(_tabla(
            ["Insumo", "Sucursal", "Stock", "Mínimo"],
            [
                [Paragraph(escape(i.nombre), TEXTO), Paragraph(escape(i.sucursal.nombre), TEXTO), f"{i.stock_actual} {i.unidad_medida}", str(i.stock_minimo)]
                for i in datos["stock_bajo"]
            ],
            [ancho * 0.36, ancho * 0.28, ancho * 0.2, ancho * 0.16], columnas_numericas=(2, 3),
        ))
    else:
        historia.append(Paragraph("Ningún insumo está por debajo de su mínimo.", VACIO))

    documento.build(historia, onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)
    return salida.getvalue()
