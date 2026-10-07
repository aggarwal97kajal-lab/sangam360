(function () {
  var C = window.Capacitor;
  if (!C || !C.isNativePlatform || !C.isNativePlatform()) return;
  var P = C.Plugins || {};
  /* A small message at the bottom of the screen. act = { label, run }: a button inside it (for example "Open"). */
  function toast(m, act, ms) {
    try {
      var old = document.getElementById('nbToast');
      if (old) old.remove();
      var d = document.createElement('div');
      d.id = 'nbToast';
      d.setAttribute('role', 'status');
      d.style.cssText = 'position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:#222;color:#fff;padding:10px 16px;border-radius:20px;z-index:2147483647;font:14px sans-serif;max-width:86%;text-align:center;display:flex;align-items:center;gap:12px;box-shadow:0 6px 20px rgba(0,0,0,.35)';
      var t = document.createElement('span');
      t.textContent = m;
      t.style.cssText = 'min-width:0;overflow-wrap:anywhere';
      d.appendChild(t);
      if (act) {
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = act.label;
        b.style.cssText = 'flex:none;border:0;border-radius:14px;background:#fff;color:#222;font:600 13px sans-serif;padding:7px 14px';
        b.onclick = function () { d.remove(); try { act.run(); } catch (e) {} };
        d.appendChild(b);
      }
      document.body.appendChild(d);
      setTimeout(function () { d.remove(); }, ms || (act ? 7000 : 2500));
    } catch (e) {}
  }
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
    var f = null;
    try {
      toast('Downloading…');
      f = await read(href, name);
      var r = await store(f);
      if (r) {
        var open = r.uri && r.plugin && typeof r.plugin.open === 'function'
          ? { label: 'Open', run: function () { r.plugin.open({ uri: r.uri, mime: r.mime }).catch(function () { toast('No app on this phone can open this file'); }); } }
          : null;
        toast('Downloaded · ' + r.name + ' · saved in ' + r.where, open);
        return;
      }
      /* this phone would not let the app write into Downloads: offer the file through the share sheet instead */
      if (!(await share(f.blob, f.name))) toast('Could not save file');
    } catch (e) {
      var msg = String((e && e.message) || e);
      if (/cancel/i.test(msg)) return;
      if (/permission/i.test(msg)) { toast('Allow storage access to save files', null, 4000); return; }
      if (typeof href === 'string' && /^https?:/i.test(href)) { window.open(href, '_blank'); }
      else { toast('Could not save file'); }
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
