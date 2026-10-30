/* Toggle de tema claro/oscuro · Ciudad Escucha
   Persiste la preferencia en localStorage. Dash sirve assets/*.js automáticamente. */
(function () {
    var KEY = "ce-theme";

    function aplicar(tema) {
        var de = document.documentElement;
        if (tema === "light") {
            de.classList.add("light");
        } else {
            de.classList.remove("light");
        }
        var icono = document.getElementById("icono_tema");
        if (icono) {
            icono.className = tema === "light" ? "fa-solid fa-moon" : "fa-solid fa-sun";
        }
        // Avisa al backend para que el mapa use basemap claro u oscuro
        try {
            window.dash_clientside.set_props("store_tema", { data: tema });
        } catch (e) {
            /* Dash todavía no montó los componentes: se reintenta en el intervalo */
        }
    }

    function temaActual() {
        return document.documentElement.classList.contains("light") ? "light" : "dark";
    }

    // Aplicar preferencia guardada lo antes posible
    aplicar(localStorage.getItem(KEY) || "dark");

    // Delegación de clic (los componentes de Dash se re-renderizan)
    document.addEventListener("click", function (ev) {
        var btn = ev.target && ev.target.closest ? ev.target.closest("#btn_tema") : null;
        if (!btn) return;
        var nuevo = temaActual() === "light" ? "dark" : "light";
        localStorage.setItem(KEY, nuevo);
        aplicar(nuevo);
    });

    // Cuando Dash monta el layout, asegurar el icono, el tema y el store del backend
    var esperas = 0;
    var timer = setInterval(function () {
        var listo = document.getElementById("btn_tema") &&
                    window.dash_clientside && window.dash_clientside.set_props;
        if (listo) {
            aplicar(temaActual());
            clearInterval(timer);
        }
        if (++esperas > 200) clearInterval(timer);
    }, 100);
})();
