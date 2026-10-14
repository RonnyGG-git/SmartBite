"""10 — Despliegue: dónde corre hoy la app Django de Ronny (rama smartbite) y
cómo llega a la base. Fuente: smartbite/settings.py (DEBUG = True,
ALLOWED_HOSTS = [], DATABASE_URL leída del .env o, si no está, SQLite),
.env.example y la base smartbite_app creada en Neon. UML 2.5.1, cláusula 19.

- Nodos = cubos; «device» y «executionEnvironment» en inglés (19.4.4).
- Artefactos con icono de hoja dentro del nodo donde están desplegados
  (19.2.4); «file» del perfil estándar (22).
- Caminos de comunicación sólidos con el protocolo como estereotipo.
- Con ALLOWED_HOSTS vacío y DEBUG = True, Django solo atiende a localhost:
  el navegador corre en la misma computadora.
- Producción no está definida: no se dibuja un servidor que no existe.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Despliegue - Inventario", 1600, 800)
d.titulo("Diagrama de despliegue — Inventario (Smart Bite)",
         "Dónde corre hoy la app Django y cómo se conecta con la base de datos en Neon")

# --- Computadora de cada integrante
d.nodo("Computadora de desarrollo (cada integrante)", 40, 110, 900, 470, palabra_clave="device")
nav = d.nodo("Navegador web", 70, 215, 220, 100, palabra_clave="executionEnvironment", color=AZUL, tam=12,
             detalle="http://127.0.0.1:8000")
django = d.nodo("Python 3.14 + Django 5.2 (venv)", 380, 175, 530, 215, palabra_clave="executionEnvironment",
                color=AZUL, tam=12, detalle="manage.py runserver (servidor de desarrollo)")
d.artefacto("smartbite", 410, 265, 230, 84, detalle="código del repo: apps de\nDjango y sus migraciones")
d.artefacto("settings.py", 660, 265, 220, 84, palabra_clave="source", tam=12,
            detalle="usa DATABASE_URL si existe;\nsi no, db.sqlite3")
d.artefacto(".env", 380, 450, 250, 90, palabra_clave="file", color=GRIS,
            detalle="DATABASE_URL de Neon\n(no se sube al repo)")
d.artefacto("db.sqlite3", 660, 450, 250, 90, palabra_clave="file", color=GRIS,
            detalle="solo si no hay DATABASE_URL\n(no se sube al repo)")

# --- Neon
d.nodo("Neon (PostgreSQL gestionado en la nube)", 1080, 110, 480, 470)
pg = d.nodo("PostgreSQL — rama test-inventario-jose", 1110, 200, 420, 170, palabra_clave="executionEnvironment",
            color=VERDE, tam=12, detalle="base smartbite_app: las tablas de Django\n(inventario_iteminventario, …),\n"
                                         "creadas con manage.py migrate")

# --- Caminos de comunicación (línea sólida, como una asociación)
Y_HTTP = 265
d.flecha(290, Y_HTTP, 380, Y_HTTP, ASOCIACION)
d.texto("«HTTP»", 292, Y_HTTP - 22, 86, 18, tam=12, alin="center", color="#222222")
Y_PG = 300
d.flecha(910, Y_PG, 1110, Y_PG, ASOCIACION)
d.texto("«PostgreSQL/TLS»\nsslmode=require", 920, Y_PG - 40, 180, 36, tam=11, alin="center", color="#222222")
d.texto("{solo si el .env define\nDATABASE_URL}", 920, Y_PG + 6, 180, 34, tam=11, alin="center", color="#222222")

d.nota("Producción: no definida. Esta configuración es solo de desarrollo (DEBUG = True, ALLOWED_HOSTS vacío y la "
       "SECRET_KEY de ejemplo en settings.py). Dónde se aloja Django, qué base de Neon usa el equipo y cómo se "
       "respalda queda por decidir; por eso no se dibuja un servidor de producción.", 40, 610, 760, 70, tam=11)
d.nota("El código se comparte por GitHub (RonnyGG-git/SmartBite) y cada integrante lo corre en su computadora con "
       "su propio .env. Si alguien no tiene .env, Django usa db.sqlite3 local y no toca Neon.",
       820, 610, 740, 70, tam=11)
d.nota("Cubo = nodo («device» = máquina física; «executionEnvironment» = software que ejecuta otros artefactos). "
       "Rectángulo con hoja = artefacto desplegado en el nodo que lo contiene. Línea sólida = camino de comunicación "
       "con su protocolo; {…} = condición.", 40, 700, 1520, 46, tam=11)

d.alto = 780
d.guardar(*salida("10-despliegue-inventario"))
print("ok")
