# Agente telefónico — Arquitectura (fases 1–4)

Estado: **fases 1 a 4 implementadas** (auditoría, diseño, integración con pedidos, agente + simulador).
Pendiente: telefonía real (fase 5), aviso en vivo a cocina (6), panel de monitoreo (7), despliegue 24/7 (8).

## Decisiones

| Tema | Decisión | Motivo |
|---|---|---|
| Pedido sin mesa | `Orden.mesa` pasa a opcional y se añade `Orden.sucursal` | Un pedido telefónico no tiene mesa; el filtro multi-restaurante pasa a `sucursal__restaurante` |
| Origen | `Orden.ORIGEN_TELEFONO = "AGENTE_TELEFONICO"` | Distinguir el canal en cocina, caja y reportes |
| IA | Intérprete local determinista (`interprete.py`, `rapidfuzz`) | El usuario pidió no usar API key. Sin costo y sin red |
| Borrador | Se guarda en `Llamada` (base de datos), no en memoria | Sobrevive a reintentos y a varios workers de gunicorn |
| Idempotencia | `Llamada.identificador` único + `Llamada.orden` OneToOne con `select_for_update` | Un webhook repetido devuelve el mismo pedido |
| Impuestos | No existen en Smart Bite: el total es Σ cantidad × `Producto.precio` | No se inventan reglas comerciales |
| Modalidades | `PARA_LLEVAR` (recoger) y `EN_RESTAURANTE`; **sin domicilio** | Son las que soporta `Orden.tipo_consumo` |
| Pago | Sin cambios: "no pagado" = la orden no tiene `Pago` | Pago y preparación ya están separados |
| Stock | El agente rechaza productos cuya receta no tiene insumos (`AGENTE_VALIDAR_STOCK`) | "Agotado" real, desde inventario |

## Flujo de una llamada

```text
iniciar_llamada(sucursal, identificador)  ── get_or_create (idempotente)
        │
Agente.iniciar()  → saludo + aviso de tratamiento de datos (o "no recibimos pedidos" si la línea está apagada)
        │
Agente.procesar(texto)  (un turno por cada frase reconocida)
        │  interpretar(texto) → Intencion  ──►  Herramientas (consultas y borrador en la BD)
        ▼
 PEDIDO ──"eso es todo"──► DATOS_REGISTRADOS? ─► NOMBRE ─► TELEFONO? ─► MODALIDAD ─► CONFIRMACION
   ▲                                                                                     │
   └──────────── cliente cambia algo / dice "no" (resumen_leido = False) ◄───────────────┤
                                                                                         │ "sí" explícito
                                                              confirmar_pedido(True) ────┘
                                                                     │ transaction.atomic + select_for_update
                                                                     ▼
                                              operativo.services.crear_orden → Orden PENDIENTE (cocina la ve)
                                                                     │
                                              notificar_cocina(orden) → señal pedido_telefonico_registrado
```

Las intenciones globales (pedir un operador, cancelar, consultar el estado, silencio) se atienden en cualquier fase.

## Herramientas (`herramientas.py`)

Todas reciben y devuelven datos estructurados, filtran por la sucursal de la llamada y nunca ejecutan SQL libre.

| Herramienta | Entrada | Salida |
|---|---|---|
| `consultar_menu(categoria=None)` | nombre de categoría opcional | lista de productos disponibles |
| `buscar_producto(nombre)` | texto | `ENCONTRADO` / `AMBIGUO` (opciones) / `NO_ENCONTRADO` |
| `consultar_disponibilidad(producto_id, cantidad)` | id, cantidad | `{disponible, motivo: NO_EXISTE·NO_DISPONIBLE·SIN_STOCK}` |
| `consultar_cliente(telefono)` | teléfono (compara los últimos 10 dígitos) | `{id, nombre, telefono}` o `None` |
| `crear_cliente(datos)` | `{nombre, telefono}` | `Cliente` del restaurante |
| `agregar_producto_borrador(id, cantidad)` | | `{ok, cantidad}` o `{ok: False, error}` |
| `modificar_producto_borrador(id, cantidad)` | | igual; `NO_EN_PEDIDO` si no estaba |
| `eliminar_producto_borrador(id)` | | `{ok}` |
| `calcular_total_pedido()` | | líneas, subtotal, impuestos, cargos y total desde la BD |
| `confirmar_pedido(confirmacion_cliente)` | debe ser exactamente `True` | `{ok, pedido_id, duplicado, aviso_cocina}` o error |
| `consultar_estado_pedido(pedido_id)` | id | solo si el pedido es del mismo teléfono |
| `cancelar_borrador_pedido()` | | `{ok}` |

`confirmar_pedido` exige: borrador con productos, resumen leído al cliente después del último cambio,
nombre y modalidad. Los precios se copian de `Producto.precio` dentro de la transacción.

## Archivos

