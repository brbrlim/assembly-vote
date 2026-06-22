"""공유 미리보기용 브랜드 OG 이미지 생성 → out/og.png (1200×630)."""
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
NAVY, GOLD, WHITE, MUTED = "#16213e", "#f3c14b", "#ffffff", "#9fb0cc"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"

def font(sz, idx=2):
    try: return ImageFont.truetype(FONT, sz, index=idx)
    except Exception: return ImageFont.truetype(FONT, sz)

img = Image.new("RGB", (W, H), NAVY)
d = ImageDraw.Draw(img)

# 상단 골드 액센트 바
d.rectangle([0, 0, W, 10], fill=GOLD)

# 워드마크: 좌우(골드) + 지간(흰) — 가운데 정렬
big = font(150, idx=8)
left, right = "좌우", "지간"
w1 = d.textlength(left, font=big); w2 = d.textlength(right, font=big)
x0 = (W - (w1 + w2)) / 2; y0 = 200
d.text((x0, y0), left, font=big, fill=GOLD)
d.text((x0 + w1, y0), right, font=big, fill=WHITE)

# 태그라인
tag = "좌든 우든, 표결은 팩트로"
tf = font(52, idx=5)
d.text(((W - d.textlength(tag, font=tf)) / 2, y0 + 185), tag, font=tf, fill=WHITE)

# 하단 설명
sub = "22대 국회 표결 · 시민 데이터 피드"
sf = font(34, idx=2)
d.text(((W - d.textlength(sub, font=sf)) / 2, y0 + 270), sub, font=sf, fill=MUTED)

img.save("out/og.png")
print("✅ out/og.png 생성 (1200x630)")
