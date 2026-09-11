# FEEDIT Tokenizer

토크나이저 관련 코드/학습 자산은 모두 이 폴더 안에서 관리합니다.

```text
analysis/tokenizer/
├─ __init__.py
├─ tokenizer.py
├─ corpus_generator.py
├─ resources/
│  └─ sentencepiece/
├─ data/
│  └─ corpora/
└─ notebooks/
```

팀원 공용 사용:

```python
from analysis.tokenizer import tokenize

result = tokenize("커브드 코튼 와이드 팬츠")
```

DictionaryTerm / TermAlias 변경 후:

```python
from analysis.tokenizer import reload_tokenizer_dictionary
reload_tokenizer_dictionary()
```

Corpus 생성:

```python
from analysis.tokenizer import FeedItCorpusGenerator

generator = FeedItCorpusGenerator(
    output_path="analysis/tokenizer/data/corpora/feedit_product_corpus.txt",
    source_codes=["MUSINSA", "ZIGZAG"],
)

stats = generator.generate()
print(stats.to_dict())
```

- `tokenizer.py`: 실제 semantic tokenizer
- `corpus_generator.py`: ProductSource.source_name 기반 corpus 생성
- `resources/sentencepiece/`: .model / .vocab
- `data/corpora/`: 생성 corpus
- `notebooks/`: tokenizer 실험 notebook
