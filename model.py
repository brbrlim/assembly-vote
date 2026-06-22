import pandas as pd                                           # 데이터 처리
from sklearn.model_selection import train_test_split          # 학습/평가 데이터 분할
from sklearn.linear_model import LogisticRegression           # 로지스틱 회귀 분류기
from sklearn.metrics import accuracy_score                    # 정확도 측정

# ── 1. 데이터 로드 및 결합 ──────────────────────────────────
votes = pd.read_parquet("votes_raw_22.parquet")              # 의원별 표결 누적 데이터
bills = pd.read_csv("bills_22.csv", dtype=str)               # 안건 목록(법안 분야 코드 포함)
# 표결 데이터에 '법안 분야'(BILL_KIND_CD)를 BILL_ID 기준으로 붙임
df = votes.merge(bills[["BILL_ID", "BILL_KIND_CD"]], on="BILL_ID", how="left")

# ── 2. label 정의: 찬성 vs 반대 (기권·불참 제외) ────────────
df = df[df["RESULT_VOTE_MOD"].isin(["찬성", "반대"])].copy()  # 두 클래스만 남김
df["label"] = (df["RESULT_VOTE_MOD"] == "찬성").astype(int)   # 찬성=1, 반대=0 으로 인코딩

# ── 3. feature 선택 (정형 범주형 컬럼) ─────────────────────
features = ["POLY_NM", "CURR_COMMITTEE", "BILL_KIND_CD"]      # 정당 / 위원회 / 법안분야
df = df.dropna(subset=features)                               # 결측 있는 행 제거
X = pd.get_dummies(df[features])                             # 범주형 → 원핫 인코딩(0/1 컬럼들)
y = df["label"]                                               # 예측 대상

# ── 4. 학습/평가 분할 (80/20) ──────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)        # 클래스 비율 유지(stratify)

# ── 5. 모델 학습 ────────────────────────────────────────────
model = LogisticRegression(max_iter=1000)                    # 반복 충분히(수렴 보장)
model.fit(X_train, y_train)                                  # 학습 데이터로 학습

# ── 6. 평가 ────────────────────────────────────────────────
pred = model.predict(X_test)                                 # test 데이터 예측
acc = accuracy_score(y_test, pred)                           # 실제값과 비교한 정확도
print(f"테스트 정확도: {acc:.4f}")

# (참고) 클래스가 매우 불균형하므로 베이스라인도 함께 출력
baseline = y_test.mean()                                      # 전부 '찬성'으로 찍었을 때 정확도
print(f"베이스라인(전부 찬성): {baseline:.4f}  |  찬성 {y_test.sum()} / 반대 {(y_test==0).sum()}")
