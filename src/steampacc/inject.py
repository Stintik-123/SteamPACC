'''Код, внедряемый в страницы магазина Steam.

SteamPACC подключается к интерфейсу клиента Steam по протоколу DevTools
и добавляет этот сценарий на страницы магазина. Сценарий сам находит
открытую игру (по адресу страницы), запрашивает цены через официальный
API магазина — прямо изнутри страницы, тем же запросом, каким пользуется
сам Steam, — и дорисовывает блок с ценами выбранных регионов под
карточкой покупки. Стиль блока повторяет оформление магазина.

Реакция на изменения страницы — MutationObserver с небольшой паузой:
без постоянного перебора DOM каждую секунду. Кэш цен живёт в
sessionStorage, а при переполнении — в памяти страницы.

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

#: Надписи на двух языках: заголовок, бесплатно, недоступно, нет сети,
#: загрузка, подпись блока DLC.
_TEXTS_JS = (
    'var TEXT = {\n'
    '  ru: {header: "\\u0426\\u0435\\u043D\\u044B \\u0432 \\u0434\\u0440\\u0443\\u0433\\u0438\\u0445 \\u0440\\u0435\\u0433\\u0438\\u043E\\u043D\\u0430\\u0445",\n'
    '       free: "\\u0411\\u0435\\u0441\\u043F\\u043B\\u0430\\u0442\\u043D\\u043E",\n'
    '       unavailable: "\\u041D\\u0435\\u0434\\u043E\\u0441\\u0442\\u0443\\u043F\\u043D\\u043E \\u0432 \\u044D\\u0442\\u043E\\u043C \\u0440\\u0435\\u0433\\u0438\\u043E\\u043D\\u0435",\n'
    '       offline: "\\u043D\\u0435\\u0442 \\u0441\\u0432\\u044F\\u0437\\u0438",\n'
    '       loading: "\\u0417\\u0430\\u0433\\u0440\\u0443\\u0437\\u043A\\u0430\\u2026",\n'
    '       dlc: "\\u0426\\u0435\\u043D\\u044B DLC \\u0432 \\u0434\\u0440\\u0443\\u0433\\u0438\\u0445 \\u0440\\u0435\\u0433\\u0438\\u043E\\u043D\\u0430\\u0445"},\n'
    '  en: {header: "PRICES IN OTHER REGIONS",\n'
    '       free: "Free",\n'
    '       unavailable: "Not available in this region",\n'
    '       offline: "no connection",\n'
    '       loading: "Loading\\u2026",\n'
    '       dlc: "DLC prices in other regions"}\n'
    '};'
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

#: Сценарий целиком. Точка входа для настроек — window.SteamPACC_configure.
INJECTED_SCRIPT = r'''
(function () {
  'use strict';
  if (window.__STEAMPACC_ACTIVE__) { return; }
  window.__STEAMPACC_ACTIVE__ = true;

  __CC_MAP__
  __SYMBOLS__
  __TEXTS__
  var cfg = { currencies: ['RUB', 'USD', 'EUR'], lang: 'ru' };
  var TTL = 15 * 60 * 1000;
  // Версия кэша: при изменении формата запросов старые записи игнорируются.
  var CACHE_VERSION = 'v2';
  // Запасной кэш в памяти: sessionStorage ограничен, при переполнении
  // переключаемся на него молча.
  var mem = {};

  function t(key) { return (TEXT[cfg.lang] || TEXT.ru)[key]; }

  function appId() {
    var m = location.href.match(/\/app\/(\d+)/);
    return m ? m[1] : null;
  }

  function cacheKey(appid, code) { return CACHE_VERSION + ':steampacc:' + appid + ':' + code; }

  function cacheGet(appid, code) {
    var key = cacheKey(appid, code);
    try {
      var raw = sessionStorage.getItem(key);
      if (raw) {
        var obj = JSON.parse(raw);
        if (Date.now() - obj.t <= TTL) { return obj.p; }
        return undefined;
      }
    } catch (e) { /* читаем из памяти */ }
    if (mem[key] && Date.now() - mem[key].t <= TTL) { return mem[key].p; }
    return undefined;
  }

  function cacheSet(appid, code, p) {
    var entry = { t: Date.now(), p: p };
    var key = cacheKey(appid, code);
    mem[key] = entry;
    try {
      sessionStorage.setItem(key, JSON.stringify(entry));
    } catch (e) { /* переехали в память — это нормально */ }
  }

  function fmt(cents, currency) {
    if (cents == null) { return '\u2014'; }
    var value = cents / 100;
    var text = value.toLocaleString(cfg.lang === 'en' ? 'en-US' : 'ru-RU', {
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
      value.title = cfg.lang === 'en' ? 'Lowest price' : '\u0421\u0430\u043C\u0430\u044F \u043D\u0438\u0437\u043A\u0430\u044F \u0446\u0435\u043D\u0430';
    }
    if (p === null) {
      value.textContent = t('offline');
      value.style.color = '#5c6672';
    } else if (p.none) {
      value.textContent = t('unavailable');
      value.style.color = '#5c6672';
    } else if (p.free) {
      value.textContent = t('free');
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
    el.textContent = t('header');
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

  /* ---- Цены DLC: строчка цен под каждым DLC, сворачивается ---- */

  function dlcRows() {
    var rows = document.querySelectorAll('.game_area_dlc_row[data-ds-appid]');
    var result = [];
    rows.forEach(function (row) {
      var id = (row.getAttribute('data-ds-appid') || '').split(',')[0];
      if (!/^\d+$/.test(id)) { return; }
      // Бесплатность берём прямо со страницы: у бесплатных DLC Steam
      // пишет «Бесплатно»/«Free» в цене, а API часто не отдаёт is_free.
      var priceEl = row.querySelector('.game_area_dlc_price, .discount_final_price');
      var priceText = priceEl ? priceEl.textContent.trim() : '';
      var free = /^(\u0411\u0435\u0441\u043F\u043B\u0430\u0442\u043D\u043E|Free)$/i.test(priceText);
      result.push({ row: row, id: id, free: free });
    });
    return result.slice(0, 40);
  }

  function priceLine(id) {
    var line = document.createElement('div');
    line.className = 'steampacc_dlc_line';
    line.setAttribute('data-steampacc-id', id);
    line.style.cssText = 'font-size:12px; color:#66c0f4; padding:2px 4px 6px;'
        + ' text-align:left; line-height:15px;';
    line.textContent = t('loading');
    return line;
  }

  function fillLine(line, id, isFree) {
    if (isFree) {
      line.textContent = t('free');
      return;
    }
    var codes = cfg.currencies.slice(0, 3);
    var attempt = function (retried) {
      var tasks = codes.map(function (c) { return fetchOne(id, c); });
      Promise.all(tasks).then(function (prices) {
        var failed = prices.indexOf(null) >= 0;
        if (failed && !retried) {
          // Одна повторная попытка через секунду: сеть могла мигнуть.
          setTimeout(function () { attempt(true); }, 1000);
          return;
        }
        var parts = [];
        var unavailable = true;
        codes.forEach(function (code, i) {
          var p = prices[i];
          if (p && !p.none && !p.free && p.final != null) {
            unavailable = false;
            parts.push(code + ' ' + fmt(p.final, p.currency));
          }
        });
        if (failed && unavailable) {
          line.textContent = t('offline');
          line.style.color = '#5c6672';
        } else if (unavailable) {
          line.textContent = t('unavailable');
          line.style.color = '#5c6672';
        } else {
          line.textContent = parts.join('  \u00B7  ');
        }
      });
    };
    attempt(false);
  }

  function buildDlcToggle() {
    var rows = dlcRows();
    if (!rows.length || !cfg.currencies.length) { return; }
    var existing = document.getElementById('steampacc_dlc_toggle');
    if (existing) { return; }
    var toggle = document.createElement('div');
    toggle.id = 'steampacc_dlc_toggle';
    toggle.style.cssText = 'margin:6px 0; font-size:13px; color:#66c0f4;'
        + ' cursor:pointer; user-select:none; text-align:left;'
        + ' font-family:"Motiva Sans", Arial, sans-serif;';
    toggle.textContent = '\u25B8 ' + t('dlc') + ' (' + rows.length + ')';
    var open = false;
    toggle.addEventListener('click', function () {
      open = !open;
      toggle.textContent = (open ? '\u25BE ' : '\u25B8 ') + t('dlc') + ' (' + rows.length + ')';
      rows.forEach(function (item) {
        var row = item.row;
        if (open) {
          var line = row.querySelector('.steampacc_dlc_line');
          if (!line) {
            line = priceLine(item.id);
            row.appendChild(line);
          }
          if (line.textContent === t('loading') || line.textContent === t('offline')) {
            fillLine(line, item.id, item.free);
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

  var lastUrl = null;

  function update() {
    var box = ensureBox();
    if (!box) { return; }
    var url = location.href;
    if (url === lastUrl) { return; }
    lastUrl = url;
    // Блок DLC привязан к странице: при переходе собирается заново.
    var oldDlc = document.getElementById('steampacc_dlc_toggle');
    if (oldDlc) { oldDlc.parentNode.removeChild(oldDlc); }
    // Все регионы сняты: блок цен и DLC не показываем вовсе.
    if (!cfg.currencies.length) {
      box.style.display = 'none';
      return;
    }
    var appid = appId();
    if (!box) { return; }
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
      buildDlcToggle();
    });
  }

  // Реакция на изменения страницы: вместо опроса каждую секунду —
  // MutationObserver с паузой и редкая страховочная проверка.
  var scheduled = false;
  function scheduleUpdate() {
    if (scheduled) { return; }
    scheduled = true;
    setTimeout(function () {
      scheduled = false;
      update();
      buildDlcToggle();
    }, 300);
  }

  function startObserver() {
    if (!document.body) {
      setTimeout(startObserver, 200);
      return;
    }
    var observer = new MutationObserver(scheduleUpdate);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  window.SteamPACC_configure = function (next) {
    if (next && next.currencies && next.currencies.length) {
      cfg.currencies = next.currencies.slice();
    }
    if (next && (next.lang === 'ru' || next.lang === 'en')) {
      cfg.lang = next.lang;
    }
    lastUrl = null;
    update();
  };

  startObserver();
  setTimeout(update, 0);
  setInterval(update, 5000);
  document.addEventListener('DOMContentLoaded', function () { update(); });
})();
'''.replace('__CC_MAP__', _CC_MAP_JS) \
   .replace('__SYMBOLS__', _SYMBOLS_JS) \
   .replace('__TEXTS__', _TEXTS_JS) \
   .replace('__BOX__', _style('box', _CSS_BOX)) \
   .replace('__LABEL__', _style('label', _CSS_LABEL)) \
   .replace('__PRICE__', _style('value', _CSS_PRICE)) \
   .replace('__OLD__', _style('old', _CSS_OLD)) \
   .replace('__DISCOUNT__', _style('badge', _CSS_DISCOUNT)) \
   .replace('__ROW__', _style('line', _CSS_ROW)) \
   .replace('__HEADER__', _style('el', _CSS_HEADER))
