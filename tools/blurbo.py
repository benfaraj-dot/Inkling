#!/usr/bin/env python3
"""Blurbo helper for the daily Inklings run.

  python3 tools/blurbo.py status            show which outfit is on
  python3 tools/blurbo.py set <outfit|suit> switch outfit (restores the suit first)
  python3 tools/blurbo.py check             validate blurbo.json (run before every commit)
  python3 tools/blurbo.py render out.png [filter]   contact sheet of every figure
  python3 tools/blurbo.py smoke out.png     load the real index.html and show every figure in the game
  python3 tools/blurbo.py props out.png     sheet of every prop in the library (red dot = its 0,0 anchor)

Outfits live in blurbo.json "outfits": {name: {"for", "replace": {partId: full <g id=partId> markup},
"layer": {partId: markup drawn on top of that part}, "css": "rules"}}. Layered parts keep the
current base (renamed partId__base), so daily design refinements are never lost.

Props (gadgets) live in defs as <g id="p-name"> with a catalog in blurbo.json "props":
[{"id", "name", "added", "anchor", "tags"}]. Any emote or dance uses one with
<use href="#p-name" transform="translate(x y) rotate(a) scale(s)"></use>, usually followed by a glove at the grip.

Falls and rises: blurbo.json "falls" (played when Blurbo is shot) and "rises" (played when he is
revived) are clips [{"id", "name", "added", "steps": [{"svg", "motion", "ms"}]}], 3 to 10 steps,
ms 150 to 1500, played once each. The game picks one at random (never the same twice in a row).
FX parts for them live in defs as fx-* (fx-wings, fx-halo, fx-abv clipPath for rising out of the line).
"""
import json, re, sys, os, xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'blurbo.json')
REQUIRED = ['pud', 'legs', 'torso', 'hd', 'ey', 'gr', 'gb', 'gl', 'mic', 'gs', 'sp']
MOTIONS = ['none', 'bob', 'sway', 'shake', 'bounce', 'wiggle', 'float', 'pulse', 'melt', 'stretch', 'spin']
TRIGGERS = ['idle', 'pick1', 'pick2', 'pick3', 'pick4', 'correct', 'wrong', 'oneaway', 'look', 'lose', 'escape', 'hint', 'cheat']

def load(): return json.load(open(PATH, encoding='utf-8'))
def save(b):
    with open(PATH, 'w', encoding='utf-8') as f: json.dump(b, f, ensure_ascii=False, indent=1)

