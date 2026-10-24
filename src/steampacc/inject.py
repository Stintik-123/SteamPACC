'''Код, внедряемый в страницы магазина Steam.

SteamPACC подключается к интерфейсу клиента Steam по протоколу DevTools
и добавляет этот сценарий на страницы магазина. Сценарий сам находит
открытую игру (по адресу страницы), запрашивает цены через официальный
API магазина — прямо изнутри страницы, тем же запросом, каким пользуется
сам Steam, — и дорисовывает блок с ценами выбранных регионов под
карточкой покупки. Стиль блока повторяет оформление магазина.

Ограничения намеренные: сценарий ничего не отправляет наружу, не меняет
поведение кнопок магазина и не обращается к аккаунту.
'''

from __future__ import annotations


def _style(name: str, css: str) -> str:
    '''Собирает JS-строку присваивания cssText из python-строки CSS.'''
    return name + ".style.cssText = '" + css + "';"


#: Код валюты -> код региона магазина (cc), как в prices.py.
_CC_MAP_JS = (
    'var CC = {RUB:"ru", USD:"us", EUR:"de", GBP:"gb", JPY:"jp", KRW:"kr", '
    'INR:"in", TRY:"tr", UAH:"ua", KZT:"kz", PLN:"pl", BRL:"br", AUD:"au", '
    'CAD:"ca", SEK:"se", CNY:"cn"};'
)

#: Код валюты -> символ.
_SYMBOLS_JS = (
    'var SYM = {RUB:"\\u20BD", USD:"$", EUR:"\\u20AC", GBP:"\\u00A3", '
    'JPY:"\\u00A5", KRW:"\\u20A9", INR:"\\u20B9", TRY:"\\u20BA", '
    'UAH:"\\u20B4", KZT:"\\u20B8", PLN:"z\\u0142", BRL:"R$", AUD:"A$", '
    'CAD:"C$", SEK:"kr", CNY:"\\u00A5"};'
)

#: CSS блоков. В Python-строках двойные кавычки пишутся свободно,
#: поэтому шрифт задаётся как есть: font-family:"Motiva Sans".
_CSS_BOX = (
    'margin:8px 0 0; padding:10px 14px;'
    ' background:linear-gradient(to bottom, rgba(38,49,64,0.95), rgba(23,32,43,0.95));'
    ' border:1px solid #2a475e; border-radius:3px;'
    ' font-family:"Motiva Sans", Arial, sans-serif; font-size:13px;'
    ' color:#8f98a0; text-align:left;'
)
_CSS_HEADER = (
    'display:block; margin-bottom:6px; color:#66c0f4; font-size:11px;'
    ' text-transform:uppercase; letter-spacing:0.5px; font-weight:600;'
)
_CSS_ROW = 'display:flex; justify-content:space-between; gap:16px; padding:2px 0; line-height:18px;'
_CSS_LABEL = 'color:#8f98a0;'
_CSS_PRICE = 'color:#c6d4df; white-space:nowrap;'
_CSS_OLD = 'color:#7c8c9c; text-decoration:line-through; margin-right:6px; font-size:12px;'
_CSS_DISCOUNT = 'background:#4c6b22; color:#beee11; font-size:11px; padding:0 5px; border-radius:2px; margin-right:6px;'

_HEADER_TEXT = '"\\u0426\\u0435\\u043D\\u044B \\u0432 \\u0434\\u0440\\u0443\\u0433\\u0438\\u0445 \\u0440\\u0435\\u0433\\u0438\\u043E\\u043D\\u0430\\u0445"'
_FREE_TEXT = '"\\u0411\\u0435\\u0441\\u043F\\u043B\\u0430\\u0442\\u043D\\u043E"'
_UNAVAILABLE_TEXT = (
    '"\\u041D\\u0435\\u0434\\u043E\\u0441\\u0442\\u0443\\u043F\\u043D\\u043E '
    '\\u0432 \\u044D\\u0442\\u043E\\u043C \\u0440\\u0435\\u0433\\u0438\\u043E\\u043D\\u0435"'
)

