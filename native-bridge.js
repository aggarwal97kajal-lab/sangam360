(function () {
  var C = window.Capacitor;
  if (!C || !C.isNativePlatform || !C.isNativePlatform()) return;
  var P = C.Plugins || {};
  function toast(m) {
    try {
      var d = document.createElement('div');
      d.textContent = m;
      d.style.cssText = 'position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:#222;color:#fff;padding:10px 16px;border-radius:20px;z-index:2147483647;font:14px sans-serif;max-width:80%;text-align:center';
      document.body.appendChild(d);
      setTimeout(function () { d.remove(); }, 2500);
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
  async function save(href, name) {
    try {
      toast('Preparing file...');
      var res = await fetch(href);
      var blob = await res.blob();
      var fn = String(name || 'download').replace(/[\\\/:*?"<>|]+/g, '_');
      if (fn.indexOf('.') < 0 && blob.type === 'application/pdf') fn += '.pdf';
      var data = await b64(blob);
      var w = await P.Filesystem.writeFile({ path: fn, data: data, directory: 'CACHE' });
      await P.Share.share({ title: fn, url: w.uri, dialogTitle: 'Save or open ' + fn });
    } catch (e) {
      var msg = String((e && e.message) || e);
      if (/cancel/i.test(msg)) return;
      if (/^https?:/i.test(href)) { window.open(href, '_blank'); }
      else { toast('Could not save file'); }
    }
  }
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
})();
