# FEEDIT STEP03 Vision Style

STEP02 텍스트 정규화 이후 STYLE ProductTerm이 없는 ProductSource만
FashionSigLIP2 + LoRA(en)로 분석한다.

정책:

- STYLE이 하나라도 있으면 즉시 SKIP
- 대표 이미지가 없으면 SKIP
- LoRA 10개 클래스 중 Top1만 사용
- 기존 ProductTerm 삭제 없음
- STEP02 normalized attributes 수정 없음
- ProductTerm relation_type = HAS_STYLE
- 모델은 프로세스당 한 번만 로드
- 고정된 10개 text embedding도 한 번만 계산

## 1. 위치

이 폴더를 다음 위치에 둔다.

pipeline/step03_vision/

## 2. 학습 prompt 생성

LoRA는 학습 당시 lora_pair_v11_en.csv의 `text`를 사용했으므로
운영 추론에서도 같은 영문 description을 사용해야 한다.

python -m pipeline.step03_vision.build_prompts C:\path\to\lora_pair_v11_en.csv

생성 파일:

pipeline/step03_vision/assets/style_prompts_en.json

## 3. 의존성

pip install torch transformers peft pillow requests pandas

CUDA 환경 권장.

## 4. 1개 predict-only 테스트

python -m pipeline.step03_vision.test_one 31744

DB에는 저장하지 않는다.

## 5. 1개 실제 저장

python -m pipeline.step03_vision.test_one 31744 --save

단, 해당 ProductSource에 STYLE ProductTerm이 이미 있으면 SKIP한다.

## 6. 소량 백필

python -m pipeline.step03_vision.backfill --source musinsa --limit 10 --dry-run

확인 후:

python -m pipeline.step03_vision.backfill --source musinsa --limit 10

## 7. 전체 백필

python -m pipeline.step03_vision.backfill --source musinsa

## 8. 크롤링 pipeline 연결

STEP02 저장이 끝난 뒤 호출한다.

from pipeline.step03_vision import ProductVisionPipeline

vision_pipeline = ProductVisionPipeline()

result = vision_pipeline.run(
    product_source,
    save=True,
)

STYLE이 STEP02에서 이미 잡혔다면 모델 추론 전에 SKIP한다.
