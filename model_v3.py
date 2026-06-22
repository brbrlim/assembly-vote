import pandas as pd                                           # 데이터 처리
from sklearn.model_selection import train_test_split          # 학습/평가 분할
from sklearn.linear_model import LogisticRegression           # 로지스틱 회귀
from sklearn.metrics import (accuracy_score, f1_score,        # 평가지표
                             confusion_matrix, classification_report)

# ── 1. 데이터 로드 및 결합 ──────────────────────────────────
votes = pd.read_parquet("votes_raw_22.parquet")              # 표결 누적 데이터
bills = pd.read_csv("bills_22.csv", dtype=str)               # 안건 목록(법안 분야)
df = votes.merge(bills[["BILL_ID", "BILL_KIND_CD"]], on="BILL_ID", how="left")

# ── 2. 시점 feature 생성: 표결 연-월 ───────────────────────
# VOTE_DATE를 날짜로 파싱해 '2025-06' 형태의 월 문자열로 변환 (보이콧 급등기 포착용)
df["ym"] = pd.to_datetime(df["VOTE_DATE"], errors="coerce").dt.to_period("M").astype(str)

# ── 3. label: 불참(1) vs 참석(0) ──────────────────────────
df["label"] = (df["RESULT_VOTE_MOD"] == "불참").astype(int)

# ── 4. feature 선택 (정당·위원회·법안분야 + 시점) ──────────
features = ["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD", "ym"]  # ym 추가됨
df = df.dropna(subset=features)                               # 결측 행 제거
df = df[df["ym"] != "NaT"]                                    # 날짜 파싱 실패 행 제거
X = pd.get_dummies(df[features])                             # 범주형 → 원핫 인코딩
y = df["label"]

# ── 5. 학습/평가 분할 (80/20, 클래스 비율 유지) ────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

# ── 6. 모델 학습 (불균형 보정) ─────────────────────────────
model = LogisticRegression(max_iter=1000, class_weight="balanced")
model.fit(X_train, y_train)

# ── 7. 평가 ────────────────────────────────────────────────
pred = model.predict(X_test)
print(f"정확도(accuracy): {accuracy_score(y_test, pred):.4f}")
print(f"F1 (불참 클래스): {f1_score(y_test, pred):.4f}")
print(f"베이스라인(전부 참석): {1 - y_test.mean():.4f}")

cm = confusion_matrix(y_test, pred)
print("\n혼동행렬 [행=실제, 열=예측]")
print(pd.DataFrame(cm, index=["실제:참석", "실제:불참"],
                   columns=["예측:참석", "예측:불참"]).to_string())

print("\n분류 리포트")
print(classification_report(y_test, pred, target_names=["참석", "불참"], digits=3))
