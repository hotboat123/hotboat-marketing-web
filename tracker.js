(function () {
  'use strict';

  // --- Sesión (una por pestaña) ---
  var _sid;
  try {
    _sid = sessionStorage.getItem('hb_sid');
    if (!_sid) {
      _sid = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2) + Date.now().toString(36);
      sessionStorage.setItem('hb_sid', _sid);
    }
  } catch (e) { _sid = Math.random().toString(36).slice(2); }

  // --- Visitante nuevo vs recurrente ---
  var _returning;
  try {
    _returning = !!localStorage.getItem('hb_visited');
    localStorage.setItem('hb_visited', '1');
  } catch (e) { _returning = false; }

  // --- Función central de envío ---
  function _send(event, extra) {
    try {
      var payload = JSON.stringify({
        event:        event,
        extra:        extra || null,
        session_id:   _sid,
        is_returning: _returning,
        lang:         document.documentElement.lang || 'es-CL',
        referrer:     (document.referrer || '').substring(0, 200),
      });
      fetch('/api/track', {
        method:    'POST',
        headers:   { 'Content-Type': 'application/json' },
        body:      payload,
        keepalive: true,
      }).catch(function () {});
    } catch (e) {}
  }

  // --- Visita inicial ---
  _send('page_visit');

  // --- Vistas de sección (cada una se dispara una sola vez) ---
  var SECTIONS = ['incluye', 'precio', 'resenas', 'fotos', 'faq', 'ubicacion'];
  if ('IntersectionObserver' in window) {
    var _obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          _send('view_' + entry.target.id);
          _obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.25 });
    SECTIONS.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) _obs.observe(el);
    });
  }

  // --- Clicks en CTAs ---
  document.addEventListener('click', function (e) {
    var el = e.target.closest('a[href], button');
    if (!el) return;
    var href = el.getAttribute('href') || '';

    if (href.indexOf('wa.me') !== -1 || el.classList.contains('btn-wa')) {
      _send('click_whatsapp');
    } else if (
      href.indexOf('booking') !== -1 ||
      href.indexOf('whatsapp.hotboat') !== -1 ||
      (el.getAttribute('data-i18n') === 'btn-book')
    ) {
      _send('click_reservar');
    } else if (href.indexOf('instagram') !== -1) {
      _send('click_instagram');
    } else if (href.indexOf('google.com/maps') !== -1) {
      _send('click_maps');
    }
  }, true);

  // --- Cambio de idioma ---
  var _dropdown = document.getElementById('lang-dropdown');
  if (_dropdown) {
    _dropdown.addEventListener('click', function (e) {
      var li = e.target.closest('li[data-lang]');
      if (li) _send('lang_change', li.dataset.lang);
    });
  }

  // --- FAQ abierto (señal de interés en objeciones) ---
  document.querySelectorAll('details.faq').forEach(function (det) {
    det.addEventListener('toggle', function () {
      if (det.open) {
        var q = det.querySelector('[data-i18n]');
        _send('faq_open', q ? q.getAttribute('data-i18n') : null);
      }
    });
  });

  // --- Salida (sendBeacon, más fiable que unload) ---
  window.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      var d = JSON.stringify({
        event: 'exit', extra: null,
        session_id: _sid, is_returning: _returning,
        lang: document.documentElement.lang || 'es-CL', referrer: '',
      });
      try {
        navigator.sendBeacon('/api/track', new Blob([d], { type: 'application/json' }));
      } catch (e) {}
    }
  });

})();
