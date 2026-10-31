(function () {
  "use strict";

  var raiz = document.documentElement;
  var gsap = window.gsap;
  var ScrollTrigger = window.ScrollTrigger;
  var reducir = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var punteroFino = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var activo = !!gsap && !reducir;
  var SVG = "http://www.w3.org/2000/svg";

  var M = {
    rapido: 0.18,
    normal: 0.38,
    lento: 0.7,
    ease: "power3.out",
    stagger: 0.06,
    visibles: 14,
    limpiar: "transform,opacity,visibility",
    ciclo: 24,
  };

  var GRUPOS = [
    ".stagger", ".grid", ".tickets", ".stack", ".stats", ".menu-list", ".tipo-opciones",
    ".chips", ".menu-nav", ".cliente-links", ".page-actions", ".form-fields", ".form-grid",
  ].join(",");

  function todos(selector, contexto) {
    return Array.prototype.slice.call((contexto || document).querySelectorAll(selector));
  }

  function lista(objetivos) {
    if (!objetivos) { return []; }
    if (objetivos.nodeType === 1) { return [objetivos]; }
    return Array.prototype.slice.call(objetivos).filter(Boolean);
  }

  function formatear(n, moneda) {
    var s = Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return moneda ? "$" + s : s;
  }

  var Animar = {
    activo: activo,

    salidaToast: function (toast, fin) {
      if (!activo) { fin(); return; }
      gsap.to(toast, { autoAlpha: 0, y: 8, scale: 0.98, duration: M.rapido, ease: "power1.in", onComplete: fin });
    },

    rebote: function (el) {
      if (!activo) { return; }
      gsap.fromTo(el, { scale: 1 }, { scale: 1.06, duration: 0.11, ease: "power1.out", yoyo: true, repeat: 1 });
    },

    otpError: function (grupo) {
      if (!activo) { return; }
      gsap.fromTo(grupo, { x: 0 }, {
        keyframes: { x: [0, -10, 9, -7, 5, -2, 0] },
        duration: 0.45,
        ease: "power1.out",
        clearProps: "transform",
      });
    },

    otpCompleto: function (grupo) {
      grupo.classList.add("is-ok");
      if (!activo) { return 0; }
      gsap.fromTo(todos(".otp-box", grupo), { scale: 1 }, {
        scale: 1.08, duration: 0.12, ease: "power2.out", yoyo: true, repeat: 1, stagger: 0.04,
      });
      return 260;
    },
  };

  window.Animar = Animar;

  function listo() {
    raiz.classList.remove("anim-pendiente");
  }

  function agregar(tl, objetivos, vars, posicion) {
    var elementos = lista(objetivos);
    if (elementos.length) {
      tl.from(elementos, vars, posicion);
    }
  }

  function revelarAlBajar(elementos) {
    if (!elementos.length) { return; }
    if (!ScrollTrigger) {
      return;
    }
    elementos.forEach(function (el) { el.classList.add("anim-revelar"); });
    gsap.set(elementos, { opacity: 0, y: 18 });
    ScrollTrigger.batch(elementos, {
      start: "top 94%",
      once: true,
      onEnter: function (lote) {
        gsap.to(lote, {
          opacity: 1, y: 0, duration: M.normal, ease: M.ease, stagger: M.stagger, overwrite: true,
          clearProps: M.limpiar,
          onComplete: function () { lote.forEach(function (el) { el.classList.remove("anim-revelar"); }); },
        });
      },
    });
  }

  function componentes(contenedor, tl, inicio) {
    var vistos = new Set();
    var abajo = [];

    todos(GRUPOS, contenedor).forEach(function (grupo) {
      var hijos = lista(grupo.children).filter(function (h) { return !vistos.has(h); });
      hijos.forEach(function (h) { vistos.add(h); });
      if (!hijos.length) { return; }
      var horizontal = grupo.matches(".chips, .menu-nav, .cliente-links, .page-actions");
      agregar(tl, hijos.slice(0, M.visibles), horizontal
        ? { opacity: 0, x: -10, stagger: 0.04, duration: 0.3 }
        : { opacity: 0, y: 14, scale: 0.985, stagger: M.stagger }, inicio + 0.1);
      abajo = abajo.concat(hijos.slice(M.visibles));
    });

    todos("table tbody", contenedor).forEach(function (cuerpo) {
      var filas = lista(cuerpo.rows);
      agregar(tl, filas.slice(0, M.visibles), { opacity: 0, x: -8, stagger: 0.03, duration: 0.3 }, inicio + 0.18);
      abajo = abajo.concat(filas.slice(M.visibles));
    });

    todos(".stepper", contenedor).forEach(function (pasos) {
      agregar(tl, pasos.children, { opacity: 0, y: 10, stagger: 0.08 }, inicio + 0.2);
      var actual = pasos.querySelector(".is-current");
      if (actual) {
        tl.fromTo(actual, { scale: 1 }, { scale: 1.05, duration: 0.22, yoyo: true, repeat: 1, ease: "power2.out" }, ">");
      }
    });

    agregar(tl, todos(".qr-frame", contenedor), {
      opacity: 0, scale: 0.9, rotation: -3, duration: 0.6, ease: "back.out(1.6)",
    }, inicio + 0.15);

    agregar(tl, todos(".order-bar", contenedor), { y: 60, opacity: 0, duration: 0.5 }, inicio + 0.3);

    todos(".menu-section", contenedor).forEach(function (seccion, i) {
      if (i > 0) { abajo.push(seccion.querySelector("h2, h3")); }
    });

    revelarAlBajar(abajo.filter(Boolean));
  }

  function escenaEstatica(svg) {
    var marcas = svg.querySelector("[data-escena-marcas]");
    if (marcas && !marcas.childNodes.length) {
      for (var i = 0; i < 72; i++) {
        var a = (i / 72) * Math.PI * 2;
        var mayor = i % 6 === 0;
        var linea = document.createElementNS(SVG, "line");
        var r1 = 279;
        var r2 = mayor ? 293 : 287;
        linea.setAttribute("x1", (300 + r1 * Math.sin(a)).toFixed(2));
        linea.setAttribute("y1", (300 - r1 * Math.cos(a)).toFixed(2));
        linea.setAttribute("x2", (300 + r2 * Math.sin(a)).toFixed(2));
        linea.setAttribute("y2", (300 - r2 * Math.cos(a)).toFixed(2));
        linea.setAttribute("class", "escena-marca" + (mayor ? " is-mayor" : ""));
        marcas.appendChild(linea);
      }
    }
    var brasas = svg.querySelector("[data-escena-brasas]");
    if (brasas && !brasas.childNodes.length) {
      for (var j = 0; j < 14; j++) {
        var angulo = Math.random() * Math.PI * 2;
        var radio = 70 + Math.random() * 190;
        var brasa = document.createElementNS(SVG, "circle");
        brasa.setAttribute("cx", (300 + radio * Math.sin(angulo)).toFixed(1));
        brasa.setAttribute("cy", (300 - radio * Math.cos(angulo)).toFixed(1));
        brasa.setAttribute("r", (0.8 + Math.random() * 1.6).toFixed(2));
        brasa.setAttribute("class", "escena-brasa");
        brasa.style.opacity = (0.12 + Math.random() * 0.35).toFixed(2);
        brasas.appendChild(brasa);
      }
    }
  }

  function trazar(elementos) {
    elementos.forEach(function (el) {
      var largo = el.getTotalLength ? el.getTotalLength() : 0;
      if (largo) { gsap.set(el, { strokeDasharray: largo, strokeDashoffset: largo }); }
    });
    return { strokeDashoffset: 0, onComplete: function () { gsap.set(elementos, { clearProps: "strokeDasharray,strokeDashoffset" }); } };
  }

  function escena(svg, aside) {
    var q = function (sel) { return svg.querySelector(sel); };
    var qq = function (sel) { return todos(sel, svg); };
    var orbitas = qq(".escena-orbita--sala, .escena-orbita--caja");
    var plato = qq(".escena-plato [data-trazo]");
    var campana = q("[data-escena-campana]");
    var campanaTrazos = qq("[data-escena-campana] [data-trazo]");
    var insignias = qq(".escena-insignia");
    var iconos = qq("[data-escena-icono] [data-trazo]");
    var giros = qq("[data-escena-giro]");
    var vapor = qq("[data-escena-vapor] path");
    var brasas = qq(".escena-brasa");
    var marcas = qq(".escena-marca");
    var onda = q("[data-escena-onda]");
    var brillo = q("[data-escena-brillo]");
    var parallax = q("[data-escena-parallax]");

    var intro = gsap.timeline({ defaults: { ease: "power2.inOut" } });
    intro
      .from(brillo, { opacity: 0, scale: 0.6, svgOrigin: "300 300", duration: 1.6, ease: "power2.out" }, 0)
      .to(orbitas, Object.assign({ duration: 1.8, stagger: 0.25 }, trazar(orbitas)), 0.1)
      .from(q(".escena-orbita--cocina"), { opacity: 0, rotation: -90, svgOrigin: "300 300", duration: 1.8, ease: "expo.out" }, 0.3)
      .from(marcas, { opacity: 0, duration: 0.5, stagger: { each: 0.012, from: "start" } }, 0.4)
      .to(plato, Object.assign({ duration: 0.8, stagger: 0.12 }, trazar(plato)), 0.7)
      .to(campanaTrazos, Object.assign({ duration: 1, stagger: 0.14 }, trazar(campanaTrazos)), 0.95)
      .from(insignias, { scale: 0, opacity: 0, transformOrigin: "50% 50%", duration: 0.6, stagger: 0.15, ease: "back.out(2.2)" }, 1.4)
      .to(iconos, Object.assign({ duration: 0.7, stagger: 0.15 }, trazar(iconos)), 1.55)
      .from(brasas, { opacity: 0, duration: 1, stagger: 0.05, ease: "power1.out" }, 1.6);

    var ciclo = gsap.timeline({ repeat: -1, paused: true, defaults: { ease: "none" } });
    var vueltas = [1, -2, 3];
    giros.forEach(function (giro, i) {
      var n = vueltas[i];
      var icono = giro.querySelector("[data-escena-icono]");
      var insignia = giro.querySelector(".escena-insignia");
      ciclo.to(giro, { rotation: 360 * n, svgOrigin: "300 300", duration: M.ciclo }, 0);
      ciclo.to(icono, { rotation: -360 * n, transformOrigin: "50% 50%", duration: M.ciclo }, 0);
      var periodo = M.ciclo / Math.abs(n);
      for (var k = 0; k < Math.abs(n); k++) {
        ciclo.fromTo(insignia, { scale: 1 }, {
          scale: 1.22, transformOrigin: "50% 50%", duration: 0.28, ease: "power2.out", yoyo: true, repeat: 1,
        }, k * periodo);
      }
    });
    ciclo
      .fromTo(onda, { attr: { r: 70 }, opacity: 0.55 }, { attr: { r: 300 }, opacity: 0, duration: 2.4, ease: "power2.out" }, 0)
      .to(campana, { y: -16, rotation: -7, svgOrigin: "204 350", duration: 0.7, ease: "power3.out" }, 0)
      .to(campana, { y: 0, rotation: 0, svgOrigin: "204 350", duration: 1.1, ease: "bounce.out" }, 1.2)
      .fromTo(brillo, { opacity: 1 }, { opacity: 0.55, duration: 1.4, ease: "sine.inOut", yoyo: true, repeat: 1 }, 0.2);

    var giroMarcas = gsap.to(svg.querySelector("[data-escena-marcas]"), {
      rotation: 360, svgOrigin: "300 300", duration: 180, ease: "none", repeat: -1, paused: true,
    });
    var giroCocina = gsap.to(q(".escena-orbita--cocina"), {
      rotation: "-=360", svgOrigin: "300 300", duration: 90, ease: "none", repeat: -1, paused: true,
    });

    var humo = vapor.map(function (camino, i) {
      var largo = camino.getTotalLength();
      return gsap.timeline({ repeat: -1, delay: i * 0.7, paused: true })
        .set(camino, { strokeDasharray: largo * 0.45 + " " + largo, strokeDashoffset: largo * 0.45, opacity: 0 })
        .to(camino, { strokeDashoffset: -largo * 0.7, duration: 2.6, ease: "sine.inOut" }, 0)
        .to(camino, { opacity: 1, duration: 0.8, ease: "sine.out" }, 0)
        .to(camino, { opacity: 0, duration: 1, ease: "sine.in" }, 1.6);
    });

    var flotar = brasas.map(function (b) {
      var base = parseFloat(b.style.opacity) || 0.3;
      var d = 5 + Math.random() * 4;
      return gsap.timeline({ repeat: -1, delay: Math.random() * 4, paused: true })
        .fromTo(b, { y: 0, x: 0 }, { y: -40 - Math.random() * 50, x: (Math.random() - 0.5) * 30, duration: d, ease: "sine.inOut" }, 0)
        .fromTo(b, { opacity: 0 }, { opacity: base, duration: d * 0.25, ease: "sine.out" }, 0)
        .to(b, { opacity: 0, duration: d * 0.75, ease: "sine.in" }, d * 0.25);
    });

    intro.eventCallback("onComplete", function () {
      ciclo.play(0);
      giroMarcas.play();
      giroCocina.play();
      humo.forEach(function (t) { t.play(); });
      flotar.forEach(function (t) { t.play(); });
    });

    if (punteroFino && aside && parallax) {
      var px = gsap.quickTo(parallax, "x", { duration: 1.2, ease: "power3.out" });
      var py = gsap.quickTo(parallax, "y", { duration: 1.2, ease: "power3.out" });
      aside.addEventListener("pointermove", function (e) {
        var r = aside.getBoundingClientRect();
        px(((e.clientX - r.left) / r.width - 0.5) * -24);
        py(((e.clientY - r.top) / r.height - 0.5) * -24);
      });
      aside.addEventListener("pointerleave", function () { px(0); py(0); });
    }
  }

  function acceso(auth) {
    var tl = gsap.timeline({ defaults: { ease: M.ease, duration: M.normal, clearProps: M.limpiar } });
    var aside = auth.querySelector(".auth-aside");
    if (aside) {
      agregar(tl, aside.querySelector(".sidebar-brand"), { autoAlpha: 0, y: -12 }, 0);
      agregar(tl, todos("h1, p", aside), { autoAlpha: 0, y: 26, stagger: 0.09, duration: M.lento }, 0.2);
      agregar(tl, todos(".auth-points span", aside), { autoAlpha: 0, y: 10, stagger: M.stagger }, 0.55);
      agregar(tl, aside.querySelector(".auth-ring"), {
        autoAlpha: 0, scale: 0.82, rotation: -40, duration: 1.2, ease: "expo.out",
      }, 0.1);
      var svg = aside.querySelector("[data-escena]");
      if (svg) { escena(svg, aside); }
    }
    var form = auth.querySelector(".auth-form");
    if (form) {
      agregar(tl, form.children, { opacity: 0, y: 16, stagger: M.stagger }, 0.15);
      agregar(tl, todos(".otp-box", form), {
        opacity: 0, y: 14, scale: 0.85, stagger: 0.07, ease: "back.out(2)", duration: 0.45,
      }, 0.4);
      agregar(tl, todos(".auth-roles > *", form), { opacity: 0, y: 8, stagger: 0.05 }, 0.5);
      var grupo = form.querySelector(".otp-boxes.is-error");
      if (grupo) {
        tl.add(function () { Animar.otpError(grupo); });
      }
    }
  }

  function pagina(contenedor) {
    var tl = gsap.timeline({ defaults: { ease: M.ease, duration: M.normal, clearProps: M.limpiar } });
    agregar(tl, contenedor.children, { opacity: 0, y: 12, stagger: 0.05 }, 0);
    todos(".menu-hero", contenedor).forEach(function (hero) {
      agregar(tl, hero.children, { opacity: 0, y: 18, stagger: 0.07, duration: M.lento }, 0.05);
    });
    componentes(contenedor, tl, 0);
  }

  function menuLateral() {
    var items = todos(".sidebar .nav-group");
    if (!items.length) { return; }
    var clave = "sb-menu-animado";
    try {
      if (sessionStorage.getItem(clave)) { return; }
      sessionStorage.setItem(clave, "1");
    } catch (e) {
      return;
    }
    gsap.from(items, { opacity: 0, x: -12, duration: M.normal, ease: M.ease, stagger: 0.07, clearProps: M.limpiar });
  }

  function contadores() {
    todos("[data-countup]").forEach(function (nodo) {
      var texto = nodo.textContent.trim();
      var moneda = texto.charAt(0) === "$";
      var objetivo = parseInt(texto.replace(/[^\d]/g, ""), 10);
      if (!objetivo) { return; }
      var estado = { valor: 0 };
      nodo.textContent = formatear(0, moneda);
      gsap.to(estado, {
        valor: objetivo,
        duration: 1,
        delay: 0.15,
        ease: "power4.out",
        onUpdate: function () { nodo.textContent = formatear(estado.valor, moneda); },
        onComplete: function () { nodo.textContent = texto; },
      });
    });
  }

  function barras() {
    todos("[data-bars]").forEach(function (grupo) {
      var filas = todos("[data-value]", grupo);
      var max = 0;
      filas.forEach(function (f) { max = Math.max(max, parseFloat(f.dataset.value) || 0); });
      filas.forEach(function (f) {
        var v = parseFloat(f.dataset.value) || 0;
        var meter = f.querySelector(".meter");
        if (meter) { meter.style.setProperty("--p", max ? (v / max) * 100 : 0); }
      });
    });
    var spans = todos(".meter > span");
    todos(".meter.is-idle").forEach(function (m) { m.classList.remove("is-idle"); });
    if (activo && spans.length) {
      gsap.from(spans, { scaleX: 0, duration: 0.9, delay: 0.2, ease: "power3.out", stagger: 0.05, clearProps: "transform" });
    }
  }

  function toasts() {
    var avisos = todos(".toast");
    if (avisos.length) {
      gsap.from(avisos, {
        autoAlpha: 0, y: 14, scale: 0.98, duration: M.normal, ease: M.ease, stagger: 0.08, delay: 0.1,
        clearProps: M.limpiar,
      });
    }
  }

  function spotlight() {
    if (!punteroFino) { return; }
    todos(".spotlight").forEach(function (el) {
      var punto = { x: 0, y: 0 };
      function pintar() {
        el.style.setProperty("--mx", punto.x + "px");
        el.style.setProperty("--my", punto.y + "px");
      }
      var x = gsap.quickTo(punto, "x", { duration: 0.35, ease: "power3.out", onUpdate: pintar });
      var y = gsap.quickTo(punto, "y", { duration: 0.35, ease: "power3.out", onUpdate: pintar });
      function posicion(e) {
        var r = el.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
      }
      el.addEventListener("pointerenter", function (e) {
        var p = posicion(e);
        punto.x = p.x;
        punto.y = p.y;
        x(p.x, p.x);
        y(p.y, p.y);
        pintar();
      });
      el.addEventListener("pointermove", function (e) {
        var p = posicion(e);
        x(p.x);
        y(p.y);
      });
    });
  }

  function clics() {
    var activos = 0;
    var CHISPAS = 6;
    document.addEventListener("pointerdown", function (e) {
      if (e.button !== 0 || activos >= 6) { return; }
      activos += 1;
      var fx = document.createElement("span");
      fx.className = "clic-fx";
      fx.setAttribute("aria-hidden", "true");
      var anillo = document.createElement("span");
      anillo.className = "clic-fx-anillo";
      fx.appendChild(anillo);
      var chispas = [];
      for (var i = 0; i < CHISPAS; i++) {
        var chispa = document.createElement("span");
        chispa.className = "clic-fx-chispa";
        fx.appendChild(chispa);
        chispas.push(chispa);
      }
      document.body.appendChild(fx);
      gsap.set(fx, { x: e.clientX, y: e.clientY });
      var giro = Math.random() * Math.PI;
      var tl = gsap.timeline({
        onComplete: function () {
          fx.remove();
          activos -= 1;
        },
      });
      tl.fromTo(anillo, { scale: 0.15, opacity: 1 }, { scale: 1, opacity: 0, duration: 0.55, ease: "power2.out" }, 0);
      chispas.forEach(function (chispa, i) {
        var a = giro + (i / CHISPAS) * Math.PI * 2;
        var d = 20 + Math.random() * 10;
        tl.fromTo(chispa, { x: 0, y: 0, scale: 1, opacity: 1 }, {
          x: Math.cos(a) * d, y: Math.sin(a) * d, scale: 0, opacity: 0, duration: 0.42, ease: "power3.out",
        }, 0.03);
      });
    }, { passive: true });
  }

  function iniciar() {
    listo();
    barras();
    todos("[data-escena]").forEach(escenaEstatica);
    if (!activo) {
      return;
    }
    if (ScrollTrigger) { gsap.registerPlugin(ScrollTrigger); }
    gsap.defaults({ overwrite: "auto" });
    var auth = document.querySelector(".auth");
    var main = document.querySelector(".main-inner");
    var cliente = document.querySelector(".menu-page");
    if (auth) { acceso(auth); }
    if (main) { pagina(main); }
    if (cliente) { pagina(cliente); }
    if (!auth && !main && !cliente) {
      var publico = document.getElementById("contenido");
      if (publico) { pagina(publico); }
    }
    menuLateral();
    contadores();
    toasts();
    spotlight();
    clics();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
