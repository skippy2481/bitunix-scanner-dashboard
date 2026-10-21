import json, os, py_compile, shutil, subprocess, time
BASE = "/opt/bitunix-dashboard"
BK = os.path.join(BASE, "backups", "2026-10-21-pre-round3-merge")
os.makedirs(BK, exist_ok=True)
for f in ("info-links.json", "tradfi-names.json", "server.py"):
    shutil.copy2(os.path.join(BASE, f), BK)
print("snapshot:", BK)
os.replace(BASE + "/info-links.json.staged", BASE + "/info-links.json")
os.replace(BASE + "/tradfi-names.json.staged", BASE + "/tradfi-names.json")
il = json.load(open(BASE + "/info-links.json"))
tn = json.load(open(BASE + "/tradfi-names.json"))
print("installed: %d links, %d tradfi entries" % (len(il), len(tn["entries"])))

sp = BASE + "/server.py"
src = open(sp).read()
old = "def info_url(base):\n    u = INFO_LINKS.get(base)"
assert old in src, "info_url head not found"
fn_old = src[src.index("def info_url"):src.index("return None", src.index("def info_url")) + len("return None")]
fn_new = '''def info_url(base):
    b = (base or "").upper()
    cands = [b, b[4:] if b.startswith("1000") else "1000" + b]
    for c in cands:
        if c in INFO_LINKS:
            return INFO_LINKS[c]
    for c in cands:
        if c in INFO_CG:
            return INFO_CG[c]
    if classify(b) == "TradFi":
        return "https://finance.yahoo.com/quote/" + b + "/"
    return None'''
src = src.replace(fn_old, fn_new)
tmp = sp + ".new"
open(tmp, "w").write(src)
py_compile.compile(tmp, doraise=True)
os.replace(tmp, sp)
print("server.py: 1000-normalization installed")

subprocess.run(["systemctl", "restart", "bitunix-dashboard"], check=True)
time.sleep(4)
print("service:", subprocess.run(["systemctl", "is-active", "bitunix-dashboard"],
      capture_output=True, text=True).stdout.strip())
