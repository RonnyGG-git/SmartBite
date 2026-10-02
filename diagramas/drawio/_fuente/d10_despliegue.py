"""10 — Despliegue: dónde corre cada pieza hoy (desarrollo) y cómo se
conecta con Neon. La estrategia de producción no está decidida (principio 9
de la constitución: ADR pendiente), así que no se dibuja un servidor que no
existe. Fuente: smartbite/settings.py (SQLite), sql/tests/conftest.py y
README de sql/tests (rama de prueba de Neon, sslmode=require).

Correcciones frente a la versión del 2026-09-28 (UML 2.5.1, cláusula 19):
- Palabras clave estándar en inglés: «device» y «executionEnvironment»
  (19.4.4), «artifact», «script» y «file» (perfil estándar). Antes:
  «dispositivo», «entorno de ejecución», «nube», «archivo», «base de datos».
- Un entorno de ejecución es un nodo: cubo, no rectángulo plano.
- Las bases no van como cilindro (no es un símbolo UML): son entornos de
  ejecución PostgreSQL dentro del nodo de Neon.
- Los artefactos son rectángulos con icono de documento, no notas.
- db.sqlite3 está desplegado dentro del nodo; antes colgaba de una línea.
- «deploy» va de los artefactos al nodo destino (19.2.4); antes salía del
  entorno de pytest. La conexión planificada (spec 003) es un camino de
  comunicación con la restricción {planificado}, no una línea punteada.
"""
from rutas import salida
from drawio_lib import *  # noqa: F401,F403

d = Diagrama("Despliegue - Inventario", 1740, 1000)
d.titulo("Diagrama de despliegue — Inventario (Smart Bite)",
         "Dónde corre hoy cada pieza y cómo se conecta con la base de datos en Neon")

ROJO = "strokeColor=#b85450;fontColor=#b85450;"

# --- Nodos
d.nodo("PC o tablet del usuario", 40, 170, 300, 190, palabra_clave="device")
nav = d.nodo("Navegador web", 60, 245, 250, 90, palabra_clave="executionEnvironment", color=AZUL, tam=12)

d.nodo("Computadora de desarrollo (cada integrante)", 400, 110, 720, 700, palabra_clave="device")
django = d.nodo("Python 3 + Django 5.2 (venv)", 425, 175, 420, 230, palabra_clave="executionEnvironment",
                color=AZUL, tam=12, detalle="manage.py runserver → http://127.0.0.1:8000")
d.artefacto("smartbite", 450, 290, 240, 70, detalle="código del repo (apps Django)")
d.artefacto("db.sqlite3", 880, 215, 210, 84, palabra_clave="file", color=GRIS,
            detalle="la base de Django hoy;\nno se sube al repo")
pytest_env = d.nodo("pytest + psycopg2 (sql/tests)", 425, 460, 670, 300, palabra_clave="executionEnvironment",
                    color=VIOLETA, tam=12, detalle="el fixture aplica INVENTARIO y después COMPRAS")
inv_sql = d.artefacto("SMARTBITE_INVENTARIO\n_SP.sql", 450, 600, 190, 74, palabra_clave="script", tam=11)
com_sql = d.artefacto("SMARTBITE_COMPRAS\n_SP.sql", 660, 600, 190, 74, palabra_clave="script", tam=11)
d.artefacto(".env.test", 870, 600, 200, 74, palabra_clave="file", color=GRIS, tam=11,
            detalle="cadena de conexión;\nno se sube al repo")

d.nodo("Neon (PostgreSQL gestionado en la nube)", 1260, 110, 460, 700)
principal = d.nodo("PostgreSQL — rama principal", 1290, 185, 400, 170, palabra_clave="executionEnvironment",
                   color=VERDE, tam=12, detalle="la base del equipo; los scripts se aplican\ncuando pasan las "
                                                "pruebas; Django la usará\ncon la spec 003")
prueba = d.nodo("PostgreSQL — rama de prueba\n(test-inventario-jose)", 1290, 500, 400, 180,
                palabra_clave="executionEnvironment", color=AMARILLO, tam=12,
                detalle="el esquema se borra y se recrea\nen cada corrida de los tests")

# --- Caminos de comunicación (línea sólida, como una asociación)
d.arista(nav, django, ASOCIACION + "exitX=1;exitY=0.45;entryX=0;entryY=0.36;")
d.texto("«HTTP»", 330, 252, 80, 18, tam=12, alin="center", color="#222222")
d.arista(pytest_env, prueba, ASOCIACION + "exitX=1;exitY=0.25;entryX=0;entryY=0.17;")
d.texto("«PostgreSQL/TLS»\n(sslmode=require)", 1100, 494, 130, 34, tam=11, alin="center", color="#222222")
d.arista(django, principal, ASOCIACION + ROJO + "exitX=0.75;exitY=0;entryX=0.5;entryY=0;",
         puntos=[(740, 92), (1490, 92)])
d.texto("«PostgreSQL/TLS» {planificado: spec 003}", 880, 72, 360, 18, tam=11, alin="center", color="#b85450")

# --- «deploy»: los scripts (dos colas que se juntan) se aplican en las dos ramas
JX, JY = 1108, 730
for art, cx in ((inv_sql, 545), (com_sql, 755)):
    d.arista(art, d.vertice("", JX - 1, JY - 1, 2, 2, "rounded=0;fillColor=none;strokeColor=none;"),
             "endArrow=none;dashed=1;html=1;strokeColor=#555555;edgeStyle=orthogonalEdgeStyle;rounded=0;"
             "exitX=0.5;exitY=1;entryX=0.5;entryY=0.5;", puntos=[(cx, JY)])
d.junta(JX, JY)
d.flecha(JX, JY, 1290, 650, DEPENDENCIA + "edgeStyle=orthogonalEdgeStyle;rounded=0;",
         puntos=[(1230, JY), (1230, 650)])
d.texto("«deploy»\nen cada corrida", 1206, 690, 100, 34, tam=11, alin="left", color="#333333")
d.flecha(JX, JY, 1290, 320, DEPENDENCIA + "edgeStyle=orthogonalEdgeStyle;rounded=0;", puntos=[(JX, 320)])
d.texto("«deploy» cuando\npasan las pruebas\n(principio 7)", 1126, 372, 130, 50, tam=11, alin="left",
        color="#333333")

d.nota("Producción: no definida. Dónde se aloja Django y cómo se respalda la base es una decisión pendiente del "
       "equipo (ADR, principio 9 de la constitución); por eso no se dibuja un servidor de producción.",
       40, 840, 820, 50, tam=11)
d.nota("El código se comparte por GitHub (RonnyGG-git/SmartBite) y cada integrante lo corre en su computadora: en "
       "desarrollo, el navegador y el servidor suelen ser la misma máquina. En rojo: la conexión que llega con la "
       "spec 003.", 880, 840, 830, 50, tam=11)
d.nota("Cubo = nodo («device» = máquina física; «executionEnvironment» = software que ejecuta otros artefactos). "
       "Rectángulo con hoja = artefacto. Línea sólida = camino de comunicación. Punteada «deploy» = el artefacto se "
       "instala en ese nodo.", 40, 905, 1670, 44, tam=11)

d.alto = 970
d.guardar(*salida("10-despliegue-inventario"))
print("ok")