#: Сценарий целиком. Точка входа для настроек — window.SteamPACC_configure.
INJECTED_SCRIPT = r'''
(function () {
  'use strict';
  if (window.__STEAMPACC_ACTIVE__) { return; }
  window.__STEAMPACC_ACTIVE__ = true;

  __CC_MAP__
  __SYMBOLS__
  var cfg = { currencies: ['RUB', 'USD', 'EUR'] };
  var TTL = 15 * 60 * 1000;
  // Версия кэша: при изменении формата запросов старые записи игнорируются.
  var CACHE_VERSION = 'v2';

  function appId() {
    var m = location.href.match(/\/app\/(\d+)/);
    return m ? m[1] : null;
  }

  function cacheKey(appid, code) { return CACHE_VERSION + ':steampacc:' + appid + ':' + code; }

  function cacheGet(appid, code) {
    try {
      var raw = sessionStorage.getItem(cacheKey(appid, code));
      if (!raw) { return undefined; }
      var obj = JSON.parse(raw);
      if (Date.now() - obj.t > TTL) { return undefined; }
      return obj.p;
    } catch (e) { return undefined; }
  }

  function cacheSet(appid, code, p) {
    try {
      sessionStorage.setItem(cacheKey(appid, code), JSON.stringify({ t: Date.now(), p: p }));
    } catch (e) { }
  }

  function fmt(cents, currency) {
    if (cents == null) { return '\u2014'; }
    var value = cents / 100;
    var text = value.toLocaleString('ru-RU', {
      minimumFractionDigits: value % 1 ? 2 : 0,
      maximumFractionDigits: 2
    });
    return text + ' ' + (SYM[currency] || currency || '');
  }

  function fetchOne(appid, code) {
    var cached = cacheGet(appid, code);
    if (cached !== undefined) { return Promise.resolve(cached); }
    var cc = CC[code] || code.toLowerCase();
    var url = '/api/appdetails?appids=' + appid + '&cc=' + cc;
    return fetch(url, { credentials: 'omit' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var entry = data && data[appid];
        var p = { none: true };
        if (entry && entry.success && entry.data) {
          var ov = entry.data.price_overview;
          if (ov) {
            p = { currency: ov.currency, final: ov.final, initial: ov.initial,
                  discount: ov.discount_percent, free: false };
          } else if (entry.data.is_free) {
            p = { free: true };
          }
        }
        cacheSet(appid, code, p);
        return p;
      })
      .catch(function () { return null; });
  }

  function ensureBox() {
    var host = document.querySelector('.game_area_purchase_game');
    if (!host) { return null; }
    var box = document.getElementById('steampacc_prices');
    if (box) { return box; }
    box = document.createElement('div');
    box.id = 'steampacc_prices';
    __BOX__
    host.parentNode.insertBefore(box, host.nextSibling);
    return box;
  }

  function row(code, p, best) {
    var label = document.createElement('span');
    __LABEL__
    label.textContent = code;
    var value = document.createElement('span');
    __PRICE__
    if (best) {
      value.style.color = '#beee11';
      value.title = '\u0421\u0430\u043C\u0430\u044F \u043D\u0438\u0437\u043A\u0430\u044F \u0446\u0435\u043D\u0430';
    }
    if (p === null) {
      value.textContent = '\u2026';
    } else if (p.none) {
      value.textContent = __UNAVAILABLE__;
      value.style.color = '#5c6672';
    } else if (p.free) {
      value.textContent = __FREE__;
    } else {
      if (p.discount && p.initial && p.initial > p.final) {
        var badge = document.createElement('span');
        __DISCOUNT__
        badge.textContent = '-' + p.discount + '%';
        value.appendChild(badge);
        var old = document.createElement('span');
        __OLD__
        old.textContent = fmt(p.initial, p.currency);
        value.appendChild(old);
      }
      value.appendChild(document.createTextNode(fmt(p.final, p.currency)));
    }
    var line = document.createElement('div');
    __ROW__
    line.appendChild(label);
    line.appendChild(value);
    return line;
  }

  function header() {
    var el = document.createElement('span');
    __HEADER__
    el.textContent = __TITLE__;
    return el;
  }

  function render(appid, rows) {
    var box = ensureBox();
    if (!box) { return; }
    box.innerHTML = '';
    box.appendChild(header());
    // Самая низкая доступная цена выделяется зелёным, как скидка в Steam.
    var best = null;
    rows.forEach(function (pair) {
      var p = pair[1];
      if (p && !p.none && !p.free && p.final != null) {
        if (best === null || p.final < best) { best = p.final; }
      }
    });
    rows.forEach(function (pair) {
      var p = pair[1];
      var isBest = best !== null && p && !p.none && !p.free && p.final === best &&
                   rows.filter(function (other) {
                     var q = other[1];
                     return q && !q.none && !q.free && q.final === best;
                   }).length === 1;
      box.appendChild(row(pair[0], p, isBest));
    });
  }

  var lastUrl = null;

  function update() {
    var box = ensureBox();
    if (!box) { return; }
    var url = location.href;
    if (url === lastUrl) { return; }
    lastUrl = url;
    // Переключатель DLC привязан к странице: при переходе собирается заново.
    var oldDlc = document.getElementById('steampacc_dlc_toggle');
    if (oldDlc) { oldDlc.parentNode.removeChild(oldDlc); }
    var appid = appId();
    if (!appid) {
      box.style.display = 'none';
      return;
    }
    box.style.display = '';
    box.innerHTML = '';
    box.appendChild(header());
    var tasks = cfg.currencies.map(function (code) {
      return fetchOne(appid, code).then(function (p) { return [code, p]; });
    });
    Promise.all(tasks).then(function (rows) {
      render(appid, rows);
    });
  }

  /* ---- Цены DLC: строчка цен под каждым DLC, сворачивается ---- */

  function dlcRows() {
    var rows = document.querySelectorAll('.game_area_dlc_row[data-ds-appid]');
    var result = [];
    rows.forEach(function (row) {
      var id = (row.getAttribute('data-ds-appid') || '').split(',')[0];
      if (/^\d+$/.test(id)) { result.push({ row: row, id: id }); }
    });
    return result.slice(0, 40);
  }

  function priceLine(id) {
    var line = document.createElement('div');
    line.className = 'steampacc_dlc_line';
    line.setAttribute('data-steampacc-id', id);
    line.style.cssText = 'font-size:12px; color:#66c0f4; padding:2px 4px 6px;'
        + ' text-align:left; line-height:15px;';
    line.textContent = '\u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430\u2026';
    return line;
  }

  function fillLine(line, id) {
    var codes = cfg.currencies.slice(0, 3);
    var tasks = codes.map(function (c) { return fetchOne(id, c); });
    Promise.all(tasks).then(function (prices) {
      var parts = [];
      var unavailable = true;
      codes.forEach(function (code, i) {
        var p = prices[i];
        if (p && !p.none && !p.free && p.final != null) {
          unavailable = false;
          parts.push(code + ' ' + fmt(p.final, p.currency));
        }
      });
      if (unavailable) {
        line.textContent = __UNAVAILABLE__;
        line.style.color = '#5c6672';
      } else {
        line.textContent = parts.join('  \u00B7  ');
      }
    });
  }

  function buildDlcToggle() {
    var rows = dlcRows();
    if (!rows.length) { return; }
    var existing = document.getElementById('steampacc_dlc_toggle');
    if (existing) { return; }
    var toggle = document.createElement('div');
    toggle.id = 'steampacc_dlc_toggle';
    toggle.style.cssText = 'margin:6px 0; font-size:13px; color:#66c0f4;'
        + ' cursor:pointer; user-select:none; text-align:left;'
        + ' font-family:"Motiva Sans", Arial, sans-serif;';
    toggle.textContent = '\u25B8 \u0426\u0435\u043D\u044B DLC \u0432 \u0434\u0440\u0443\u0433\u0438\u0445 \u0440\u0435\u0433\u0438\u043E\u043D\u0430\u0445 (' + rows.length + ')';
    var open = false;
    toggle.addEventListener('click', function () {
      open = !open;
      toggle.textContent = (open ? '\u25BE ' : '\u25B8 ') +
        '\u0426\u0435\u043D\u044B DLC \u0432 \u0434\u0440\u0443\u0433\u0438\u0445 \u0440\u0435\u0433\u0438\u043E\u043D\u0430\u0445 (' + rows.length + ')';
      rows.forEach(function (item) {
        var row = item.row;
        if (open) {
          var line = row.querySelector('.steampacc_dlc_line');
          if (!line) {
            line = priceLine(item.id);
            row.appendChild(line);
          }
          if (line.textContent === '\u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430\u2026') {
            fillLine(line, item.id);
          }
          line.style.display = '';
        } else {
          var old = row.querySelector('.steampacc_dlc_line');
          if (old) { old.style.display = 'none'; }
        }
      });
    });
    var first = rows[0].row;
    first.parentNode.insertBefore(toggle, first);
  }

  window.SteamPACC_configure = function (next) {
    if (next && next.currencies && next.currencies.length) {
      cfg.currencies = next.currencies.slice();
    }
    lastUrl = null;
    update();
  };

  setInterval(update, 1000);
  // Строки DLC появляются в DOM позже основного блока: пробуем достроить.
  setInterval(function () {
    if (document.getElementById('steampacc_dlc_toggle')) { return; }
    if (!/\/app\/(\d+)/.test(location.href)) { return; }
    if (document.querySelector('.game_area_dlc_row[data-ds-appid]')) {
      buildDlcToggle();
    }
  }, 1000);
  setTimeout(update, 0);
  document.addEventListener('DOMContentLoaded', function () { update(); });
})();
'''.replace('__CC_MAP__', _CC_MAP_JS) \
   .replace('__SYMBOLS__', _SYMBOLS_JS) \
   .replace('__BOX__', _style('box', _CSS_BOX)) \
   .replace('__LABEL__', _style('label', _CSS_LABEL)) \
   .replace('__PRICE__', _style('value', _CSS_PRICE)) \
   .replace('__OLD__', _style('old', _CSS_OLD)) \
   .replace('__DISCOUNT__', _style('badge', _CSS_DISCOUNT)) \
   .replace('__ROW__', _style('line', _CSS_ROW)) \
   .replace('__HEADER__', _style('el', _CSS_HEADER)) \
   .replace('__TITLE__', _HEADER_TEXT) \
   .replace('__FREE__', _FREE_TEXT) \
   .replace('__UNAVAILABLE__', _UNAVAILABLE_TEXT) \
   .replace('__TOGGLE__', "'" + _CSS_HEADER + "'")

