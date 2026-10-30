/* Clic sobre el mini-mapa del formulario → coordenadas · Ciudad Escucha
   Plotly no emite `plotly_click` cuando se hace clic en el fondo de un mapa
   (Scattermap): solo lo hace sobre los marcadores. Por eso el mapa lleva una
   capa transparente encima (#capa_clic_mapa) y aquí se traduce el píxel
   pulsado a latitud/longitud con la proyección Web Mercator.

   El mapa está configurado sin arrastrar ni hacer zoom (dragmode: false), así
   que el centro y el zoom de la figura son siempre los que se ven en pantalla
   y la conversión píxel → coordenada es exacta.

   El resultado se publica en `store_click`; el backend decide la comuna y
   pinta el marcador. */
(function () {
    function numero(v, alt) {
        return typeof v === "number" && isFinite(v) ? v : alt;
    }

    function pixelAGeo(gd, px, py) {
        var mapa = (gd._fullLayout && gd._fullLayout.map) || gd.layout.map || {};
        var centro = mapa.center || {};
        var lat0 = numero(centro.lat, 4.1425);
        var lon0 = numero(centro.lon, -73.6294);
        var zoom = numero(mapa.zoom, 12);
        var rect = gd.getBoundingClientRect();
        var ancho = rect.width, alto = rect.height;
        if (!ancho || !alto) return null;

        // maplibre usa teselas de 512 px: mundo = 512 * 2^zoom píxeles
        var mundo = 512 * Math.pow(2, zoom);
        var lon = lon0 + (px - ancho / 2) * 360 / mundo;
        var yCentro = (1 - Math.log(Math.tan(Math.PI / 4 + lat0 * Math.PI / 360)) / Math.PI) / 2;
        var y = yCentro + (py - alto / 2) / mundo;
        var lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180 / Math.PI;
        return {lat: lat, lon: lon};
    }

    document.addEventListener("click", function (ev) {
        var capa = ev.target && ev.target.closest ? ev.target.closest("#capa_clic_mapa") : null;
        if (!capa) return;
        var caja = capa.parentElement;
        var gd = caja && caja.querySelector(".js-plotly-plot");
        if (!gd) return;
        var rect = gd.getBoundingClientRect();
        var punto = pixelAGeo(gd, ev.clientX - rect.left, ev.clientY - rect.top);
        if (!punto) return;
        try {
            window.dash_clientside.set_props("store_click", {
                data: {lat: punto.lat, lon: punto.lon, ts: Date.now()}
            });
        } catch (e) {
            console.error("No se pudo enviar el punto del mapa:", e);
        }
    }, true);
})();
