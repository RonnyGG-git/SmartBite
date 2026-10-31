(function () {
  "use strict";

  var LARGO = 4;

  function soloDigitos(texto) {
    return (texto || "").replace(/\D/g, "");
  }

  function montar(original) {
    var form = original.form;
    var grupo = document.createElement("div");
    grupo.className = "otp-boxes";
    grupo.setAttribute("role", "group");
    grupo.setAttribute("aria-label", "Código de " + LARGO + " dígitos");

    var cajas = [];
    for (var i = 0; i < LARGO; i++) {
      var caja = document.createElement("input");
      caja.type = "text";
      caja.inputMode = "numeric";
      caja.maxLength = 1;
      caja.autocomplete = i === 0 ? "one-time-code" : "off";
      caja.className = "otp-box";
      caja.setAttribute("aria-label", "Dígito " + (i + 1));
      cajas.push(caja);
      grupo.appendChild(caja);
    }

    var conError = !!form.querySelector("[data-otp-error]");
    var inicial = conError ? "" : soloDigitos(original.value).slice(0, LARGO);
    cajas.forEach(function (caja, i) { caja.value = inicial[i] || ""; });

    original.type = "hidden";
    original.removeAttribute("autofocus");
    original.insertAdjacentElement("afterend", grupo);

    var etiqueta = form.querySelector('label[for="' + original.id + '"]');
    if (etiqueta) {
      cajas[0].id = original.id + "_1";
      etiqueta.setAttribute("for", cajas[0].id);
    }

    var otrosCampos = Array.prototype.filter.call(form.elements, function (el) {
      return el.tagName === "INPUT" && el.type !== "hidden" && !el.classList.contains("otp-box");
    });

    function sincronizar() {
      var valor = cajas.map(function (c) { return c.value; }).join("");
      original.value = valor;
      cajas.forEach(function (c) { c.classList.toggle("is-filled", c.value !== ""); });
      grupo.classList.remove("is-error");
      if (valor.length !== LARGO) {
        grupo.classList.remove("is-ok");
        return;
      }
      var espera = window.Animar ? window.Animar.otpCompleto(grupo) : 0;
      if (!otrosCampos.length && !form.dataset.otpEnviado) {
        form.dataset.otpEnviado = "1";
        setTimeout(function () {
          if (form.requestSubmit) { form.requestSubmit(); } else { form.submit(); }
        }, espera);
      }
    }

    function repartir(desde, digitos) {
      for (var i = 0; i < digitos.length && desde + i < LARGO; i++) {
        cajas[desde + i].value = digitos[i];
      }
      var siguiente = Math.min(desde + digitos.length, LARGO - 1);
      cajas[siguiente].focus();
      sincronizar();
    }

    cajas.forEach(function (caja, i) {
      caja.addEventListener("input", function () {
        var digitos = soloDigitos(caja.value);
        caja.value = "";
        if (digitos) { repartir(i, digitos); } else { sincronizar(); }
      });

      caja.addEventListener("keydown", function (evento) {
        if (evento.key === "Backspace" && !caja.value && i > 0) {
          cajas[i - 1].value = "";
          cajas[i - 1].focus();
          sincronizar();
          evento.preventDefault();
        } else if (evento.key === "ArrowLeft" && i > 0) {
          cajas[i - 1].focus();
          evento.preventDefault();
        } else if (evento.key === "ArrowRight" && i < LARGO - 1) {
          cajas[i + 1].focus();
          evento.preventDefault();
        }
      });

      caja.addEventListener("paste", function (evento) {
        var texto = (evento.clipboardData || window.clipboardData).getData("text");
        var digitos = soloDigitos(texto);
        if (!digitos) { return; }
        evento.preventDefault();
        repartir(digitos.length >= LARGO ? 0 : i, digitos);
      });

      caja.addEventListener("focus", function () { caja.select(); });
    });

    form.addEventListener("submit", function () { sincronizar(); });

    if (conError) {
      grupo.classList.add("is-error");
    }

    var vacia = cajas.find(function (c) { return !c.value; }) || cajas[LARGO - 1];
    vacia.focus();
  }

  function cuentaRegresiva(boton) {
    var restante = parseInt(boton.dataset.espera, 10) || 0;
    var texto = boton.querySelector("[data-espera-texto]");
    if (restante <= 0) { return; }
    boton.disabled = true;
    var reloj = setInterval(function () {
      restante -= 1;
      if (restante <= 0) {
        clearInterval(reloj);
        boton.disabled = false;
        if (texto) { texto.textContent = ""; }
        return;
      }
      if (texto) { texto.textContent = " en " + restante + " s"; }
    }, 1000);
  }

  function iniciar() {
    document.querySelectorAll("input[data-otp]").forEach(montar);
    document.querySelectorAll("[data-espera]").forEach(cuentaRegresiva);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
