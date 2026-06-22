import pandas as pd                                           # 데이터 처리
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, accuracy_score

# ── 1. 데이터 및 파생변수 (v4와 동일) ──────────────────────
votes = pd.read_parquet("votes_raw_22.parquet")
bills = pd.read_csv("bills_22.csv", dtype=str)
df = votes.merge(bills[["BILL_ID", "BILL_KIND_CD"]], on="BILL_ID", how="left")
df["ym"] = pd.to_datetime(df["VOTE_DATE"], errors="coerce").dt.to_period("M").astype(str)
df["label"] = (df["RESULT_VOTE_MOD"] == "불참").astype(int)
df["poly_x_ym"] = df["POLY_NM"] + "_" + df["ym"]
df = df.dropna(subset=["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD", "ym"])
df = df[df["ym"] != "NaT"].reset_index(drop=True)
y = df["label"]
groups = df["MONA_CD"]                                        # 의원 단위 분할용 그룹키

BASE = ["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD", "ym", "poly_x_ym"]  # 일반화 피처
WITH_MONA = BASE + ["MONA_CD"]                                # 의원식별 포함

def metrics(ytr_idx, yte_idx, cols):
    """주어진 train/test 인덱스와 feature로 학습·평가 → 지표 dict 반환"""
    X = pd.get_dummies(df[cols].astype(str))                 # 전체에서 원핫(컬럼 정렬 일치)
    m = LogisticRegression(max_iter=1000, class_weight="balanced")
    m.fit(X.iloc[ytr_idx], y.iloc[ytr_idx])                  # train으로 학습
    p = m.predict(X.iloc[yte_idx])                           # test 예측
    yte = y.iloc[yte_idx]
    return {"정확도": accuracy_score(yte, p), "F1(불참)": f1_score(yte, p),
            "정밀도": precision_score(yte, p), "재현율": recall_score(yte, p)}

# ── 2. 분할 두 종류 준비 ───────────────────────────────────
# (a) 무작위 분할: 같은 의원이 train/test 양쪽에 섞임
rnd_tr, rnd_te = train_test_split(range(len(df)), test_size=0.2,
                                  random_state=42, stratify=y)
# (b) 의원 단위 분할: test에는 train에 없던 의원만 등장
gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
grp_tr, grp_te = next(gss.split(df, y, groups))

# 검증: 의원 단위 분할에서 train/test 의원이 안 겹치는지 확인
overlap = set(groups.iloc[grp_tr]) & set(groups.iloc[grp_te])
print(f"의원 단위 분할 → train 의원 {groups.iloc[grp_tr].nunique()}명, "
      f"test 의원 {groups.iloc[grp_te].nunique()}명, 겹침 {len(overlap)}명")

# ── 3. 세 조건 평가 ────────────────────────────────────────
rows = {
    "① 무작위 분할 + MONA_CD":        metrics(rnd_tr, rnd_te, WITH_MONA),
    "② 의원분할 + MONA_CD(처음보는의원)": metrics(grp_tr, grp_te, WITH_MONA),
    "③ 의원분할 + MONA_CD 제거":       metrics(grp_tr, grp_te, BASE),
}
pd.set_option("display.unicode.east_asian_width", True)
print("\n=== 과적합(암기) 점검 ===")
print(pd.DataFrame(rows).T.round(4).to_string())
