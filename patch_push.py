p = "www/index.html"
s = open(p, encoding="utf-8").read()

# remember microphone / location permission after the first time
c = 'if(st==="unknown"&&pHint(k)&&k!=="media")return true;'
assert s.count(c) == 1, "permission check not found"
s = s.replace(c, 'if(pHint(k)&&st!=="denied")return true;')

open(p, "w", encoding="utf-8").write(s)
print("patched ok (push registration is switched off)")
