/* The Players page's interactive map: progressive enhancement over the
 * static SVG and the per-window tables attendance.py already renders.
 * Needs jsvectormap.min.js and vendor/world-merc.js loaded first (see
 * templates/stats_players.html); does nothing, leaving the static map
 * and tables exactly as they render without this file, if either is
 * missing, if the page has no #nm-worldmap-data, or if anything below
 * throws.
 *
 * Colours come straight from the page's own CSS custom properties: each
 * region/marker is given a literal `color-mix(in srgb, var(--nm-accent)
 * N%, var(--nm-rule-soft))` string as its fill, which the browser
 * resolves against whichever skin is loaded, so a theme change needs no
 * JS re-run. The four tiers mirror attendance.py's TIERS exactly. */
(function () {
  "use strict";

  var WINDOW_KEYS = ["active_7d", "active_30d", "active_365d", "ever"];
  var WINDOW_LABELS = ["this week", "this month", "this year", "ever"];
  var TIERS = [[0.5, 92], [0.2, 68], [0.05, 44], [0, 24]];

  // Countries/territories too small, or simply absent, in jsVectorMap's
  // world_merc atlas: shown as a circle marker at the capital (or a
  // central point for places with none) instead of a region fill.
  // Everything attendance.py's static map carries that the atlas does
  // not (checked against the vendored world-merc.js) is listed here, so
  // no country code a real export sends is ever silently dropped.
  var MARKERS = {
    ad: ["Andorra", 42.5063, 1.5218],
    ag: ["Antigua and Barbuda", 17.1274, -61.8468],
    ai: ["Anguilla", 18.2170, -63.0578],
    as: ["American Samoa", -14.2756, -170.7020],
    aw: ["Aruba", 12.5211, -69.9683],
    bb: ["Barbados", 13.0969, -59.6145],
    bh: ["Bahrain", 26.2285, 50.5860],
    bm: ["Bermuda", 32.2949, -64.7859],
    ck: ["Cook Islands", -21.2089, -159.7750],
    cv: ["Cape Verde", 14.9315, -23.5125],
    dm: ["Dominica", 15.3092, -61.3794],
    fm: ["Micronesia", 6.9248, 158.1611],
    fo: ["Faroe Islands", 62.0079, -6.7900],
    gd: ["Grenada", 12.0564, -61.7485],
    gf: ["French Guiana", 4.9372, -52.3260],
    gg: ["Guernsey", 49.4546, -2.5368],
    gi: ["Gibraltar", 36.1408, -5.3536],
    gp: ["Guadeloupe", 16.0074, -61.7056],
    gu: ["Guam", 13.4745, 144.7504],
    hk: ["Hong Kong", 22.3193, 114.1694],
    im: ["Isle of Man", 54.1509, -4.4800],
    je: ["Jersey", 49.1858, -2.1058],
    ki: ["Kiribati", 1.3291, 172.9790],
    km: ["Comoros", -11.7042, 43.2402],
    kn: ["Saint Kitts and Nevis", 17.3026, -62.7177],
    ky: ["Cayman Islands", 19.2869, -81.3674],
    lc: ["Saint Lucia", 14.0101, -60.9875],
    li: ["Liechtenstein", 47.1410, 9.5209],
    mc: ["Monaco", 43.7384, 7.4246],
    mh: ["Marshall Islands", 7.1164, 171.1858],
    mo: ["Macau", 22.1987, 113.5439],
    mp: ["Northern Mariana Islands", 15.1944, 145.7489],
    mq: ["Martinique", 14.6161, -61.0588],
    ms: ["Montserrat", 16.7923, -62.2113],
    mt: ["Malta", 35.8989, 14.5146],
    mu: ["Mauritius", -20.1609, 57.5012],
    mv: ["Maldives", 4.1755, 73.5093],
    nr: ["Nauru", -0.5477, 166.9209],
    nu: ["Niue", -19.0545, -169.9180],
    pf: ["French Polynesia", -17.5516, -149.5585],
    pm: ["Saint Pierre and Miquelon", 46.7850, -56.1820],
    pn: ["Pitcairn Islands", -25.0660, -130.1015],
    pw: ["Palau", 7.5006, 134.6242],
    re: ["Reunion", -20.8789, 55.4481],
    sc: ["Seychelles", -4.6191, 55.4513],
    sg: ["Singapore", 1.3521, 103.8198],
    sh: ["Saint Helena", -15.9387, -5.7168],
    sm: ["San Marino", 43.9424, 12.4578],
    st: ["Sao Tome and Principe", 0.3302, 6.7333],
    tc: ["Turks and Caicos Islands", 21.4612, -71.1419],
    to: ["Tonga", -21.1333, -175.2000],
    tv: ["Tuvalu", -8.5243, 179.1942],
    va: ["Vatican City", 41.9029, 12.4534],
    vc: ["Saint Vincent and the Grenadines", 13.1600, -61.2248],
    vg: ["British Virgin Islands", 18.4207, -64.6399],
    vi: ["United States Virgin Islands", 18.3419, -64.9307],
    wf: ["Wallis and Futuna", -13.2817, -176.1746],
    ws: ["Samoa", -13.8333, -171.7500],
    yt: ["Mayotte", -12.7806, 45.2278]
  };

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c];
    });
  }

  function fmt(n) {
    return (n || 0).toLocaleString("en-US");
  }

  function tierPct(value, top) {
    if (!value || !top) {
      return null;
    }
    var ratio = value / top;
    for (var i = 0; i < TIERS.length; i++) {
      if (ratio > TIERS[i][0]) {
        return TIERS[i][1];
      }
    }
    return null;
  }

  function fillFor(pct) {
    return pct == null ? "var(--nm-rule-soft)"
      : "color-mix(in srgb, var(--nm-accent) " + pct + "%, var(--nm-rule-soft))";
  }

  function init() {
    var box = document.querySelector(".nm-worldmap");
    var svg = box && box.querySelector("svg");
    var dataEl = document.getElementById("nm-worldmap-data");
    if (!box || !svg || !dataEl || typeof jsVectorMap === "undefined") {
      return;
    }
    var DATA;
    try {
      DATA = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }

    var radios = document.querySelectorAll('input[name="players-map"]');
    if (!radios.length) {
      return;
    }

    var markerCodes = Object.keys(MARKERS).sort();
    var markerConfig = markerCodes.map(function (code) {
      return { name: MARKERS[code][0], coords: [MARKERS[code][1], MARKERS[code][2]] };
    });
    var markerIndex = {};
    markerCodes.forEach(function (code, i) { markerIndex[code] = i; });

    var canvas = document.createElement("div");
    canvas.className = "nm-worldmap-js";
    canvas.id = "nm-worldmap-canvas";
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "Interactive world map, coloured by players seen from each country");

    var controls = document.createElement("div");
    controls.className = "nm-map-controls";
    var resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "nm-map-reset";
    resetBtn.textContent = "Reset view";
    controls.appendChild(resetBtn);

    var map, currentKey = "ever";

    function checkedWindow() {
      for (var i = 0; i < radios.length; i++) {
        if (radios[i].checked) {
          return WINDOW_KEYS[i] || "ever";
        }
      }
      return "ever";
    }

    function windowTotal(key) {
      var sum = 0;
      for (var code in DATA) {
        sum += DATA[code][key] || 0;
      }
      return sum;
    }

    function recolor(key) {
      currentKey = key;
      var top = 0;
      for (var code in DATA) {
        if ((DATA[code][key] || 0) > top) {
          top = DATA[code][key];
        }
      }
      Object.keys(DATA).forEach(function (code) {
        var pct = tierPct(DATA[code][key], top);
        var fill = fillFor(pct);
        var region = map.regions[code.toUpperCase()];
        if (region) {
          region.element.setStyle("fill", fill);
        } else if (code in markerIndex) {
          var m = map._markers[markerIndex[code]];
          if (m) {
            m.element.setStyle("fill", fill);
          }
        }
      });
      if (map._tooltip) {
        map._tooltip.hide();
      }
    }

    function tooltipHtml(code, name) {
      var d = DATA[code];
      if (!d) {
        return "<b>" + esc(name) + "</b><br>No players recorded.";
      }
      var total = windowTotal(currentKey);
      var share = total ? (100 * (d[currentKey] || 0) / total) : 0;
      var shareText = share > 0 ? (share >= 1 ? share.toFixed(0) : share.toFixed(1)) : "0";
      return "<b>" + esc(name) + "</b><br>" +
        fmt(d.ever) + " ever &middot; " + fmt(d.active_7d) + " / 7d &middot; " +
        fmt(d.active_30d) + " / 30d &middot; " + fmt(d.active_365d) + " / 365d<br>" +
        shareText + "% of all seen " + WINDOW_LABELS[WINDOW_KEYS.indexOf(currentKey)];
    }

    function showTooltip(code, isMarker, event) {
      if (!map._tooltip) {
        return;
      }
      var name = isMarker ? MARKERS[code][0] : (map._mapData.paths[code.toUpperCase()] || {}).name || code;
      map._tooltip.text(tooltipHtml(code, name), true);
      if (event && event.pageX != null) {
        map._tooltip.css({ left: (event.pageX + 8) + "px", top: (event.pageY - 28) + "px" });
      }
      map._tooltip.show();
    }

    // The container must already be in the document, sized by CSS,
    // before construction: jsVectorMap reads its offsetWidth/Height
    // once at init and a detached node measures zero, leaving the map
    // permanently at scale(0).
    box.insertBefore(canvas, svg);
    box.appendChild(controls);

    try {
      map = new jsVectorMap({
        selector: canvas,
        map: "world_merc",
        zoomButtons: true,
        zoomOnScroll: true,
        zoomMax: 10,
        bindTouchEvents: true,
        showTooltip: true,
        regionsSelectable: false,
        markersSelectable: false,
        backgroundColor: "transparent",
        regionStyle: {
          initial: { fill: "var(--nm-rule-soft)", stroke: "var(--nm-bg)", strokeWidth: 0.6 },
          hover: { fillOpacity: 0.75, cursor: "pointer" }
        },
        markerStyle: {
          initial: { r: 5, fill: "var(--nm-rule-soft)", stroke: "var(--nm-bg)", strokeWidth: 1, fillOpacity: 1 },
          hover: { fillOpacity: 0.75, cursor: "pointer" }
        },
        markers: markerConfig,
        onRegionTooltipShow: function (event, tooltip, code) {
          showTooltip(code.toLowerCase(), false, event);
        },
        onMarkerTooltipShow: function (event, tooltip, index) {
          showTooltip(markerCodes[index], true, event);
        },
        onRegionClick: function (event, code) {
          showTooltip(code.toLowerCase(), false, event);
        },
        onMarkerClick: function (event, index) {
          showTooltip(markerCodes[index], true, event);
        }
      });
    } catch (e) {
      canvas.remove();
      controls.remove();
      return;
    }

    svg.style.display = "none";

    recolor(checkedWindow());

    radios.forEach(function (radio) {
      radio.addEventListener("change", function () {
        if (radio.checked) {
          recolor(checkedWindow());
        }
      });
    });

    resetBtn.addEventListener("click", function () {
      map.reset();
      map.addMarkers(markerConfig);
      recolor(currentKey);
    });

    // Tapping empty space (not a region/marker) hides any open tooltip.
    canvas.addEventListener("touchend", function (event) {
      var el = event.target;
      if (!el.closest || !el.closest(".jvm-region, .jvm-marker")) {
        if (map._tooltip) {
          map._tooltip.hide();
        }
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
