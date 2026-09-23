# ADR 0002 — Generación del código único de insumo (RF-1, RF-37)

> Estado: aprobada 2026-09-23

## Contexto
RF-1 exige que cada insumo tenga un código único autogenerado; RF-37 exige
que ese código sea inmutable una vez asignado. Ninguno de los `CU-INV-01`
originales especifica el formato — es una decisión estructural (constitución,
principio 9).

## Opciones
- **A. UUID**: único garantizado, sin coordinación entre sucursales, pero
  ilegible y no memorable para un Jefe de Almacén en un mostrador.
- **B. Secuencial global simple** (1, 2, 3…): legible, pero no aporta
  contexto — indistinguible de un ID interno cualquiera.
- **C. Prefijo de categoría + secuencial por sucursal** (ej. `LAC-00001`):
  legible, da contexto de categoría de un vistazo, y el secuencial por
  sucursal evita que dos sucursales compitan por el mismo número.

## Decisión
Opción C. Formato `<3 letras mayúsculas de la categoría>-<secuencial de 5
dígitos, por sucursal>` (ej. `LAC-00001`, `CAR-00002`). Se genera con un
trigger `BEFORE INSERT` en `item_inventario` que calcula el siguiente
secuencial para esa combinación de categoría y sucursal.

## Consecuencias
- El prefijo se fija en el momento de crear el insumo, tomando el nombre de
  la categoría **en ese instante** — si la categoría se renombra después,
  los códigos ya asignados no cambian (esto es lo que permite cumplir RF-37,
  inmutabilidad, sin depender de que el nombre de la categoría no cambie
  nunca).
- Dos categorías cuyas 3 primeras letras coincidan (ej. "Cárnicos" y
  "Carbohidratos") comparten prefijo `CAR` — se acepta como riesgo menor;
  si ocurre en la práctica, se resuelve a mano en el momento (cambiar el
  nombre de una categoría) sin necesidad de cambiar el mecanismo.
