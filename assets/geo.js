/* Geolocalización del formulario de reportes · Ciudad Escucha
   El botón #btn_gps pide la posición al navegador y la publica en el store
   `store_gps`; el backend (callback fijar_punto) la convierte en el punto del
   reporte y preselecciona la comuna más cercana.

   `navigator.geolocation` solo funciona en contextos seguros (HTTPS o
   localhost), por eso en la versión publicada detrás del túnel funciona. */
(function () {
    var pidiendo = false;

    function publicar(datos) {
        try {
            window.dash_clientside.set_props("store_gps", {
                data: Object.assign({ts: Date.now()}, datos)
            });
        } catch (e) {
            console.error("No se pudo publicar la ubicación:", e);
        }
    }

    function mensaje(texto) {
        var el = document.getElementById("txt_geo");
        if (el) el.textContent = texto;
    }

    document.addEventListener("click", function (ev) {
        var btn = ev.target && ev.target.closest ? ev.target.closest("#btn_gps") : null;
        if (!btn || pidiendo) return;

        if (!navigator.geolocation) {
            mensaje("⚠️ Este navegador no permite geolocalización; marca el punto en el mapa.");
            return;
        }
        pidiendo = true;
        mensaje("Buscando tu ubicación…");
        navigator.geolocation.getCurrentPosition(
            function (pos) {
                pidiendo = false;
                publicar({lat: pos.coords.latitude, lon: pos.coords.longitude,
                          precision: pos.coords.accuracy});
            },
            function (err) {
                pidiendo = false;
                var motivos = {
                    1: "permiso denegado (actívalo en el candado de la barra de direcciones)",
                    2: "posición no disponible",
                    3: "se agotó el tiempo de espera"
                };
                publicar({error: motivos[err.code] || err.message || "error desconocido"});
            },
            {enableHighAccuracy: true, timeout: 12000, maximumAge: 0}
        );
    });
})();
