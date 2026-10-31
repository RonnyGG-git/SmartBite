(function () {
  const urls = window.SIMULADOR_URLS;
  const $ = (id) => document.getElementById(id);
  const csrf = document.querySelector("input[name=csrfmiddlewaretoken]").value;
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  const SILENCIO_MS = 8000;

  let llamada = null;
  let escuchando = false;
  let reconocedor = null;
  let temporizadorSilencio = null;
  let huboResultado = false;

  function ruta(plantilla, id) {
    return plantilla.replace("/0/", "/" + id + "/");
  }

  function mostrar(rol, texto) {
    const nodo = document.createElement("div");
    nodo.className = "sim-msg";
    nodo.dataset.rol = rol;
    nodo.textContent = texto;
    $("sim-log").appendChild(nodo);
    $("sim-log").scrollTop = $("sim-log").scrollHeight;
  }

  function estado(texto) {
    $("sim-estado").textContent = texto;
  }

  async function post(url, datos) {
    const respuesta = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(datos || {}),
    });
    if (!respuesta.ok) throw new Error("HTTP " + respuesta.status);
    return respuesta.json();
  }

  function voz() {
    const voces = speechSynthesis.getVoices();
    for (const idioma of ["es-CO", "es-419", "es-MX", "es-US", "es"]) {
      const encontrada = voces.find((v) => v.lang && v.lang.replace("_", "-").startsWith(idioma));
      if (encontrada) return encontrada;
    }
    return null;
  }

  function hablar(texto) {
    return new Promise((resolver) => {
      if (!("speechSynthesis" in window)) return resolver();
      speechSynthesis.cancel();
      const frase = new SpeechSynthesisUtterance(texto);
      const elegida = voz();
      if (elegida) frase.voice = elegida;
      frase.lang = elegida ? elegida.lang : "es-CO";
      frase.rate = 1.02;
      frase.onend = resolver;
      frase.onerror = resolver;
      speechSynthesis.speak(frase);
      if ($("sim-interrumpir").checked) escuchar();
    });
  }

  function habilitar(activa) {
    $("sim-llamar").disabled = activa;
    $("sim-colgar").disabled = !activa;
    $("sim-texto").disabled = !activa;
    $("sim-enviar").disabled = !activa;
    $("sim-mic").disabled = !activa || !Reconocimiento;
  }

  async function atender(datos) {
    mostrar("agente", datos.texto);
    estado("Llamada #" + datos.llamada + " · " + datos.fase + (datos.orden ? " · orden #" + datos.orden : ""));
    await hablar(datos.texto);
    if (datos.finalizar) {
      terminar("La llamada terminó.");
      return;
    }
    if (Reconocimiento && $("sim-mic").getAttribute("aria-pressed") === "true") escuchar();
  }

  async function enviar(texto) {
    if (!llamada) return;
    if (texto) mostrar("cliente", texto);
    try {
      await atender(await post(ruta(urls.turno, llamada), { texto: texto }));
    } catch (error) {
      mostrar("sistema", "Error de conexión con el servidor (" + error.message + ").");
    }
  }

  function terminar(mensaje) {
    detenerEscucha();
    speechSynthesis.cancel();
    llamada = null;
    habilitar(false);
    $("sim-mic").setAttribute("aria-pressed", "false");
    mostrar("sistema", mensaje);
    estado("Sin llamada");
  }

  function detenerEscucha() {
    clearTimeout(temporizadorSilencio);
    if (reconocedor && escuchando) reconocedor.abort();
    escuchando = false;
  }

  function escuchar() {
    if (!Reconocimiento || !llamada || escuchando) return;
    reconocedor = new Reconocimiento();
    reconocedor.lang = "es-CO";
    reconocedor.interimResults = false;
    reconocedor.maxAlternatives = 1;
    huboResultado = false;
    reconocedor.onspeechstart = () => {
      if ($("sim-interrumpir").checked) speechSynthesis.cancel();
      clearTimeout(temporizadorSilencio);
    };
    reconocedor.onresult = (evento) => {
      huboResultado = true;
      const texto = evento.results[0][0].transcript.trim();
      detenerEscucha();
      enviar(texto);
    };
    reconocedor.onerror = (evento) => {
      if (evento.error === "not-allowed") mostrar("sistema", "El navegador bloqueó el micrófono.");
    };
    reconocedor.onend = () => {
      escuchando = false;
    };
    temporizadorSilencio = setTimeout(() => {
      if (!huboResultado && llamada && !speechSynthesis.speaking) {
        detenerEscucha();
        enviar("");
      }
    }, SILENCIO_MS);
    escuchando = true;
    reconocedor.start();
  }

  $("sim-llamar").addEventListener("click", async () => {
    $("sim-log").innerHTML = "";
    try {
      const datos = await post(urls.iniciar, { sucursal: $("sim-sucursal").value, telefono: $("sim-telefono").value });
      llamada = datos.llamada;
      habilitar(true);
      if (Reconocimiento) $("sim-mic").setAttribute("aria-pressed", "true");
      await atender(datos);
    } catch (error) {
      mostrar("sistema", "No se pudo iniciar la llamada (" + error.message + ").");
    }
  });

  $("sim-colgar").addEventListener("click", async () => {
    const id = llamada;
    terminar("Colgaste la llamada.");
    if (id) await post(ruta(urls.colgar, id)).catch(() => {});
  });

  $("sim-mic").addEventListener("click", () => {
    const activo = $("sim-mic").getAttribute("aria-pressed") === "true";
    $("sim-mic").setAttribute("aria-pressed", String(!activo));
    if (activo) detenerEscucha();
    else escuchar();
  });

  $("sim-form").addEventListener("submit", (evento) => {
    evento.preventDefault();
    const texto = $("sim-texto").value.trim();
    $("sim-texto").value = "";
    detenerEscucha();
    speechSynthesis.cancel();
    enviar(texto);
  });

  if (!Reconocimiento) mostrar("sistema", "Este navegador no tiene reconocimiento de voz; usa la caja de texto.");
  if ("speechSynthesis" in window) speechSynthesis.getVoices();
})();
