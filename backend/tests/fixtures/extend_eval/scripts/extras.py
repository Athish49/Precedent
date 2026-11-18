import json, sys, time, re, glob, io
from pathlib import Path
import httpx
from docx import Document
S = Path(sys.argv[1]); OUT = S / "out"
H = {"Authorization": f"Bearer {(S/'key.txt').read_text().strip()}", "x-extend-api-version": "2026-02-09"}
c = httpx.Client(headers=H, timeout=120, base_url="https://api.extend.ai")
def wait(path):
    t = time.time()
    while True:
        j = c.get(path).json()
        if j.get("status") in ("PROCESSED", "FAILED", "CANCELLED") or time.time() - t > 300:
            return j
        time.sleep(3)
def upload(name, data):
    r = c.post("/files/upload", files={"file": (name, data)})
    print(" upload", name, r.status_code, r.text[:200] if r.status_code >= 400 else r.json()["id"])
    return r.json().get("id") if r.status_code < 400 else None
def parse(fid):
    r = c.post("/parse_runs", json={"file": {"id": fid}, "config": {"engine": "parse_light", "chunkingStrategy": {"type": "document"}, "blockOptions": {"tables": {"targetFormat": "markdown"}}}})
    if r.status_code >= 400:
        print(" parse create error", r.status_code, r.text[:300]); return None
    return wait(f"/parse_runs/{r.json()['id']}")

print("## a. repeat: fresh upload, extract only (no standalone parse first)")
prev = json.load(open(OUT / "msa_runin_pdf_light_extract.json"))
fid = upload("msa_runin.pdf", open(S / "docs/msa_runin.pdf", "rb").read())
r = c.post("/extract_runs", json={"file": {"id": fid}, "config": prev["config"]})
print(" create", r.status_code, r.text[:200] if r.status_code >= 400 else "")
j = wait(f"/extract_runs/{r.json()['id']}")
(OUT / "repeat_extract.json").write_text(json.dumps(j, indent=1))
print(" usage", json.dumps(j["usage"]))
a, b = prev["output"]["value"], j["output"]["value"]
diff = {k: (a[k], b.get(k)) for k in a if a[k] != b.get(k)}
print(" fields differing between run 1 and run 2:", json.dumps(diff)[:1500] or "none")
p2 = c.get(f"/parse_runs/{j['parseRunId']}").json()
(OUT / "repeat_parse.json").write_text(json.dumps(p2, indent=1))
p1 = json.load(open(OUT / "msa_runin_pdf_light_parse.json"))
blk = lambda p: [(x["type"], x["content"]) for ch in p["output"]["chunks"] for x in ch["blocks"]]
print(" parse usage", json.dumps(p2.get("usage")), "| blocks identical to run 1:", blk(p1) == blk(p2), "| chunk type", p2["output"]["chunks"][0]["type"], len(p2["output"]["chunks"]))
print(" processor config returned:", json.dumps({k: prev["config"].get(k) for k in ("baseProcessor", "baseVersion")}), "parse engine version:", p1["config"].get("engineVersion"))

print("## b. Word automatic numbering")
d = Document()
for t in ["Definitions", "Services"]:
    d.add_paragraph(t, style="List Number")
    d.add_paragraph("Supplier shall provide the Services to Customer under this Agreement.")
d.add_paragraph("first bullet item", style="List Bullet")
buf = io.BytesIO(); d.save(buf)
fid = upload("autonum.docx", buf.getvalue())
pj = parse(fid)
for ch in pj["output"]["chunks"]:
    for x in ch["blocks"]:
        print("  ", x["type"], repr(x["content"][:90]))

print("## c. failure cases")
for name, data in [("corrupt.pdf", b"not a pdf at all"), ("corrupt.docx", b"not a docx")]:
    fid = upload(name, data)
    if fid:
        pj = parse(fid)
        if pj: print("  ", name, pj.get("status"), pj.get("failureReason"), (pj.get("failureMessage") or "")[:150])
# blank page pdf
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (850, 1100), "white").save(buf, format="PDF")
fid = upload("blank.pdf", buf.getvalue())
pj = parse(fid)
if pj: print("   blank.pdf", pj.get("status"), pj.get("failureReason"), "blocks:", sum(len(ch["blocks"]) for ch in (pj.get("output") or {}).get("chunks", [])), "content len:", sum(len(ch["content"]) for ch in (pj.get("output") or {}).get("chunks", [])))

print("## d. are citation quotes findable in the parsed text?")
norm = lambda s: re.sub(r"\s+", " ", s).strip()
for f in sorted(glob.glob(str(OUT / "msa_*_extract.json"))):
    e = json.load(open(f)); p = json.load(open(f.replace("_extract.json", "_parse.json")))
    text = "\n\n".join(x["content"] for ch in p["output"]["chunks"] for x in ch["blocks"])
    tot = exact = loose = nocite = 0; misses = []
    for k, m in e["output"]["metadata"].items():
        if "[" in k and "." not in k: continue
        cites = (m or {}).get("citations") or []
        if not cites: nocite += 1; continue
        for ci in cites:
            q = ci.get("referenceText") or ""
            tot += 1
            if q in text: exact += 1
            elif norm(q) in norm(text): loose += 1
            else: misses.append((k, q[:70]))
    print(f"  {Path(f).stem:36} citations {tot}: exact {exact}, whitespace-only diff {loose}, not found {len(misses)}; fields with no citation {nocite}")
    for m in misses[:4]: print("      miss", m)
nc = [k for k, m in json.load(open(OUT / "msa_runin_pdf_light_extract.json"))["output"]["metadata"].items() if not (m or {}).get("citations")]
print("  fields without citations (runin pdf light):", nc[:60])
