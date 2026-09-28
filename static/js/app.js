/* Smart Bite — interacciones de la UI (sin dependencias).
   Cada bloque es independiente y no hace nada si su markup no está en la página. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  /* ---- Navegación: marca el enlace activo (prefijo de ruta más largo) ---- */
  (function marcarNavActiva() {
    var links = document.querySelectorAll(".sidebar a.sidebar-item");
    if (!links.length) return;
    var path = location.pathname;
    var mejor = null;
    var mejorLargo = -1;
    links.forEach(function (a) {
      var prefijos = [new URL(a.href, location.href).pathname];
      if (a.dataset.match) prefijos = prefijos.concat(a.dataset.match.split(" "));
      prefijos.forEach(function (p) {
        var coincide = p === "/" ? path === "/" : path.indexOf(p) === 0;
        if (coincide && p.length > mejorLargo) {
          mejor = a;
          mejorLargo = p.length;
        }
      });
    });
    if (mejor) mejor.setAttribute("aria-current", "page");
  })();

  /* ---- Drawer lateral en móvil ---- */
  (function drawer() {
    var boton = document.querySelector("[data-sidebar-toggle]");
    var scrim = document.querySelector(".scrim");
    if (!boton) return;
    var raiz = document.documentElement;

    function abrir(abierto) {
      raiz.classList.toggle("sidebar-open", abierto);
      boton.setAttribute("aria-expanded", String(abierto));
    }
    boton.addEventListener("click", function () {
      abrir(!raiz.classList.contains("sidebar-open"));
    });
    if (scrim) scrim.addEventListener("click", function () { abrir(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && raiz.classList.contains("sidebar-open")) {
        abrir(false);
        boton.focus();
      }
    });
  })();

  /* ---- Toasts: auto-cierre, pausa al pasar el cursor o con la pestaña oculta ---- */
  (function toasts() {
    var toasts = document.querySelectorAll(".toast");
    toasts.forEach(function (toast) {
      var restante = toast.classList.contains("toast-error") ? 8000 : 5000;
      var inicio = 0;
      var timer = null;

      function cerrar() {
        clearTimeout(timer);
        if (toast.classList.contains("is-leaving")) return;
        toast.classList.add("is-leaving");
        setTimeout(function () { toast.remove(); }, reduceMotion ? 0 : 200);
      }
      function correr() {
        inicio = Date.now();
        timer = setTimeout(cerrar, restante);
      }
      function pausar() {
        clearTimeout(timer);
        restante -= Date.now() - inicio;
      }

      toast.addEventListener("mouseenter", pausar);
      toast.addEventListener("mouseleave", correr);
      document.addEventListener("visibilitychange", function () {
        if (document.hidden) pausar(); else correr();
      });
      var cerrarBtn = toast.querySelector(".toast-close");
      if (cerrarBtn) cerrarBtn.addEventListener("click", cerrar);
      correr();
    });
  })();

  /* ---- Formularios: evita doble envío y muestra spinner en el botón pulsado.
     No se deshabilita el botón: su name/value (p. ej. "estado") debe viajar en el POST. ---- */
  (function envios() {
    document.addEventListener("submit", function (e) {
      var form = e.target;
      if (e.defaultPrevented) return; // otro manejador ya canceló el envío
      if (form.dataset.enviando === "1") {
        e.preventDefault();
        return;
      }
      form.dataset.enviando = "1";
      var boton = e.submitter || form.querySelector("[type=submit]");
      if (boton && boton.classList.contains("btn")) boton.classList.add("is-loading");
    });
    // Al volver con "atrás" (bfcache) el formulario debe quedar usable otra vez
    window.addEventListener("pageshow", function (e) {
      if (!e.persisted) return;
      document.querySelectorAll("form[data-enviando]").forEach(function (f) { delete f.dataset.enviando; });
      document.querySelectorAll(".btn.is-loading").forEach(function (b) { b.classList.remove("is-loading"); });
    });
  })();

  /* ---- Contadores animados en las cifras del dashboard ---- */
  (function contadores() {
    var nodos = document.querySelectorAll("[data-countup]");
    if (!nodos.length || reduceMotion) return;

    function formatear(n, moneda) {
      var s = Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
      return moneda ? "$" + s : s;
    }
    nodos.forEach(function (nodo) {
      var texto = nodo.textContent.trim();
      var moneda = texto.charAt(0) === "$";
      var objetivo = parseInt(texto.replace(/[^\d]/g, ""), 10);
      if (!objetivo) return;
      var duracion = 900;
      var t0 = null;
      nodo.textContent = formatear(0, moneda);
      function paso(t) {
        if (t0 === null) t0 = t;
        var p = Math.min((t - t0) / duracion, 1);
        var e = 1 - Math.pow(1 - p, 4); // ease-out quart
        nodo.textContent = formatear(objetivo * e, moneda);
        if (p < 1) requestAnimationFrame(paso);
        else nodo.textContent = texto;
      }
      requestAnimationFrame(paso);
    });
  })();

  /* ---- Barras de reportes: escala relativa al máximo de su grupo ---- */
  (function barras() {
    document.querySelectorAll("[data-bars]").forEach(function (grupo) {
      var filas = grupo.querySelectorAll("[data-value]");
      var max = 0;
      filas.forEach(function (f) { max = Math.max(max, parseFloat(f.dataset.value) || 0); });
      filas.forEach(function (f) {
        var v = parseFloat(f.dataset.value) || 0;
        var meter = f.querySelector(".meter");
        if (meter) meter.style.setProperty("--p", max ? (v / max) * 100 : 0);
      });
    });
    // Los medidores parten en 0 y crecen tras el primer frame
    var idle = document.querySelectorAll(".meter.is-idle");
    if (!idle.length) return;
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        idle.forEach(function (m) { m.classList.remove("is-idle"); });
      });
    });
  })();

  /* ---- Borde iluminado bajo el cursor ---- */
  (function spotlight() {
    if (!finePointer || reduceMotion) return;
    document.querySelectorAll(".spotlight").forEach(function (el) {
      el.addEventListener("pointermove", function (e) {
        var r = el.getBoundingClientRect();
        el.style.setProperty("--mx", e.clientX - r.left + "px");
        el.style.setProperty("--my", e.clientY - r.top + "px");
      });
    });
  })();

  /* ---- Filtro de mesas por estado ---- */
  (function filtroMesas() {
    var chips = document.querySelectorAll("[data-filter]");
    if (!chips.length) return;
    var tiles = document.querySelectorAll("[data-estado]");
    chips.forEach(function (chip) {
      var filtro = chip.dataset.filter;
      var total = 0;
      tiles.forEach(function (t) { if (filtro === "TODAS" || t.dataset.estado === filtro) total++; });
      var contador = chip.querySelector(".chip-count");
      if (contador) contador.textContent = total;
    });
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        var filtro = chip.dataset.filter;
        chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c === chip)); });
        tiles.forEach(function (t) {
          t.hidden = filtro !== "TODAS" && t.dataset.estado !== filtro;
        });
      });
    });
  })();

  /* ---- Menú público: resalta la categoría visible ---- */
  (function menuCategorias() {
    var nav = document.querySelector(".menu-nav");
    if (!nav || !("IntersectionObserver" in window)) return;
    var chips = {};
    nav.querySelectorAll("a[href^='#']").forEach(function (a) { chips[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (en) {
        if (!en.isIntersecting) return;
        Object.keys(chips).forEach(function (id) { chips[id].classList.toggle("is-active", id === en.target.id); });
        var activo = chips[en.target.id];
        if (activo) {
          nav.scrollTo({
            left: activo.offsetLeft - nav.clientWidth / 2 + activo.offsetWidth / 2,
            behavior: reduceMotion ? "auto" : "smooth",
          });
        }
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    document.querySelectorAll(".menu-section[id]").forEach(function (s) { io.observe(s); });
  })();

  /* ---- Autopedido: selector de cantidades y total en vivo ---- */
  (function autopedido() {
    var form = document.querySelector("form[data-pedido]");
    if (!form) return;
    var barra = form.querySelector("[data-order-bar]");
    var conteo = form.querySelector("[data-order-count]");
    var totalEl = form.querySelector("[data-order-total]");
    var inputs = form.querySelectorAll(".stepper-qty input");

    function formatear(n) {
      return "$" + Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    }
    function recalcular(animar) {
      var cantidad = 0;
      var total = 0;
      inputs.forEach(function (input) {
        var max = parseInt(input.max, 10) || 20;
        var v = Math.max(0, Math.min(max, parseInt(input.value, 10) || 0));
        if (String(v) !== input.value) input.value = v;
        var plato = input.closest(".dish");
        plato.classList.toggle("is-selected", v > 0);
        cantidad += v;
        total += v * parseFloat(plato.dataset.precio || "0");
      });
      conteo.textContent = cantidad;
      totalEl.textContent = formatear(total);
      barra.classList.toggle("is-empty", cantidad === 0);
      if (animar && !reduceMotion) {
        totalEl.classList.remove("bump");
        void totalEl.offsetWidth; // reinicia la animación
        totalEl.classList.add("bump");
      }
    }

    form.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-qty]");
      if (!btn) return;
      var input = btn.parentElement.querySelector("input");
      input.value = (parseInt(input.value, 10) || 0) + parseInt(btn.dataset.qty, 10);
      recalcular(true);
    });
    form.addEventListener("input", function (e) {
      if (e.target.matches(".stepper-qty input")) recalcular(false);
    });
    // Sin platillos no se envía (el servidor también lo valida)
    form.addEventListener("submit", function (e) {
      if (barra.classList.contains("is-empty")) e.preventDefault();
    }, true);
    recalcular(false);
  })();

  /* ---- Acciones declarativas ---- */
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-action]");
    if (!el) return;
    if (el.dataset.action === "print") window.print();
    if (el.dataset.action === "back") {
      e.preventDefault();
      history.back();
    }
  });
})();
