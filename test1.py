import spacy
from gliner import GLiNER

# 1. 모델 로드 
nlp = spacy.load("ko_core_news_sm")
# 한국어에 더 강한 모델로 설정
gliner_model = GLiNER.from_pretrained("taeminlee/gliner_ko")

text = "일론 머스크가 화성 이민 프로젝트에 300만원을 투자하면 연 30% 수익을 보장합니다"

# 2. spaCy 의존 파싱 
print("=== spaCy 구조 분석 결과 ===")
doc = nlp(text)
for token in doc:
    print(f"{token.text} \t→ 역할: {token.dep_} \t(연결된 단어: {token.head.text})")

# 3. GLiNER 엔티티 추출
labels = ["인물", "금액", "수익률", "장소", "투자 상품"]
entities = gliner_model.predict_entities(text, labels)

print("\n=== GLiNER 개체명 추출 결과 ===")
for e in entities:
    print(f"{e['text']} \t→ {e['label']}")