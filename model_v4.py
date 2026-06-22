import pandas as pd                                           # 데이터 처리
from sklearn.model_selection import train_test_split          # 분할
from sklearn.linear_model import LogisticRegression           # 로지스틱 회귀
from sklearn.metrics import (accuracy_score, f1_score,        # 평가지표
                             precision_score, recall_score, confusion_matrix)

# ── 1. 로드 및 공통 파생변수 ────────────────────────────────
votes = pd.read_parquet("votes_raw_22.parquet")
bills = pd.read_csv("bills_22.csv", dtype=str)
df = votes.merge(bills[["BILL_ID", "BILL_KIND_CD"]], on="BILL_ID", how="left")
df["ym"] = pd.to_datetime(df["VOTE_DATE"], errors="coerce").dt.to_period("M").astype(str)
df["label"] = (df["RESULT_VOTE_MOD"] == "불참").astype(int)   # 불참=1

# 피처1: 정당×시점 상호작용 (결합 범주)
df["poly_x_ym"] = df["POLY_NM"] + "_" + df["ym"]
# 피처2: 의원 식별 → MONA_CD 그대로 사용
# 피처5: 쟁점 안건 플래그 (안건명에 정쟁 키워드 포함 여부)
KW = "방송|내란|계엄|검사|특검|탄핵|감사|상속세"
df["is_hot"] = df["BILL_NAME"].fillna("").str.contains(KW).astype(int)

df = df.dropna(subset=["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD", "ym"])
df = df[df["ym"] != "NaT"]
y = df["label"]

# ── 2. 단계별 feature 집합 정의 (누적) ─────────────────────
steps = {
    "v3 베이스(정당+위원회+분야+시점)": ["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD", "ym"],
    "+1 정당×시점 상호작용":            ["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD", "ym", "poly_x_ym"],
    "+2 의원식별(MONA_CD)":             ["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD", "ym", "poly_x_ym", "MONA_CD"],
    "+5 쟁점안건 플래그":               ["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD", "ym", "poly_x_ym", "MONA_CD", "is_hot"],
}

# ── 3. 단계별 학습·평가 ────────────────────────────────────
def evaluate(cols):
    X = pd.get_dummies(df[cols].astype(str))                 # 모두 범주형 취급 → 원핫
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)    # 동일 분할(random_state 고정)
    m = LogisticRegression(max_iter=1000, class_weight="balanced")
    m.fit(Xtr, ytr)
    p = m.predict(Xte)
    return {
        "정확도": accuracy_score(yte, p),
        "F1(불참)": f1_score(yte, p),
        "정밀도": precision_score(yte, p),
        "재현율": recall_score(yte, p),
        "TP": confusion_matrix(yte, p)[1, 1],                # 불참 적중 수
    }

rows = []
for name, cols in steps.items():
    r = evaluate(cols)
    rows.append({"단계": name, **r})
    print(f"[완료] {name}  F1={r['F1(불참)']:.4f}")

# ── 4. 비교표 출력 ─────────────────────────────────────────
pd.set_option("display.unicode.east_asian_width", True)
res = pd.DataFrame(rows).set_index("단계")
print("\n=== 단계별 성능 비교 ===")
print(res.round(4).to_string())
