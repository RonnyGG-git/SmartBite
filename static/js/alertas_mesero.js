(function () {
  var raiz = document.querySelector("[data-alertas-mesero]");
  if (!raiz) return;

  var INTERVALO_MS = 8000;
  var conocidos = null;

  function sonar() {
    var Contexto = window.AudioContext || window.webkitAudioContext;
    if (!Contexto) return;
    try {
      var audio = new Contexto();
      var tono = audio.createOscillator();
      var volumen = audio.createGain();
      tono.frequency.value = 880;
      volumen.gain.value = 0.08;
      tono.connect(volumen).connect(audio.destination);
      tono.start();
      tono.stop(audio.currentTime + 0.25);
    } catch (error) {}
  }

  function elemento(etiqueta, clase, texto) {
    var nodo = document.createElement(etiqueta);
    if (clase) nodo.className = clase;
    if (texto) nodo.textContent = texto;
    return nodo;
  }

  async function resolver(url, boton) {
    boton.disabled = true;
    try {
      await fetch(url, {
        method: "POST",
        headers: { "X-CSRFToken": raiz.dataset.csrf, "X-Requested-With": "XMLHttpRequest" },
      });
    } finally {
      consultar();
    }
  }

  function boton(texto, clase, url) {
    var nodo = elemento("button", "btn btn-sm " + clase, texto);
    nodo.type = "button";
    nodo.addEventListener("click", function () { resolver(url, nodo); });
    return nodo;
  }

  function tarjeta(pedido) {
    var nodo = elemento("article", "alerta-mesero");
    nodo.appendChild(elemento("strong", "alerta-mesero-titulo", "Pedido #" + pedido.id + " · " + pedido.lugar));
    if (pedido.cliente) nodo.appendChild(elemento("span", "subtle", pedido.cliente));
    nodo.appendChild(elemento("p", "alerta-mesero-platillos", pedido.platillos.join(", ")));
    var acciones = elemento("div", "alerta-mesero-acciones");
    acciones.appendChild(boton("Confirmar", "btn-primary", pedido.confirmar_url));
    acciones.appendChild(boton("Rechazar", "btn-quiet is-danger", pedido.rechazar_url));
    nodo.appendChild(acciones);
    return nodo;
  }

  function pintar(pedidos) {
    var ids = pedidos.map(function (p) { return p.id; });
    var hayNuevos = conocidos !== null && ids.some(function (id) { return conocidos.indexOf(id) === -1; });
    if (conocidos === null || ids.join() !== conocidos.join()) {
      raiz.replaceChildren.apply(raiz, pedidos.map(tarjeta));
    }
    raiz.hidden = pedidos.length === 0;
    conocidos = ids;
    if (hayNuevos) sonar();
  }

  async function consultar() {
    if (document.hidden) return;
    try {
      var respuesta = await fetch(raiz.dataset.url, { headers: { Accept: "application/json" } });
      if (respuesta.ok) pintar((await respuesta.json()).pedidos);
    } catch (error) {}
  }

  consultar();
  setInterval(consultar, INTERVALO_MS);
  document.addEventListener("visibilitychange", consultar);
})();
