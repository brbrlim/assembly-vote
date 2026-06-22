import pandas as pd                                           # 데이터 처리
from sklearn.model_selection import train_test_split          # 학습/평가 분할
from sklearn.linear_model import LogisticRegression           # 로지스틱 회귀
from sklearn.metrics import (accuracy_score, f1_score,        # 평가지표
                             confusion_matrix, classification_report)

# ── 1. 데이터 로드 및 결합 ──────────────────────────────────
votes = pd.read_parquet("votes_raw_22.parquet")              # 표결 누적 데이터
bills = pd.read_csv("bills_22.csv", dtype=str)               # 안건 목록(법안 분야)
df = votes.merge(bills[["BILL_ID", "BILL_KIND_CD"]], on="BILL_ID", how="left")

# ── 2. label 재정의: 불참 vs 참석 ──────────────────────────
# 찬성/반대/기권 = 표결 참석(0), 불참 = 보이콧(1)
df["label"] = (df["RESULT_VOTE_MOD"] == "불참").astype(int)   # 불참=1, 참석=0

# ── 3. feature 선택 ────────────────────────────────────────
features = ["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD"]      # 정당 / 위원회 / 법안분야
df = df.dropna(subset=features)                               # 결측 행 제거
X = pd.get_dummies(df[features])                             # 범주형 → 원핫 인코딩
y = df["label"]                                               # 예측 대상(불참 여부)

# ── 4. 학습/평가 분할 (80/20, 클래스 비율 유지) ────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

# ── 5. 모델 학습 (불균형 보정) ─────────────────────────────
# class_weight='balanced': 소수 클래스(불참)에 가중치를 줘 실제로 학습하게 함
model = LogisticRegression(max_iter=1000, class_weight="balanced")
model.fit(X_train, y_train)                                  # 학습

# ── 6. 평가: 정확도 + F1 + 혼동행렬 ────────────────────────
pred = model.predict(X_test)                                 # test 예측
print(f"정확도(accuracy): {accuracy_score(y_test, pred):.4f}")
print(f"F1 (불참 클래스): {f1_score(y_test, pred):.4f}")     # 불참을 얼마나 잘 잡나
print(f"베이스라인(전부 참석): {1 - y_test.mean():.4f}")

# 혼동행렬: 행=실제, 열=예측  → 불참을 실제로 몇 개 맞췄는지 확인
cm = confusion_matrix(y_test, pred)
print("\n혼동행렬 [행=실제, 열=예측]")
print(pd.DataFrame(cm, index=["실제:참석", "실제:불참"],
                   columns=["예측:참석", "예측:불참"]).to_string())

# 정밀도/재현율/F1 상세
print("\n분류 리포트")
print(classification_report(y_test, pred, target_names=["참석", "불참"], digits=3))
