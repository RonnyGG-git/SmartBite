# Constitución del Proyecto SmartBite

1. **Stack y Arquitectura:** Django 5.2 MVT, máximo 3 dependencias externas. Cada app representa un dominio de negocio acotado. Sin frameworks JS ni APIs REST.
2. **Especificaciones vs Código:** Toda modificación se basa en requerimientos documentados en `ordenes.txt` o validados por el usuario. No se asume funcionalidad no especificada.
3. **Separación de Responsabilidades:** Modelos = lógica de negocio y persistencia. Vistas = orquestación HTTP. Plantillas = presentación. No cruzar capas.
4. **Tests y Validación:** Toda app debe tener tests mínimos (models + views). Validaciones de seguridad según `VALIDACIONES.md`. Sin código sin cubrir.
5. **Persistencia e Integridad:** Transacciones atómicas en operaciones financieras. Relaciones ForeignKey con PROTECT/CASCADE apropiados. Datos auditables con `TimestampedModel`.
6. **Idioma:** Código, comentarios, mensajes de usuario, documentación y commits en español. Variables y funciones en español.