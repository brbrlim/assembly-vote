"""누적 표결 raw 데이터(votes_raw_22)로 3가지 분석을 수행한다.
  1) 의원별 찬성/반대/기권 비율  2) 정당별 표결 성향  3) 이견 큰 안건 top N
찬성률 등 비율은 '불참'을 제외한 실제 투표(찬성+반대+기권)를 분모로 한다.
"""
import pandas as pd

df = pd.read_parquet("votes_raw_22.parquet")             # 경량 포맷에서 로드(빠름)
VOTED = ["찬성", "반대", "기권"]                          # 실제 투표로 인정할 값(불참 제외)

# ── 1. 의원별 표결 성향 ─────────────────────────────────────
# 의원 × 표결유형 교차표 → 비율 계산
mp = df.pivot_table(index=["HG_NM", "POLY_NM"], columns="RESULT_VOTE_MOD",
                    values="BILL_ID", aggfunc="count", fill_value=0)
for c in VOTED + ["불참"]:
    if c not in mp: mp[c] = 0                             # 없는 열 보정
mp["투표수"] = mp[VOTED].sum(axis=1)                      # 불참 제외 실제 투표수
mp["찬성률%"] = (mp["찬성"] / mp["투표수"] * 100).round(1)
mp["반대율%"] = (mp["반대"] / mp["투표수"] * 100).round(1)
member_stat = mp.reset_index().sort_values("반대율%", ascending=False)
member_stat.to_csv("stat_member.csv", index=False, encoding="utf-8-sig")

print("=== [1] 반대율 높은 의원 top 10 (불참 제외 기준) ===")
print(member_stat[["HG_NM", "POLY_NM", "투표수", "찬성률%", "반대율%"]]
      .head(10).to_string(index=False))

# ── 2. 정당별 표결 성향 ─────────────────────────────────────
party = df[df["RESULT_VOTE_MOD"].isin(VOTED + ["불참"])] \
    .pivot_table(index="POLY_NM", columns="RESULT_VOTE_MOD",
                 values="BILL_ID", aggfunc="count", fill_value=0)
for c in VOTED + ["불참"]:
    if c not in party: party[c] = 0
party["투표수"] = party[VOTED].sum(axis=1)
party["찬성률%"] = (party["찬성"] / party["투표수"] * 100).round(1)
party["반대율%"] = (party["반대"] / party["투표수"] * 100).round(1)
party["불참률%"] = (party["불참"] / (party["투표수"] + party["불참"]) * 100).round(1)
party = party.sort_values("투표수", ascending=False)
party.to_csv("stat_party.csv", encoding="utf-8-sig")

print("\n=== [2] 정당별 표결 성향 ===")
print(party[["찬성", "반대", "기권", "불참", "찬성률%", "반대율%", "불참률%"]]
      .to_string())

# ── 3. 이견(반대+기권)이 큰 안건 top N ─────────────────────
g = df.pivot_table(index=["BILL_ID", "BILL_NAME"], columns="RESULT_VOTE_MOD",
                   values="MONA_CD", aggfunc="count", fill_value=0)
for c in VOTED + ["불참"]:
    if c not in g: g[c] = 0
g["반대기권"] = g["반대"] + g["기권"]                     # 이견 규모
g["투표수"] = g[VOTED].sum(axis=1)
g["반대기권%"] = (g["반대기권"] / g["투표수"] * 100).round(1)
contested = g.reset_index().sort_values("반대기권", ascending=False)
contested.to_csv("stat_contested.csv", index=False, encoding="utf-8-sig")

print("\n=== [3] 이견 큰 안건 top 10 (반대+기권 많은 순) ===")
print(contested[["BILL_NAME", "찬성", "반대", "기권", "반대기권%"]]
      .head(10).to_string(index=False))

print("\n저장: stat_member.csv / stat_party.csv / stat_contested.csv")