#: CSS панели настроек в стиле Steam.
_SETTINGS_CSS = (
    'position:fixed; z-index:99999; overflow-y:auto; padding:16px 18px; display:none;'
    ' background:linear-gradient(to bottom, #1b2838, #141e2d);'
    ' font-family:"Motiva Sans", Arial, sans-serif;'
    ' font-size:13px; color:#c6d4df; box-shadow:0 4px 16px rgba(0,0,0,0.5);'
)
_SETTINGS_TITLE_CSS = (
    'display:block; color:#66c0f4; font-size:12px; font-weight:600;'
    ' text-transform:uppercase; letter-spacing:0.5px; margin-bottom:10px;'
)
_SETTINGS_LABEL_CSS = (
    'display:flex; align-items:center; gap:8px; padding:4px 0; cursor:pointer;'
    ' color:#c6d4df;'
)

#: Сценарий для окна настроек Steam.
#: Добавляет свой пункт «SteamPACC» в левое меню настроек (клоном стиля
#: штатного пункта) и по клику показывает панель регионов поверх области
#: содержимого. Выбор галочек передаётся программе через биндинг
#: SteamPACC_set. Если разметка Steam не опознана, панель показывается
#: в углу окна как запасной вариант.
INJECTED_SETTINGS_SCRIPT = r'''
(function () {
  'use strict';
  if (window.__STEAMPACC_SETTINGS__) { return; }
  window.__STEAMPACC_SETTINGS__ = true;

  var cfg = { currencies: ['RUB', 'USD', 'EUR'] };
  var SYM = {RUB:"\u20BD", USD:"$", EUR:"\u20AC", GBP:"\u00A3", JPY:"\u00A5",
             KRW:"\u20A9", INR:"\u20B9", TRY:"\u20BA", UAH:"\u20B4",
             KZT:"\u20B8", PLN:"z\u0142", BRL:"R$", AUD:"A$", CAD:"C$",
             SEK:"kr", CNY:"\u00A5"};
  var ALL = Object.keys(SYM);

  function send() {
    if (typeof window.SteamPACC_set === 'function') {
      window.SteamPACC_set(JSON.stringify({ currencies: cfg.currencies }));
    }
  }

  function buildCheckboxes(host) {
    ALL.forEach(function (code) {
      var label = document.createElement('label');
      label.style.cssText = __SET_LABEL__;
      var box = document.createElement('input');
      box.type = 'checkbox';
      box.value = code;
      box.checked = cfg.currencies.indexOf(code) >= 0;
      box.addEventListener('change', function () {
        var picked = ALL.filter(function (c) {
          var b = host.querySelector('input[value=' + c + ']');
          return b && b.checked;
        });
        cfg.currencies = picked.length ? picked : ['RUB', 'USD', 'EUR'];
        send();
      });
      var text = document.createElement('span');
      text.textContent = code + '  ' + SYM[code];
      label.appendChild(box);
      label.appendChild(text);
      host.appendChild(label);
    });
  }

  function makePanel(id) {
    var el = document.createElement('div');
    el.id = id;
    el.style.cssText = __SET_PANEL__;
    var title = document.createElement('span');
    title.style.cssText = __SET_TITLE__;
    title.textContent = 'SteamPACC \u2014 \u0440\u0435\u0433\u0438\u043E\u043D\u044B \u0446\u0435\u043D \u0432 \u043C\u0430\u0433\u0430\u0437\u0438\u043D\u0435';
    el.appendChild(title);
    buildCheckboxes(el);
    return el;
  }

  /* ---- Нативная встройка: пункт в меню настроек ---- */

  var navItem = null;
  var overlay = null;

  function showOverlay() {
    var sample = null;
    var all = document.querySelectorAll('[id$=_Content]');
    Array.prototype.forEach.call(all, function (c) {
      if (!sample && c.offsetParent !== null && (c.textContent || '').length > 0) {
        sample = c;
      }
    });
    if (!sample) { return false; }
    var rect = sample.getBoundingClientRect();
    overlay.style.top = rect.top + 'px';
    overlay.style.left = rect.left + 'px';
    overlay.style.width = rect.width + 'px';
    overlay.style.height = rect.height + 'px';
    overlay.style.display = 'block';
    return true;
  }

  function hideOverlay() {
    if (!overlay) { return; }
    overlay.style.display = 'none';
    if (navItem) {
      navItem.setAttribute('aria-selected', 'false');
      navItem.style.background = '';
      navItem.style.color = '';
    }
  }

  var ICON_SVG = '<svg viewBox="0 0 36 36" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
      + '<circle cx="18" cy="18" r="16" fill="#66c0f4"/>'
      + '<path d="M12 26V10h9a6 6 0 0 1 0 12h-6" fill="none" stroke="#1b2838" stroke-width="3.4" stroke-linecap="round"/>'
      + '</svg>';

  function buildNative() {
    if (navItem && document.contains(navItem)) { return true; }
    var items = document.querySelectorAll('[role="tab"][id*="/settings/"]');
    if (!items.length) { return false; }
    var ref = items[items.length - 1];

    // Пункты меню могут лежать в группах по два: поднимаемся к общему
    // списку, в котором больше трёх пунктов, чтобы наш пункт встал
    // отдельной строкой, а не рядом с «Музыкой».
    var list = ref.parentElement;
    while (list && list !== document.body
           && list.querySelectorAll('[role="tab"]').length < 3) {
      list = list.parentElement;
    }
    if (!list || list === document.body) { return false; }
    if (list.querySelector('#steampacc_nav_item')) { return true; }

    navItem = document.createElement('div');
    navItem.id = 'steampacc_nav_item';
    navItem.className = ref.className;
    navItem.setAttribute('role', 'tab');
    navItem.setAttribute('aria-selected', 'false');
    // Иконка: берём класс родной (даёт размер и отступы), но вставляем
    // в неё свой значок вместо чужого.
    var icon = document.createElement('div');
    if (ref.children.length >= 1) {
      icon.className = ref.children[0].className;
    }
    icon.innerHTML = ICON_SVG;
    navItem.appendChild(icon);
    var label = document.createElement('div');
    if (ref.children.length >= 2) { label.className = ref.children[1].className; }
    label.textContent = 'SteamPACC';
    navItem.appendChild(label);

    overlay = makePanel('steampacc_settings');

    navItem.addEventListener('click', function (event) {
      event.stopPropagation();
      if (!showOverlay()) { return; }
      navItem.setAttribute('aria-selected', 'true');
      navItem.style.background = 'rgba(102,192,244,0.15)';
    });

    document.addEventListener('click', function (event) {
      if (!overlay || overlay.style.display !== 'block') { return; }
      if (navItem.contains(event.target) || overlay.contains(event.target)) { return; }
      hideOverlay();
    }, true);

    list.appendChild(navItem);
    document.body.appendChild(overlay);
    return true;
  }

  function fallbackPanel() {
    var host = document.body;
    if (!host || !/SteamUIPopupWindowBody/.test(host.className || '')) { return; }
    if (!document.getElementById('steampacc_settings')) {
      var el = makePanel('steampacc_settings');
      el.style.cssText += ' position:fixed; right:12px; bottom:12px; width:230px;';
      host.appendChild(el);
    }
  }

  function tick() {
    if (!buildNative()) { fallbackPanel(); }
  }

  window.SteamPACC_settings_configure = function (next) {
    if (next && next.currencies && next.currencies.length) {
      cfg.currencies = next.currencies.slice();
    }
    var el = document.getElementById('steampacc_settings');
    if (el) {
      Array.prototype.forEach.call(el.querySelectorAll('input'), function (box) {
        box.checked = cfg.currencies.indexOf(box.value) >= 0;
      });
    }
  };

  setInterval(tick, 1000);
  setTimeout(tick, 0);
})();
'''.replace('__SET_PANEL__', "'" + _SETTINGS_CSS + "'") \
   .replace('__SET_TITLE__', "'" + _SETTINGS_TITLE_CSS + "'") \
   .replace('__SET_LABEL__', "'" + _SETTINGS_LABEL_CSS + "'")