def find_group(defs, pid):
    m = re.search(r'<g id="%s"[ >]' % re.escape(pid), defs)
    if not m: raise SystemExit('part #%s not found as a <g> in defs' % pid)
    depth, i = 0, m.start()
    for t in re.finditer(r'<(/?)g[ >]', defs[i:]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return m.start(), i + t.start() + len('</g>')
    raise SystemExit('unbalanced <g> for #%s' % pid)

STYLE_RE = re.compile(r'<style data-outfit="[^"]*">.*?</style>', re.S)

def outfit_off(b):
    st = b.get('outfitStash')
    if not st: b['outfitNow'] = 'suit'; return
    d = STYLE_RE.sub('', b['defs'])
    o = b['outfits'][st['name']]
    for pid in st.get('layered', []):
        s, e = find_group(d, pid)
        d = d[:s] + d[e:]
        d = d.replace('<g id="%s__base"' % pid, '<g id="%s"' % pid, 1)
    for pid, orig in st.get('replaced', {}).items():
        s, e = find_group(d, pid)
        o.setdefault('replace', {})[pid] = d[s:e]   # keep refinements made during the holiday
        d = d[:s] + orig + d[e:]
    b['defs'] = d
    b['outfitNow'] = 'suit'
    b.pop('outfitStash', None)

def outfit_on(b, name):
    o = b['outfits'][name]
    d = b['defs']
    st = {'name': name, 'replaced': {}, 'layered': []}
    for pid, mk in o.get('replace', {}).items():
        s, e = find_group(d, pid)
        st['replaced'][pid] = d[s:e]
        d = d[:s] + mk + d[e:]
    for pid, mk in o.get('layer', {}).items():
        s, e = find_group(d, pid)
        base = d[s:e].replace('<g id="%s"' % pid, '<g id="%s__base"' % pid, 1)
        d = d[:s] + base + '<g id="%s"><use href="#%s__base"></use>%s</g>' % (pid, pid, mk) + d[e:]
        st['layered'].append(pid)
    if o.get('css'):
        d = '<style data-outfit="%s">%s</style>' % (name, o['css']) + d
    b['defs'] = d
    b['outfitNow'] = name
    b['outfitStash'] = st

def check(b):
    errs = []
    wrap = lambda s: '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><defs>%s</defs>%s</svg>' % (b['defs'], s)
    try: ET.fromstring(wrap(''))
    except Exception as e: errs.append('defs not valid XML: %s' % e)
    ids = re.findall(r'\sid="([^"]+)"', b['defs'])
    dup = {i for i in ids if ids.count(i) > 1}
    if dup: errs.append('duplicate ids in defs: %s' % dup)
    for r in REQUIRED:
        if r not in ids: errs.append('missing part #%s' % r)
    for h in re.findall(r'href="#([^"]+)"', b['defs']):
        if h not in ids: errs.append('defs reference missing #%s' % h)
    if b.get('motions') != MOTIONS: errs.append('motions list changed')
    def chk(svg, name):
        try: ET.fromstring(wrap(svg))
        except Exception as e: errs.append('%s: bad XML %s' % (name, e))
        for h in re.findall(r'href="#([^"]+)"', svg):
            if h not in ids: errs.append('%s: missing #%s' % (name, h))
        if re.search(r'/>|<script|<image|\son[a-z]+=|href="(?!#)', svg): errs.append('%s: forbidden markup' % name)
        if '<use href="#pud"></use>' not in svg: errs.append('%s: missing #pud' % name)
    if set(b['emotes']) != set(TRIGGERS): errs.append('trigger set changed')
    for k, vs in b['emotes'].items():
        if len({v['id'] for v in vs}) != len(vs): errs.append('duplicate ids in %s' % k)
        for v in vs:
            chk(v['svg'], v['id'])
            if v.get('motion') not in MOTIONS: errs.append('%s: bad motion' % v['id'])
    dids = [d['id'] for d in b['dances']]
    if len(set(dids)) != len(dids): errs.append('duplicate dance ids')
    for d in b['dances']:
        if not 4 <= len(d['steps']) <= 8: errs.append('%s: step count' % d['id'])
        for i, s in enumerate(d['steps']):
            chk(s['svg'], '%s#%d' % (d['id'], i))
            if s.get('motion') not in MOTIONS or not 250 <= s.get('ms', 0) <= 1200: errs.append('%s#%d: motion/ms' % (d['id'], i))
    for key in ('falls', 'rises'):
        cids = [c['id'] for c in b.get(key, [])]
        if len(set(cids)) != len(cids): errs.append('duplicate %s ids' % key)
        for c in b.get(key, []):
            if not all(c.get(k) for k in ('id', 'name', 'added')): errs.append('%s: clip needs id, name, added' % c.get('id'))
            if not 3 <= len(c.get('steps', [])) <= 10: errs.append('%s: step count (3 to 10)' % c.get('id'))
            for i, st in enumerate(c.get('steps', [])):
                chk(st['svg'], '%s#%d' % (c['id'], i))
                if st.get('motion') not in MOTIONS or not 150 <= st.get('ms', 0) <= 1500: errs.append('%s#%d: motion/ms' % (c['id'], i))
    now = b.get('outfitNow', 'suit')
    if now != 'suit' and (b.get('outfitStash', {}).get('name') != now): errs.append('outfitNow without matching outfitStash')
    if now == 'suit' and (b.get('outfitStash') or STYLE_RE.search(b['defs'])): errs.append('suit on but outfit leftovers remain')
    for n, o in b.get('outfits', {}).items():
        for pid, mk in o.get('replace', {}).items():
            if not mk.startswith('<g id="%s"' % pid): errs.append('outfit %s: replace.%s must be <g id="%s">' % (n, pid, pid))
        for pid, mk in o.get('layer', {}).items():
            try: ET.fromstring('<g xmlns="http://www.w3.org/2000/svg">%s</g>' % mk)
            except Exception as e: errs.append('outfit %s layer %s: %s' % (n, pid, e))
    cat = b.get('props', [])
    cids = [p.get('id') for p in cat]
    if len(set(cids)) != len(cids): errs.append('duplicate prop ids in catalog')
    for p in cat:
        if not all(p.get(k) for k in ('id', 'name', 'added', 'anchor')): errs.append('prop %s: catalog entry needs id, name, added, anchor' % p.get('id'))
        if not str(p.get('id', '')).startswith('p-'): errs.append('prop %s: id must start with p-' % p.get('id'))
        if p.get('id') not in ids: errs.append('prop %s: missing from defs' % p.get('id'))
    for i in ids:
        if i.startswith('p-') and i not in cids: errs.append('prop #%s in defs but not in the props catalog' % i)
    return errs

def props_sheet(b, png):
    from playwright.sync_api import sync_playwright
    cells = ''.join('<div style="display:inline-block;margin:4px;text-align:center;font:11px sans-serif;width:180px"><svg id="bl" xmlns="http://www.w3.org/2000/svg" viewBox="-90 -90 180 180" width="180" height="180" style="background:#f6f1e3"><use href="#%s"></use><circle r="2.5" fill="red"></circle></svg><br>%s<br>%s</div>' % (p['id'], p['id'], p['name']) for p in b.get('props', []))
    html = '<html><body style="margin:0;width:1180px"><svg width="0" height="0" style="position:absolute"><defs>%s</defs></svg>%s</body></html>' % (b['defs'], cells)
    with sync_playwright() as pw:
        br = pw.chromium.launch(); pg = br.new_page(viewport={'width': 1180, 'height': 400})
        pg.set_content(html); pg.screenshot(path=png, full_page=True); br.close()
    print('rendered %d props -> %s' % (len(b.get('props', [])), png))

def figures(b, flt=None):
    out = []
    for k, vs in b['emotes'].items():
        for v in vs: out.append((k + ':' + v['id'], v['svg'], v['motion']))
    for d in b['dances']:
        for i, s in enumerate(d['steps']): out.append(('%s#%d' % (d['id'], i), s['svg'], s['motion']))
    for key in ('falls', 'rises'):
        for c in b.get(key, []):
            for i, s in enumerate(c['steps']): out.append(('%s#%d' % (c['id'], i), s['svg'], s['motion']))
    if flt: out = [f for f in out if any(x in f[0] for x in flt.split(','))]
    return out

def render(b, png, flt=None):
    from playwright.sync_api import sync_playwright
    figs = figures(b, flt)
    cells = ''.join('<div style="display:inline-block;margin:4px;text-align:center;font:11px sans-serif"><svg id="bl" xmlns="http://www.w3.org/2000/svg" viewBox="0 -24 200 340" width="200" height="340" style="background:#f6f1e3">%s</svg><br>%s</div>' % (s, n) for n, s, m in figs)
    html = '<html><body style="margin:0;width:1680px"><svg width="0" height="0" style="position:absolute"><defs>%s</defs></svg>%s</body></html>' % (b['defs'], cells)
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={'width': 1680, 'height': 400})
        pg.set_content(html); pg.screenshot(path=png, full_page=True); br.close()
    print('rendered %d figures -> %s' % (len(figs), png))

