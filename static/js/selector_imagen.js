(function () {
  document.querySelectorAll("[data-selector-imagen]").forEach(function (raiz) {
    var entrada = raiz.querySelector('input[type="file"]:not([data-captura])');
    var captura = raiz.querySelector("[data-captura]");
    var vista = raiz.querySelector("[data-vista]");
    var vacio = raiz.querySelector("[data-sin-imagen]");
    var estado = raiz.querySelector("[data-estado]");
    var panel = raiz.querySelector("[data-panel-camara]");
    var video = raiz.querySelector("[data-video]");
    var campoUrl = entrada.form.querySelector('[name="url_imagen"]');
    var flujo = null;
    var urlVista = null;

    function mostrar(src) {
      vista.src = src;
      vista.hidden = false;
      vacio.hidden = true;
    }

    function ocultarVista() {
      vista.removeAttribute("src");
      vista.hidden = true;
      vacio.hidden = false;
    }

    function previsualizar(archivo) {
      if (urlVista) URL.revokeObjectURL(urlVista);
      urlVista = URL.createObjectURL(archivo);
      mostrar(urlVista);
      if (campoUrl) campoUrl.value = "";
      estado.textContent = "Imagen lista. Se guarda al presionar Guardar.";
    }

    function asignar(archivo) {
      var datos = new DataTransfer();
      datos.items.add(archivo);
      entrada.files = datos.files;
      previsualizar(archivo);
    }

    function detener() {
      if (flujo) flujo.getTracks().forEach(function (pista) { pista.stop(); });
      flujo = null;
      video.srcObject = null;
      panel.hidden = true;
    }

    entrada.addEventListener("change", function () {
      if (entrada.files[0]) previsualizar(entrada.files[0]);
    });

    captura.addEventListener("change", function () {
      if (captura.files[0]) asignar(captura.files[0]);
    });

    raiz.querySelector("[data-abrir-camara]").addEventListener("click", async function () {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        captura.click();
        return;
      }
      try {
        flujo = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        video.srcObject = flujo;
        panel.hidden = false;
        await video.play();
        estado.textContent = "";
      } catch (error) {
        detener();
        estado.textContent = "No se pudo abrir la cámara. Revisa el permiso del navegador o usa Subir imagen.";
        captura.click();
      }
    });

    raiz.querySelector("[data-cerrar-camara]").addEventListener("click", detener);

    raiz.querySelector("[data-capturar]").addEventListener("click", function () {
      var lienzo = document.createElement("canvas");
      lienzo.width = video.videoWidth;
      lienzo.height = video.videoHeight;
      lienzo.getContext("2d").drawImage(video, 0, 0);
      lienzo.toBlob(function (blob) {
        if (!blob) return;
        asignar(new File([blob], "camara.jpg", { type: "image/jpeg" }));
        detener();
      }, "image/jpeg", 0.9);
    });

    if (campoUrl) {
      campoUrl.addEventListener("input", function () {
        var valor = campoUrl.value.trim();
        if (/^https?:\/\//i.test(valor)) {
          entrada.value = "";
          mostrar(valor);
          estado.textContent = "";
        } else if (!entrada.files[0] && !valor) {
          ocultarVista();
        }
      });
    }

    vista.addEventListener("error", function () {
      if (!vista.getAttribute("src")) return;
      ocultarVista();
      estado.textContent = "No se pudo cargar esa imagen. Revisa el enlace.";
    });
  });
})();
