"""Puts Firebase and the web fonts inside the app (run by the build after www/index.html is made).

Without this, every start of the app first downloads Firebase (about 1 MB) and the fonts from the internet: on a
slow network or a cheap phone the app then hangs on the first screen. With it, they come from the phone itself.
If a download fails, the page is left as it was (it then loads them from the internet, like before).
Usage: python3 bundle_web.py www
"""
import os, re, sys, urllib.request

WWW = sys.argv[1] if len(sys.argv) > 1 else 'www'
GS = os.environ.get('S360_GSTATIC', 'https://www.gstatic.com')
FONTS = os.environ.get('S360_FONTS', 'https://fonts.googleapis.com')
UA = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36'


def get(u):
    r = urllib.request.Request(u, headers={'User-Agent': UA})
    with urllib.request.urlopen(r, timeout=90) as f:
        return f.read()


idx = os.path.join(WWW, 'index.html')
page = open(idx, encoding='utf-8').read()
orig = page

# ---- Firebase: every module the page imports, and every module those import
try:
    m = re.search(r'https://www\.gstatic\.com/firebasejs/([\d.]+)/', page)
    if not m:
        raise Exception('no Firebase import found')
    ver = m.group(1)
    real = 'https://www.gstatic.com/firebasejs/%s/' % ver
    src = GS + '/firebasejs/%s/' % ver
    pat = re.compile(re.escape(real) + r'(firebase-[a-z-]+\.js)')
    todo, files = sorted(set(pat.findall(page))), {}
    while todo:
        n = todo.pop()
        if n in files:
            continue
        body = get(src + n).decode('utf-8')
        if 'export' not in body:
            raise Exception(n + ' does not look like a module')
        files[n] = body
        todo += [x for x in pat.findall(body) if x not in files]
    os.makedirs(os.path.join(WWW, 'fb'), exist_ok=True)
    for n, body in files.items():
        body = body.replace(real, './')
        body = re.sub(r'//# sourceMappingURL=\S+', '', body)
        open(os.path.join(WWW, 'fb', n), 'w', encoding='utf-8').write(body)
    page = page.replace(real, './fb/')
    print('Firebase is inside the app:', ', '.join(sorted(files)))
except Exception as e:
    page = orig
    print('Firebase NOT bundled (the app loads it from the internet):', e)

# ---- Google fonts: the stylesheet and its font files
try:
    links = sorted(set(re.findall(r'https://fonts\.googleapis\.com/css2\?[^"\']+', page)))
    os.makedirs(os.path.join(WWW, 'fonts'), exist_ok=True)
    k, p2 = 0, page
    for i, href in enumerate(links):
        css = get(href.replace('&amp;', '&').replace('https://fonts.googleapis.com', FONTS)).decode('utf-8')
        def keep(mo):
            global k
            k += 1
            name = 'f%d.woff2' % k
            open(os.path.join(WWW, 'fonts', name), 'wb').write(get(mo.group(1)))
            return 'url(' + name + ')'
        css = re.sub(r'url\((https?://[^)]+\.woff2)\)', keep, css)
        open(os.path.join(WWW, 'fonts', 'g%d.css' % i), 'w', encoding='utf-8').write(css)
        p2 = p2.replace(href, 'fonts/g%d.css' % i)
    page = p2
    print('Fonts are inside the app:', k, 'files')
except Exception as e:
    print('Fonts NOT bundled (the app loads them from the internet):', e)

open(idx, 'w', encoding='utf-8').write(page)
