(function () {
  var C = window.Capacitor;
  if (!C || !C.isNativePlatform || !C.isNativePlatform()) return;
  var P = C.Plugins || {};
  /* ---- what the person sees: one card that slides up from the bottom (downloading -> downloaded, with Open) ----
     It takes its colours from the app (light / dark theme, the workspace's accent colour). */
  var IC = {
    ok: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
    bad: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/></svg>',
    x: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>'
  };
  function css() {
    if (document.getElementById('nbCss')) return;
    var st = document.createElement('style');
    st.id = 'nbCss';
    st.textContent =
      '#nbCard{position:fixed;left:12px;right:12px;bottom:calc(86px + env(safe-area-inset-bottom,0px));z-index:2147483647;margin:0 auto;max-width:460px;box-sizing:border-box;display:flex;align-items:center;gap:12px;padding:12px 10px 12px 12px;overflow:hidden;' +
      'background:var(--tn-bg,var(--card,#fff));color:var(--tn-tx,var(--text,#0f172a));border:1px solid var(--tn-bd,var(--line,#e2e8f0));border-radius:18px;box-shadow:var(--tn-sh,0 14px 38px rgba(15,23,42,.24),0 2px 6px rgba(15,23,42,.08));font-family:Poppins,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;' +
      'opacity:0;transform:translateY(18px) scale(.98);transition:opacity .22s ease,transform .26s cubic-bezier(.2,.9,.3,1.15);-webkit-tap-highlight-color:transparent}' +
      '#nbCard.in{opacity:1;transform:none}' +
      '#nbCard.top{bottom:auto;top:calc(12px + env(safe-area-inset-top,0px));transform:translateY(-18px) scale(.98)}#nbCard.top.in{transform:none}' +
      '#nbCard .nbi{flex:none;width:42px;height:42px;border-radius:13px;display:grid;place-items:center;color:var(--a,#5b3df5);background:rgba(91,61,245,.12);background:color-mix(in srgb,var(--a,#5b3df5) 13%,transparent)}' +
      '#nbCard.ok .nbi{color:var(--grn,#10b981);background:rgba(16,185,129,.14);background:color-mix(in srgb,var(--grn,#10b981) 15%,transparent)}' +
      '#nbCard.bad .nbi{color:var(--red,#ef4444);background:rgba(239,68,68,.12);background:color-mix(in srgb,var(--red,#ef4444) 13%,transparent)}' +
      '#nbCard .nbs{width:20px;height:20px;border-radius:50%;border:2.5px solid currentColor;border-right-color:transparent;animation:nbspin .7s linear infinite}' +
      '#nbCard .nbt{flex:1;min-width:0}' +
      '#nbCard .nbt b{display:block;font-size:14px;font-weight:600;line-height:1.3}' +
      '#nbCard .nbt span{display:block;font-size:12.5px;line-height:1.35;color:var(--tn-mu,var(--muted,#64748b));overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
      '#nbCard .nba{flex:none;border:0;border-radius:99px;background:var(--a,#5b3df5);color:#fff;font:600 13.5px Poppins,system-ui,sans-serif;padding:10px 18px;min-height:40px}' +
      '#nbCard .nba:active{transform:scale(.96)}' +
      '#nbCard .nbx{flex:none;width:36px;height:36px;border:0;border-radius:50%;background:transparent;color:var(--muted,#64748b);display:grid;place-items:center;padding:0}' +
      '#nbCard .nbp{position:absolute;left:0;bottom:0;height:3px;width:100%;background:var(--a,#5b3df5);opacity:.5;transform-origin:left;animation:nbbar linear forwards}' +
      '#nbCard.ok .nbp{background:var(--grn,#10b981)}' +
      '#nbCard.mini{left:50%;right:auto;transform:translate(-50%,18px);padding:10px 18px;border-radius:99px;max-width:86%}#nbCard.mini.in{transform:translate(-50%,0)}#nbCard.mini .nbt b{font-weight:600;font-size:13.5px;text-align:center}' +
      '@keyframes nbspin{to{transform:rotate(360deg)}}@keyframes nbbar{from{transform:scaleX(1)}to{transform:scaleX(0)}}' +
      '@media (prefers-reduced-motion:reduce){#nbCard{transition:opacity .15s}#nbCard .nbs{animation-duration:1.4s}}';
    (document.head || document.documentElement).appendChild(st);
  }
  var hideT = 0;
  function hide() {
    clearTimeout(hideT);
    var d = document.getElementById('nbCard');
    if (!d) return;
    d._gone = true;   // it may be told to go before it has finished sliding in
    d.classList.remove('in');
    setTimeout(function () { if (d.parentNode) d.remove(); }, 260);
  }
  /* o: { kind: 'busy' | 'ok' | 'bad' | 'mini', title, sub, sub2, action: { label, run }, ms } */
  function card(o) {
    try {
      css();
      clearTimeout(hideT);
      var old = document.getElementById('nbCard');
      if (old) old.remove();
      var d = document.createElement('div'), mini = o.kind === 'mini';
      d.id = 'nbCard';
      /* a sheet or the payment screen is open: its buttons are at the bottom, so the card goes to the top */
      var top = !mini && !!document.querySelector('#ov:not(.hide) .sheet, .pyo');
      d.className = o.kind + (top ? ' top' : '') + (old && !old._gone ? ' in' : '');
      d.setAttribute('role', 'status');
      d.setAttribute('aria-live', 'polite');
      if (!mini) {
        var i = document.createElement('div');
        i.className = 'nbi';
        i.innerHTML = o.kind === 'busy' ? '<div class="nbs"></div>' : o.kind === 'ok' ? IC.ok : IC.bad;
        d.appendChild(i);
      }
      var t = document.createElement('div'), b = document.createElement('b');
      t.className = 'nbt';
      b.textContent = o.title || '';
      t.appendChild(b);
      [o.sub, o.sub2].forEach(function (x) { if (!x) return; var sp = document.createElement('span'); sp.textContent = x; t.appendChild(sp); });
      d.appendChild(t);
      if (o.action) {
        var a = document.createElement('button');
        a.type = 'button';
        a.className = 'nba';
        a.textContent = o.action.label;
        a.onclick = function () { hide(); try { o.action.run(); } catch (e) {} };
        d.appendChild(a);
      }
      if (!mini && o.kind !== 'busy') {
        var x = document.createElement('button');
        x.type = 'button';
        x.className = 'nbx';
        x.setAttribute('aria-label', 'Close');
        x.innerHTML = IC.x;
        x.onclick = hide;
        d.appendChild(x);
      }
      var ms = o.ms || (o.kind === 'busy' ? 0 : o.action ? 8000 : mini ? 2400 : 4500);
      if (ms && !mini) { var p = document.createElement('i'); p.className = 'nbp'; p.style.animationDuration = ms + 'ms'; d.appendChild(p); }
      document.body.appendChild(d);
      requestAnimationFrame(function () { requestAnimationFrame(function () { if (!d._gone) d.classList.add('in'); }); });
      if (ms) hideT = setTimeout(hide, ms);
    } catch (e) {}
  }
  function toast(m) { card({ kind: 'mini', title: m }); }
  function b64(blob) {
    return new Promise(function (ok, no) {
      var r = new FileReader();
      r.onload = function () { ok(String(r.result).split(',')[1] || ''); };
      r.onerror = no;
      r.readAsDataURL(blob);
    });
  }
  var EXT = { 'application/pdf': '.pdf', 'text/csv': '.csv', 'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp' };
  function fileName(name, blob) {
    var fn = String(name || 'download').replace(/[\\\/:*?"<>|\u0000-\u001f]+/g, '_').replace(/^\.+/, '').slice(0, 120) || 'download';
    var type = String((blob && blob.type) || '').split(';')[0];
    if (fn.indexOf('.') < 0 && EXT[type]) fn += EXT[type];
    return fn;
  }
  /* href: an address (blob:, https:) or the file itself (Blob / File) */
  async function read(href, name) {
    var blob = href;
    if (typeof href === 'string') { var res = await fetch(href); blob = await res.blob(); }
    return { blob: blob, name: fileName(name, blob), mime: String(blob.type || '').split(';')[0] || 'application/octet-stream', data: await b64(blob) };
  }

  /* ---- Share: hands the file to another app (WhatsApp, e-mail ...). Only used when the person taps a Share button. ---- */
  async function share(href, name, o) {
    try {
      var f = await read(href, name);
      var w = await P.Filesystem.writeFile({ path: f.name, data: f.data, directory: 'CACHE' });
      await P.Share.share({ title: (o && o.title) || f.name, text: (o && o.text) || undefined, url: w.uri, dialogTitle: 'Share ' + f.name });
      return true;
    } catch (e) {
      var msg = String((e && e.message) || e);
      if (/cancel/i.test(msg)) return true;   // the person closed the share sheet: nothing else to do
      return false;
    }
  }

  /* ---- Download: the file is written into the phone's Downloads folder (Download/Sangam360) and stays there ----
     1. the app's own SaveFile plugin (download_native.py): works on every Android version, no permission on Android 10+
     2. without it, the Filesystem plugin, straight into the public Download or Documents folder
     Only when neither can write is the share sheet shown, so the file is never lost. */
  var FOLDER = 'Sangam360';
  async function store(f) {
    var S = P.SaveFile;
    if (S && typeof S.save === 'function') {
      try {
        var r = await S.save({ name: f.name, data: f.data, mime: f.mime });
        return { where: (r && r.folder) || 'Download/' + FOLDER, name: (r && r.name) || f.name, uri: r && r.uri, mime: f.mime, plugin: S };
      } catch (e) {
        if (/permission/i.test(String((e && e.message) || e))) throw e;   // refused by the person: say so, do not open a share sheet instead
      }
    }
    var F = P.Filesystem, tries = [['EXTERNAL_STORAGE', 'Download/' + FOLDER], ['DOCUMENTS', FOLDER]];
    if (F && typeof F.writeFile === 'function') {
      for (var i = 0; i < tries.length; i++) {
        try {
          await F.writeFile({ path: tries[i][1] + '/' + f.name, data: f.data, directory: tries[i][0], recursive: true });
          return { where: tries[i][0] === 'DOCUMENTS' ? 'Documents/' + FOLDER : tries[i][1], name: f.name };
        } catch (e) {}
      }
    }
    return null;
  }
  async function save(href, name) {
    var f = null, label = fileName(name, null);
    try {
      card({ kind: 'busy', title: 'Downloading…', sub: label });
      f = await read(href, name);
      var r = await store(f);
      if (r) {
        var open = r.uri && r.plugin && typeof r.plugin.open === 'function'
          ? { label: 'Open', run: function () { r.plugin.open({ uri: r.uri, mime: r.mime }).catch(function () { card({ kind: 'bad', title: 'No app can open this file', sub: 'Install a PDF or file viewer and try again.' }); }); } }
          : null;
        card({ kind: 'ok', title: 'Download complete', sub: r.name, sub2: String(r.where).replace(/^Download\//, 'Downloads/').replace(/\//g, ' › '), action: open });
        return;
      }
      /* this phone would not let the app write into Downloads: offer the file through the share sheet instead */
      hide();
      if (!(await share(f.blob, f.name))) card({ kind: 'bad', title: 'Could not save the file', sub: f.name });
    } catch (e) {
      var msg = String((e && e.message) || e);
      if (/cancel/i.test(msg)) { hide(); return; }
      if (/permission/i.test(msg)) { card({ kind: 'bad', title: 'Storage access is needed', sub: 'Allow it to save files on this phone.' }); return; }
      if (typeof href === 'string' && /^https?:/i.test(href)) { hide(); window.open(href, '_blank'); }
      else card({ kind: 'bad', title: 'Could not save the file', sub: label });
    }
  }
  /* what the web app can call directly */
  window.S360Native = { save: save, share: share };

  var oc = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.hasAttribute('download') && this.href) {
      save(this.href, this.getAttribute('download') || this.download);
      return;
    }
    return oc.apply(this, arguments);
  };
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[download]') : null;
    if (a && a.href) {
      e.preventDefault();
      save(a.href, a.getAttribute('download'));
    }
  }, true);
  // Android back button: go back inside the app, leave only from the home screen
  var A = P.App, waiting = false;
  if (A && A.addListener) {
    A.addListener('backButton', function () {
      var ok = false;
      try { ok = !!(window.__back && window.__back()); } catch (e) {}
      if (ok) return;
      if (waiting) { try { A.exitApp(); } catch (e) {} return; }
      waiting = true;
      toast('Press back again to exit');
      setTimeout(function () { waiting = false; }, 2200);
    });
  }
})();
