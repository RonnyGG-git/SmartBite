"""07 — Objetos: los datos justo después del escenario del diagrama de
secuencia (salida de 7 de leche con stock 10 y mínimo 5). Los valores
siguen las reglas reales del esquema: código generado LAC-00001 (prefijo de
la categoría + secuencial), stock encadenado en el kardex y cantidad
sugerida = mínimo − stock.

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1, 9.8.4):
- Todo enlace es una instancia de una asociación: línea sólida. Antes las
  referencias a otros módulos eran flechas punteadas (dependencias).
- Objetos de otros módulos con el nombre calificado de su clase
  (Cuentas::Usuario), no con «externo».
- Los slots corresponden a atributos del diagrama de clases: sucursal_id y
  usuario_id no son atributos (son asociaciones), así que van como enlaces.
  Faltaban los enlaces de 'entrada' y 'cambio' con el usuario.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Objetos - Inventario", 1240, 1100)
d.titulo("Diagrama de objetos — Inventario (Smart Bite)",
         "Foto de los datos justo después de la salida del diagrama de secuencia: Leche entera con stock 10 y "
         "mínimo 5, salida de 7")

O = dict(objeto=True, tam=12)
X1, X2, X3 = 60, 450, 860
lacteos = d.clase("lacteos : CategoriaInsumo", X2 + 40, 110, 260, ['id = 1', 'nombre = "Lácteos"'], **O)
sucursal = d.clase_simple("sucursal1 : Restaurantes::Sucursal", X3, 120, 300, 50, objeto=True)

Y2 = 320
leche = d.clase("leche : ItemInventario", X2, Y2, 340, [
    'id = 12', 'codigo_unico = "LAC-00001"', 'nombre = "Leche entera"', 'unidad_medida = "L"',
    'stock_actual = 3.000', 'stock_minimo = 5.000', 'costo_unitario = 4200.00', 'activo = true'], **O)
alto_leche = d.ultima_altura
entrada = d.clase("entrada : MovimientoInventario", X1, Y2, 330, [
    'id = 41', 'tipo = "ENTRADA"', 'cantidad_movimiento = 10.000', 'stock_anterior = 0.000',
    'stock_nuevo = 10.000', 'motivo = "Stock inicial"', 'requiere_aprobacion = false'], **O)
alto_entrada = d.ultima_altura
cambio = d.clase("cambio : ItemInventarioHistorial", X3, Y2, 320, [
    'id = 18', 'campo = "stock_minimo"', 'valor_anterior = null', 'valor_nuevo = "5.000"'], **O)
alto_cambio = d.ultima_altura

Y3 = Y2 + max(alto_leche, alto_entrada) + 90
salida_ = d.clase("salida : MovimientoInventario", X1, Y3, 330, [
    'id = 42', 'tipo = "SALIDA"', 'cantidad_movimiento = 7.000', 'stock_anterior = 10.000',
    'stock_nuevo = 3.000', 'motivo = "Consumo de cocina"', 'requiere_aprobacion = false'], color=AMARILLO, **O)
alto_salida = d.ultima_altura
solicitud = d.clase("solicitud : SolicitudReabastecimiento", X2, Y3, 340, [
    'id = 5', 'cantidad_sugerida = 2.000', 'estado = "PENDIENTE"'], color=VERDE, **O)
JEFE_Y = Y3 + 40
jefe = d.clase_simple("jefe : Cuentas::Usuario", X3 + 40, JEFE_Y, 240, 50, objeto=True)

L = LINK + "edgeStyle=orthogonalEdgeStyle;rounded=0;"
d.arista(leche, lacteos, L + f"exitX={(X2 + 170 - X2) / 340:.4f};exitY=0;entryX=0.5;entryY=1;")
d.arista(leche, sucursal, L + "exitX=0.9;exitY=0;entryX=0;entryY=0.5;", puntos=[(X2 + 306, 145)])
Y_ENL = Y2 + 42                     # altura común de los enlaces horizontales con leche
d.arista(entrada, leche, L + f"exitX=1;exitY={(Y_ENL - Y2) / alto_entrada:.4f};entryX=0;"
         f"entryY={(Y_ENL - Y2) / alto_leche:.4f};")
d.arista(cambio, leche, L + f"exitX=0;exitY={(Y_ENL - Y2) / alto_cambio:.4f};entryX=1;"
         f"entryY={(Y_ENL - Y2) / alto_leche:.4f};")
Y_SAL = Y2 + alto_leche - 14        # salida sube por el pasillo y entra a leche por la izquierda
d.arista(salida_, leche, L + f"exitX=1;exitY={25 / alto_salida:.4f};entryX=0;entryY={(Y_SAL - Y2) / alto_leche:.4f};",
         puntos=[(X2 - 30, Y3 + 25), (X2 - 30, Y_SAL)])
d.arista(solicitud, leche, L + "exitX=0.5;exitY=0;entryX=0.5;entryY=1;")

# Los tres registros los hizo el mismo usuario (usuario_id = 7)
d.arista(cambio, jefe, L + f"exitX={(X3 + 160 - X3) / 320:.4f};exitY=1;entryX=0.5;entryY=0;")
Y_BAJO1 = Y3 + alto_salida + 30
d.arista(salida_, jefe, L + "exitX=0.5;exitY=1;entryX=0.35;entryY=1;",
         puntos=[(X1 + 165, Y_BAJO1), (X3 + 40 + 84, Y_BAJO1)])
Y_BAJO2 = Y_BAJO1 + 28
d.arista(entrada, jefe, L + f"exitX=0;exitY={(Y_ENL + 40 - Y2) / alto_entrada:.4f};entryX=0.7;entryY=1;",
         puntos=[(X1 - 30, Y_ENL + 40), (X1 - 30, Y_BAJO2), (X3 + 40 + 168, Y_BAJO2)])
d.texto("usuario", X3 + 40 + 84 + 4, JEFE_Y + 54, 60, 16, tam=11, alin="left", color="#444444")
d.texto("usuario", X3 + 40 + 168 + 4, JEFE_Y + 54, 60, 16, tam=11, alin="left", color="#444444")
d.texto("usuario", X3 + 164, Y2 + alto_cambio + 6, 60, 16, tam=11, alin="left", color="#444444")

YN = Y_BAJO2 + 40
d.nota("Cómo se llegó acá: el insumo se creó con stock 0 y el código lo generó la base (LAC + secuencial por "
       "sucursal); después se configuró el mínimo en 5 (queda en el historial); una ENTRADA de 10 dejó stock 10; "
       "la SALIDA de 7 dejó stock 3, bajo el mínimo, y la base creó la solicitud por 5 − 3 = 2.",
       X1, YN, 1100, 56, tam=12)
d.nota("Línea sólida = enlace (instancia de una asociación del diagrama de clases). En amarillo, el movimiento del "
       "diagrama de secuencia; en verde, lo que la base creó en ese mismo paso. Los enlaces con sucursal1 y jefe "
       "existen como columnas (sucursal_id, usuario_id), todavía sin FK física.", X1, YN + 66, 1100, 56, tam=12)

d.alto = YN + 140
d.guardar(*salida("07-objetos-inventario"))
print("ok")