```text
agente_telefonico/
  models.py          LineaTelefonica (número → sucursal, interruptor, número de transferencia),
                     Llamada (estado, fase, borrador, idempotencia), TurnoLlamada (transcripción)
  texto.py           normalización, números en español, enmascarado de tarjetas
  interprete.py      texto → Intencion (reglas + coincidencia difusa de productos)
  herramientas.py    contratos de negocio (tabla anterior)
  conversacion.py    Agente: máquina de estados y redacción de respuestas
  notificaciones.py  notificar_cocina → señal Django (punto de extensión para la fase 6)
  views.py, urls.py  simulador en el navegador (/agente/simulador/)
  management/commands/purgar_conversaciones.py   política de retención
operativo/services.py  crear_orden(): creación transaccional reutilizable
operativo/migrations/0009, 0010  mesa opcional, sucursal y relleno de sucursal desde la mesa
```

Cambios en código existente: rutas de filtrado `mesa__sucursal__restaurante` → `sucursal__restaurante`
(caja, cocina, operativo, reportes); plantillas muestran `orden.ubicacion` en vez de `Mesa N`;
`CrearOrdenForm` sigue exigiendo mesa al mesero.

## Variables de entorno

| Variable | Defecto | Uso |
|---|---|---|
| `AGENTE_MAX_SILENCIOS` | 3 | silencios seguidos antes de colgar |
| `AGENTE_MAX_TURNOS` | 60 | límite de turnos por llamada |
| `AGENTE_VALIDAR_STOCK` | true | rechazar productos sin insumos |
| `AGENTE_RETENCION_DIAS` | 30 | días que se guardan las transcripciones |

## Simulador (modo demostración)

1. `python manage.py runserver` y entrar como ADMINISTRADOR.
2. Menú lateral → **Agente telefónico** (`/agente/simulador/`).
3. Elegir sucursal y, si quieres, un número "que llama" (para probar clientes registrados).
4. **Llamar**. En Chrome/Edge se usa el micrófono (`SpeechRecognition`, es-CO) y la voz del navegador
   (`speechSynthesis`, prefiere es-CO → es-419 → es-MX). En otros navegadores, escribir en la caja.
5. Ocho segundos sin hablar se envían como silencio. Con «Permitir interrumpir» la voz del agente se corta
   cuando hablas (usa audífonos para que no se escuche a sí mismo).

El reconocimiento de voz de Chrome envía el audio a los servidores de Google: no es "local" en ese sentido.

## Privacidad (Ley 1581 de 2012)

- El saludo informa que es un asistente virtual y que la conversación se guarda solo para gestionar el pedido.
- Las transcripciones enmascaran secuencias tipo tarjeta (13–19 dígitos) antes de guardarse.
- `python manage.py purgar_conversaciones [--dias N]` borra transcripciones antiguas (programarlo a diario).
- El agente no pide ni procesa pagos.
- Pendiente para la fase 5: si se graban llamadas en Twilio, pedir consentimiento explícito y definir dónde se guardan.

## Pruebas

`DATABASE_URL=sqlite:///... python manage.py test agente_telefonico` — 37 pruebas con la telefonía y el
proveedor de IA simulados (no hay red). Cubren los 15 escenarios obligatorios:

| # | Escenario | Prueba |
|---|---|---|
| 1 | Pedido correcto | `test_flujo_completo_registra_la_orden_y_la_envia_a_cocina` |
| 2 | Producto inexistente | `test_producto_inexistente_no_se_inventa` |
| 3 | Sin disponibilidad | `test_producto_sin_disponibilidad` |
| 4 | Modificar cantidades | `test_modificar_cantidades` |
| 5 | Eliminar producto | `test_eliminar_producto` |
| 6 | Cancelar antes de confirmar | `test_cancelar_antes_de_confirmar` |
| 7 | Cliente no responde | `test_cliente_no_responde` |
| 8 | Cliente interrumpe | `test_cliente_interrumpe_la_confirmacion` (a nivel de conversación; la voz se corta en el navegador) |
| 9 | Se cae la conexión | `test_se_pierde_la_conexion` |
| 10 | Falla la base de datos | `test_falla_la_base_de_datos`, `test_falla_la_base_al_confirmar_no_anuncia_el_pedido` |
| 11 | Webhook repetido | `test_webhook_repetido_no_duplica` |
| 12 | Falla el aviso a cocina | `test_pedido_registrado_pero_falla_cocina` |
| 13 | Dos llamadas simultáneas | `test_dos_clientes_a_la_vez` (turnos intercalados; no son hilos reales) |
| 14 | Manipular el precio por voz | `test_intento_de_manipular_el_precio` |
| 15 | Estado de un pedido | `test_consultar_estado_de_un_pedido` |

## Limitaciones conocidas

- El intérprete se basa en reglas: entiende bien pedidos, cantidades, precios y confirmaciones, pero frases
  muy libres pueden no entenderse ("No te entendí bien…"). La interfaz de `Agente` permite cambiarlo por un LLM
  más adelante sin tocar las herramientas.
- La telefonía real **no está implementada ni probada**. Plan de la fase 5: Twilio `<Gather input="speech">` por
  webhooks HTTP (compatible con gunicorn/WSGI), con validación de firma `X-Twilio-Signature`. Antes hay que
  verificar disponibilidad y precio de números colombianos.
- La pantalla de cocina todavía no se actualiza sola: hay que recargarla (fase 6).
