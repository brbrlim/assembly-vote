"""쟁점·화제 안건 개요 일괄 생성 (Gemini). 행 방지를 위해 안건마다 별도 프로세스+타임아웃.
대상: 쟁점 태그 있거나 화제도>=85, 개요 없는 안건. 화제순. 재개 가능.
"""
import os, re, json, sys, subprocess
import pandas as pd

STORE = "overviews_gemini.json"
TIMEOUT = 150           # 안건당 최대 초(초과 시 스킵 — 행 방지)

h = open("assembly_votes.html", encoding="utf-8").read()
d = json.loads(re.search(r"const DATA = (\{.*?\});\nconst PC", h, re.S).group(1))
bills = pd.read_csv("bills_22.csv", dtype=str)
n2id = dict(zip(bills["BILL_NO"], bills["BILL_ID"]))

def done_set():
    s = json.load(open(STORE, encoding="utf-8")) if os.path.exists(STORE) else {}
    demo = set(json.load(open("overviews.json", encoding="utf-8"))) if os.path.exists("overviews.json") else set()
    return set(s) | demo

done0 = done_set()
targets = []
for b in d["bills"]:
    if b["overview"] or not (b["tags"] or b["buzz"] >= 85):
        continue
    bid = n2id.get(b["no"])
    if bid and bid not in done0:
        targets.append((b["buzz"], bid, b["name"][:30]))
targets.sort(reverse=True)
print(f"대상 {len(targets)}건 (개요 없음). 안건당 타임아웃 {TIMEOUT}s", flush=True)

ok = err = to = 0
for i, (buzz, bid, nm) in enumerate(targets, 1):
    if bid in done_set():                         # 재시작 시 이미 된 것 스킵
        continue
    try:
        r = subprocess.run([sys.executable, "gen_gemini_verified.py", bid],
                           timeout=TIMEOUT, capture_output=True, text=True)
        if bid in done_set():
            ok += 1; print(f"  [{i}/{len(targets)}] ✅ 🔥{buzz} {nm}", flush=True)
        else:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
            err += 1; print(f"  [{i}/{len(targets)}] ⚠️ {nm}: {tail[0][:60]}", flush=True)
    except subprocess.TimeoutExpired:
        to += 1; print(f"  [{i}/{len(targets)}] ⏱ {nm}: {TIMEOUT}s 초과 스킵", flush=True)

print(f"완료: 성공 {ok} / 실패 {err} / 시간초과 {to} / 전체개요 {len(done_set())}건", flush=True)