def smoke(png):
    """Serve the repo, open the real game (it loads blurbo.json and injects defs itself), show every figure in its #blfig, screenshot #bl each time."""
    import threading, http.server, functools, socketserver, base64
    from playwright.sync_api import sync_playwright
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    H = functools.partial(Q, directory=ROOT)
    srv = socketserver.TCPServer(('127.0.0.1', 0), H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    b = load(); shots = []; bad = []
    with sync_playwright() as p:
        br = p.chromium.launch(); pg = br.new_page(viewport={'width': 420, 'height': 400}, device_scale_factor=2)
        pg.goto('http://127.0.0.1:%d/index.html' % port); pg.wait_for_function('document.querySelector("#bldefs").children.length>0')
        pg.evaluate('(()=>{const s=document.querySelector("#stage");if(s){s.hidden=false;s.classList.remove("off")}document.querySelector("#bl").style.display="block"})()')
        for n, svg, m in figures(b):
            pg.evaluate('([s,m])=>{document.querySelector("#blfig").innerHTML=s;document.querySelector("#blmv").setAttribute("class","m-none")}', [svg, m])
            box = pg.evaluate('(()=>{const r=document.querySelector("#blfig").getBBox();return [r.width,r.height]})()')
            if box[0] < 60 or box[1] < 200: bad.append(n)
            shots.append((n, base64.b64encode(pg.locator('#bl').screenshot()).decode()))
        cells = ''.join('<div style="display:inline-block;margin:3px;text-align:center;font:10px sans-serif;background:#f6f1e3"><img src="data:image/png;base64,%s" style="height:150px"><br>%s</div>' % (s, n) for n, s in shots)
        pg2 = br.new_page(viewport={'width': 1200, 'height': 400}); pg2.set_content('<body style="margin:0">%s</body>' % cells)
        pg2.screenshot(path=png, full_page=True); br.close()
    srv.shutdown()
    print('game smoke test: %d figures, %d look broken %s -> %s' % (len(shots), len(bad), bad, png))
    return not bad

if __name__ == '__main__':
    a = sys.argv[1:] or ['status']
    b = load()
    if a[0] == 'status':
        print('outfitNow:', b.get('outfitNow', 'suit'), '| outfits:', ', '.join('%s (%s)' % (k, v.get('for', '')) for k, v in b.get('outfits', {}).items()))
    elif a[0] == 'set':
        want = a[1]
        if want != 'suit' and want not in b.get('outfits', {}): raise SystemExit('unknown outfit ' + want)
        if b.get('outfitNow', 'suit') == want: print('already', want); sys.exit()
        outfit_off(b)
        if want != 'suit': outfit_on(b, want)
        e = check(b)
        if e: raise SystemExit('NOT saved, switch would break Blurbo:\n' + '\n'.join(e))
        save(b); print('outfit now', want)
    elif a[0] == 'check':
        e = check(b); print('\n'.join(e) if e else 'blurbo.json OK'); sys.exit(1 if e else 0)
    elif a[0] == 'render': render(b, a[1], a[2] if len(a) > 2 else None)
    elif a[0] == 'props': props_sheet(b, a[1])
    elif a[0] == 'smoke': sys.exit(0 if smoke(a[1]) else 1)
