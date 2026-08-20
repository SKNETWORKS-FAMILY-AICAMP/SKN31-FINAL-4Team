# FEEDIT YouTube Audio → Whisper Large V3 Turbo 전환 지시서

## 1. 목적

기존 `youtube-transcript-api` 기반 자막 수집에서 발생하는 `IpBlocked` 문제와 자막 미제공 영상 문제를 줄이기 위해,  
**YouTube 영상의 오디오를 `yt-dlp`로 천천히 수집하고 `openai/whisper-large-v3-turbo`로 직접 음성 인식(STT)하는 파이프라인**으로 전환한다.

대상 프로젝트는 FEEDIT의 YouTube 패션 트렌드 데이터 수집 파이프라인이다.

최종 흐름은 다음과 같다.

```text
YouTube Video
    ↓
yt-dlp
    ↓
가벼운 압축 오디오 파일
    ↓
Whisper Large V3 Turbo
    ↓
timestamp 포함 transcript
    ↓
기존 Fashion Chunking
    ↓
TREND_SIGNAL
UP / DOWN / NEUTRAL
    ↓
timestamp TXT 저장
```

---

## 2. 반드시 사용할 모델

Hugging Face 모델:

```text
openai/whisper-large-v3-turbo
```

모델 페이지:

```text
https://huggingface.co/openai/whisper-large-v3-turbo
```

다른 Whisper 모델로 임의 변경하지 않는다.

현재 개발 PC에는 **VRAM 8GB NVIDIA GPU**가 있다.

따라서 기본 실행 설정은 다음을 우선한다.

```python
device = "cuda:0"
torch_dtype = torch.float16
```

8GB VRAM 안정성을 우선하여:

- 기본 `batch_size=1`
- 긴 오디오는 chunk 단위 처리
- 모델은 한 번만 로드하고 여러 영상에서 재사용
- 영상마다 모델을 다시 로드하지 말 것
- CUDA OOM 발생 시 자동으로 batch size를 더 낮추는 구조 필요
- 필요 이상으로 GPU에 여러 모델을 동시에 올리지 말 것

---

# 3. 전체 구현 목표

기존 YouTube 파이프라인을 완전히 삭제하지 말고 다음 구조로 만든다.

```text
1. YouTube 영상 목록 수집
2. 이미 처리된 video_id인지 DB 확인
3. 미처리 영상만 yt-dlp로 오디오 수집
4. Whisper Large V3 Turbo로 STT
5. segment timestamp + text 저장
6. 기존 fashion chunking 실행
7. TREND_SIGNAL 분석
8. 성공 시 오디오 파일 삭제 가능
9. 실패 시 상태 기록
10. 다음 실행에서 이어서 처리
```

반드시 **순차 처리**가 가능해야 한다.

프로그램이 중간에 종료되어도 처음부터 다시 받지 않는다.

---

# 4. yt-dlp 사용 정책

## 핵심 요구사항

YouTube에 요청을 너무 빠르게 보내지 않는다.

대량 다운로드를 공격적으로 실행하지 말고 **영상 하나씩 순차 처리**한다.

병렬 다운로드는 사용하지 않는다.

```text
MAX_CONCURRENT_DOWNLOADS = 1
```

각 영상 다운로드 전후에 랜덤한 대기 시간을 둔다.

초기 기본값:

```text
DOWNLOAD_SLEEP_MIN = 8초
DOWNLOAD_SLEEP_MAX = 20초
```

예:

```python
import random
import time

time.sleep(random.uniform(8, 20))
```

고정된 간격보다 랜덤 interval을 사용한다.

추가적으로 yt-dlp 자체의 sleep 옵션도 설정한다.

Python API 기준 예시:

```python
ydl_opts = {
    "sleep_interval": 8,
    "max_sleep_interval": 20,
}
```

단, 우리 코드 자체에서도 영상 단위 sleep을 적용하여 너무 빠른 연속 요청을 피한다.

---

# 5. 비디오가 아니라 오디오만 다운로드

영상은 필요하지 않다.

반드시 audio-only format을 선택한다.

기본:

```python
"format": "bestaudio/best"
```

하지만 최종 저장본은 원본 고음질을 그대로 장기 보관하지 않는다.

목적은 음악 감상이 아니라 **한국어 음성 인식(STT)** 이므로 용량을 우선 줄인다.

---

# 6. 오디오 저장 형식

## WAV 장기 저장 금지

다음 방식은 사용하지 않는다.

```text
.wav
PCM
무압축 오디오
```

10분~30분 영상이 수십~수백 개 쌓이면 저장 공간을 지나치게 사용한다.

## 권장 저장 형식

가능하면 최종 파일을 다음과 같이 만든다.

```text
Ogg Opus
mono
16 kHz
24~32 kbps
```

예:

```text
audio/{video_id}.opus
```

FFmpeg 기준 예:

```bash
ffmpeg -i INPUT   -vn   -ac 1   -ar 16000   -c:a libopus   -b:a 32k   OUTPUT.opus
```

목표:

- mono
- 16 kHz
- speech 중심
- 24~32 kbps 수준
- STT 품질을 크게 훼손하지 않는 범위에서 최대한 작은 파일

기본 bitrate는 우선:

```text
32 kbps
```

로 설정한다.

추후 테스트 후 24 kbps까지 낮출 수 있도록 config로 분리한다.

```python
AUDIO_BITRATE = "32k"
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
```

---


# 6-1. FFmpeg 사용은 필수 권장 사항으로 고정

본 파이프라인에서는 **FFmpeg를 사용한다.**

Whisper 자체는 FFmpeg 없이도 일부 입력 형식을 처리할 수 있지만, FEEDIT에서는 다음 이유로 FFmpeg를 기본 의존성으로 둔다.

```text
1. yt-dlp가 내려받는 webm / m4a 등 다양한 오디오 형식의 안정적 처리
2. 오디오를 16kHz / mono로 통일
3. 장기 저장용 Opus 24~32kbps 변환
4. Whisper 입력 시 디스크에 WAV를 만들지 않고 메모리 PCM으로 decode
5. Windows 환경에서 codec 차이로 인한 오류 최소화
```

따라서 최종 설계는 다음을 기본으로 한다.

```text
YouTube
 ↓
yt-dlp
 ↓
원본 audio-only (webm / m4a 등)
 ↓
FFmpeg
 ↓
16kHz / mono / Opus 32kbps
 ↓
Whisper Large V3 Turbo
```

FFmpeg를 제거하는 방향으로 임의 단순화하지 않는다.

---

# 6-2. FFmpeg 설치 및 시작 전 검사

Windows 개발 환경에서 FFmpeg가 설치되어 있어야 한다.

PowerShell 확인:

```powershell
ffmpeg -version
```

설치되어 있지 않다면 예:

```powershell
winget install Gyan.FFmpeg
```

설치 후 새 터미널을 열고 다시:

```powershell
ffmpeg -version
```

을 실행하여 PATH 등록 여부를 확인한다.

프로그램 시작 시 FFmpeg 존재 여부를 반드시 검사한다.

```python
import shutil

def ensure_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg를 찾을 수 없습니다. "
            "FFmpeg를 설치하고 PATH를 설정한 뒤 다시 실행하세요."
        )
```

파이프라인 시작 직후:

```python
ensure_ffmpeg()
```

를 호출한다.

---

# 6-3. FFmpeg 변환 정책

yt-dlp가 받은 원본 오디오는 그대로 장기 보관하지 않는다.

FFmpeg로 아래 포맷으로 변환한다.

```text
codec: libopus
sample rate: 16000 Hz
channels: mono
bitrate: 32 kbps
```

Python subprocess 예시:

```python
import subprocess
from pathlib import Path

def convert_to_opus(input_path: str, output_path: str) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "libopus",
        "-b:a", "32k",
        output_path,
    ]

    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
```

변환 성공 후 yt-dlp 원본 임시 파일은 삭제한다.

```text
tmp/video.webm
 ↓ FFmpeg 성공
audio/video.opus 생성
 ↓
tmp/video.webm 삭제
```

FFmpeg 변환 실패 시 원본 임시 파일은 삭제하지 않는다.

---

# 6-4. Whisper 입력용 FFmpeg 메모리 디코딩

Whisper 추론 직전에 `.opus` 파일을 다시 WAV 파일로 저장하지 않는다.

FFmpeg의 stdout을 사용하여 **16kHz mono float32 PCM을 메모리로 직접 읽는다.**

권장 구현:

```python
import subprocess
import numpy as np

def decode_audio_for_whisper(path: str) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-i", path,
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ac", "1",
        "-ar", "16000",
        "pipe:1",
    ]

    process = subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    audio = np.frombuffer(
        process.stdout,
        dtype=np.float32,
    )

    return audio
```

Whisper에는 다음처럼 전달한다.

```python
audio_array = decode_audio_for_whisper(audio_path)

result = asr_pipe(
    {
        "array": audio_array,
        "sampling_rate": 16000,
    },
    chunk_length_s=30,
    batch_size=1,
    return_timestamps=True,
    generate_kwargs={
        "language": "korean",
        "task": "transcribe",
    },
)
```

이렇게 하면 다음 장점이 있다.

```text
✅ 디스크에 WAV 생성 안 함
✅ 저장 공간 절약
✅ Whisper 입력 sample rate 고정
✅ webm / m4a / opus codec 차이 제거
✅ Windows codec 관련 문제 감소
```

---

# 6-5. yt-dlp와 FFmpeg 역할 분리

역할을 명확하게 분리한다.

```text
yt-dlp
→ YouTube에서 audio-only 스트림 획득

FFmpeg
→ 오디오 변환 / 압축 / sample rate 통일 / decode

Whisper
→ STT
```

yt-dlp의 FFmpeg postprocessor를 사용해도 되지만, 상태 관리와 오류 추적을 쉽게 하기 위해 FEEDIT에서는 가능하면:

```text
yt-dlp download
→ 다운로드 성공 확인
→ FFmpeg subprocess 변환
→ 변환 성공 확인
→ 임시 파일 삭제
```

처럼 단계를 분리하는 것을 우선한다.

각 단계별 상태와 오류를 DB / 로그에서 구분할 수 있어야 한다.

예:

```text
DOWNLOAD_FAILED
FFMPEG_CONVERT_FAILED
TRANSCRIBE_FAILED
```

---

# 6-6. FFmpeg 로그

FFmpeg 실행 결과도 사용자 로그에서 확인 가능하도록 한다.

성공:

```text
[FFMPEG] converting VIDEO_ID
[FFMPEG DONE] webm -> opus
[FFMPEG] 16000 Hz / mono / 32 kbps
```

실패:

```text
[FFMPEG ERROR] VIDEO_ID
[FFMPEG ERROR] <stderr summary>
```

전체 FFmpeg stderr를 무조건 콘솔에 쏟지 말고, 실패 시 핵심 메시지만 출력한다.

필요하면 상세 로그 파일에 전체 stderr를 저장한다.

---

# 6-7. 오디오 용량 최적화 기준

기본값은:

```python
AUDIO_CODEC = "libopus"
AUDIO_BITRATE = "32k"
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
```

으로 고정한다.

추후 실제 패션 유튜브 영상으로 STT 품질을 비교한 뒤:

```text
32 kbps → 24 kbps
```

로 낮출 수 있다.

단, Codex가 초기 구현 단계에서 임의로 16kbps 이하까지 낮추지 않는다.

목표는:

```text
최대한 가볍게
+
Whisper 한국어 인식 품질 유지
```

의 균형이다.


# 7. yt-dlp + FFmpeg 처리 방식

추천 흐름:

```text
YouTube
 ↓
yt-dlp 임시 audio-only 파일
 ↓
FFmpeg
 ↓
16kHz mono Opus
 ↓
원본 임시 파일 삭제
```

예상 디렉터리:

```text
data/
└─ youtube/
   ├─ audio/
   │  ├─ VIDEO_ID_1.opus
   │  ├─ VIDEO_ID_2.opus
   │  └─ ...
   ├─ transcripts/
   └─ fashion_chunks.jsonl
```

임시 파일은:

```text
data/youtube/tmp/
```

에 저장하고 변환 성공 후 제거한다.

---

# 8. Whisper Large V3 Turbo 로딩

권장 구현 예시:

```python
import torch
from transformers import (
    AutoModelForSpeechSeq2Seq,
    AutoProcessor,
    pipeline,
)

MODEL_ID = "openai/whisper-large-v3-turbo"

device = "cuda:0" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

model = AutoModelForSpeechSeq2Seq.from_pretrained(
    MODEL_ID,
    torch_dtype=torch_dtype,
    low_cpu_mem_usage=True,
    use_safetensors=True,
)

model.to(device)

processor = AutoProcessor.from_pretrained(MODEL_ID)

asr_pipe = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    torch_dtype=torch_dtype,
    device=device,
)
```

중요:

```text
프로그램 시작
 ↓
Whisper 모델 1회 로드
 ↓
영상 A 처리
 ↓
영상 B 처리
 ↓
영상 C 처리
```

이어야 한다.

영상마다 `from_pretrained()` 하지 않는다.

---

# 9. 한국어 transcription 설정

FEEDIT 대상 영상은 대부분 한국어 패션 콘텐츠이다.

기본:

```python
generate_kwargs = {
    "language": "korean",
    "task": "transcribe",
}
```

를 사용한다.

예:

```python
result = asr_pipe(
    audio_input,
    return_timestamps=True,
    generate_kwargs={
        "language": "korean",
        "task": "transcribe",
    },
)
```

영어/외국어 영상 대응이 필요한 경우 추후 자동 언어 감지를 옵션화한다.

기본 정책은 한국어 우선이다.

---

# 10. 긴 영상 처리

YouTube 패션 영상은 10~30분 이상일 수 있다.

전체 오디오를 한 번에 GPU에 넣지 않는다.

Whisper/Transformers long-form 처리가 안정적으로 수행되도록 chunk 기반 처리한다.

초기 권장값:

```python
CHUNK_LENGTH_S = 30
BATCH_SIZE = 1
```

예:

```python
result = asr_pipe(
    audio_input,
    chunk_length_s=30,
    batch_size=1,
    return_timestamps=True,
    generate_kwargs={
        "language": "korean",
        "task": "transcribe",
    },
)
```

8GB VRAM 환경에서 안정성을 우선한다.

OOM이 발생하면:

```text
batch_size 1 유지
chunk_length_s 30 → 20
```

순서로 낮춘다.

---

# 11. Opus 파일 입력 처리

Transformers pipeline이 환경에 따라 Opus 파일을 직접 처리하는 과정에서 FFmpeg 의존성이 생길 수 있다.

따라서 안정적인 방법으로 다음 중 하나를 구현한다.

## 권장 방식

FFmpeg를 subprocess로 사용해 `.opus`를 **메모리에서 16kHz mono PCM으로 decode**한 뒤 Whisper에 전달한다.

장기 보관을 위한 WAV 파일은 만들지 않는다.

개념:

```text
video.opus
 ↓
ffmpeg stdout
 ↓
float32 numpy 16kHz mono
 ↓
Whisper
```

예시 함수 구조:

```python
def decode_audio_for_whisper(path):
    # ffmpeg를 이용해 16kHz mono float32 PCM을 stdout으로 읽고
    # numpy array로 반환한다.
    # WAV 파일을 디스크에 생성하지 않는다.
    ...
```

이 방식으로:

- 저장 공간 절약
- 임시 WAV 생성 방지
- Whisper 입력 형식 통일

을 달성한다.

---

# 12. transcript 출력 형식

Whisper 결과는 JSON segment를 최종 사용자 출력으로 보여주는 방식보다,  
**영상 제목 아래에 timestamp가 포함된 텍스트 라인을 순서대로 출력하는 형식**으로 만든다.

기준 형식은 다음과 같다.

```text
영상 제목

[00:00:00.000 --> 00:00:03.840] 첫 번째 문장
[00:00:03.840 --> 00:00:06.720] 두 번째 문장
[00:00:06.720 --> 00:00:09.440] 세 번째 문장
...
```

예:

```text
2026 봄 패션 트렌드 총정리

[00:00:00.000 --> 00:00:04.120] 안녕하세요 오늘은 올해 봄 패션 트렌드를 정리해 볼게요.
[00:00:04.120 --> 00:00:09.360] 요즘 스웨이드 재킷이 정말 많이 보이고 있습니다.
[00:00:09.360 --> 00:00:14.800] 특히 브라운과 카멜 컬러가 많이 나오고 있어요.
```

timestamp는 반드시 아래 규격을 사용한다.

```text
[HH:MM:SS.mmm --> HH:MM:SS.mmm]
```

예:

```text
[00:00:03.840 --> 00:00:06.720]
[00:01:12.400 --> 00:01:18.950]
[01:02:05.120 --> 01:02:11.830]
```

밀리초는 항상 **3자리**로 표시한다.

---

# 13. timestamp 변환 함수

Whisper가 반환한 초 단위 timestamp를 다음 형태로 변환한다.

```python
def format_timestamp(seconds: float) -> str:
    if seconds is None:
        seconds = 0.0

    total_ms = int(round(seconds * 1000))

    hours = total_ms // 3_600_000
    total_ms %= 3_600_000

    minutes = total_ms // 60_000
    total_ms %= 60_000

    secs = total_ms // 1000
    millis = total_ms % 1000

    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
```

segment 출력:

```python
def format_segment(start: float, end: float, text: str) -> str:
    start_ts = format_timestamp(start)
    end_ts = format_timestamp(end)

    return f"[{start_ts} --> {end_ts}] {text.strip()}"
```

예:

```python
line = format_segment(
    3.84,
    6.72,
    "요즘 스웨이드 재킷이 정말 많이 보여요."
)

print(line)
```

출력:

```text
[00:00:03.840 --> 00:00:06.720] 요즘 스웨이드 재킷이 정말 많이 보여요.
```

---

# 14. 영상 제목 + transcript 저장 구조

각 영상마다 **영상 제목을 가장 위에 표시**하고 그 아래에 timestamp transcript를 저장한다.

권장 텍스트 파일:

```text
data/youtube/transcripts/{video_id}.txt
```

내용:

```text
{video_title}

[00:00:00.000 --> 00:00:03.840] ...
[00:00:03.840 --> 00:00:06.720] ...
[00:00:06.720 --> 00:00:09.440] ...
```

예:

```text
요즘 진짜 많이 보이는 2026 패션 아이템

[00:00:00.000 --> 00:00:04.240] 안녕하세요 여러분.
[00:00:04.240 --> 00:00:08.160] 오늘은 요즘 정말 많이 보이는 아이템을 가져왔어요.
[00:00:08.160 --> 00:00:13.520] 첫 번째는 스웨이드 재킷입니다.
```

제목은 `yt-dlp` metadata에서 가져온다.

예:

```python
video_title = info.get("title", video_id)
```

파일 저장:

```python
from pathlib import Path

def save_transcript_txt(
    output_path: Path,
    video_title: str,
    chunks: list,
) -> None:
    lines = [video_title.strip(), ""]

    for chunk in chunks:
        start, end = chunk["timestamp"]
        text = chunk["text"]

        lines.append(
            format_segment(
                start,
                end,
                text,
            )
        )

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
```

---

# 15. Whisper 결과 처리

Whisper inference:

```python
result = asr_pipe(
    audio_input,
    chunk_length_s=30,
    batch_size=1,
    return_timestamps=True,
    generate_kwargs={
        "language": "korean",
        "task": "transcribe",
    },
)
```

결과의 `chunks`를 사용한다.

예:

```python
for chunk in result["chunks"]:
    start, end = chunk["timestamp"]
    text = chunk["text"]

    print(
        format_segment(
            start,
            end,
            text,
        )
    )
```

콘솔에서도 저장 파일과 동일하게 보여준다.

예:

```text
[TRANSCRIPT] 요즘 진짜 많이 보이는 2026 패션 아이템

[00:00:00.000 --> 00:00:04.240] 안녕하세요 여러분.
[00:00:04.240 --> 00:00:08.160] 오늘은 요즘 정말 많이 보이는 아이템을 가져왔어요.
[00:00:08.160 --> 00:00:13.520] 첫 번째는 스웨이드 재킷입니다.
```

---

# 19. 오디오 보존 정책

현재 단계에서는 **Whisper 추출 성공 후에도 오디오 파일을 삭제하지 않는다.**

목표는 우선 다음 파이프라인을 안정적으로 완성하는 것이다.

```text
YouTube
 ↓
yt-dlp
 ↓
FFmpeg
 ↓
16kHz / mono / Opus 32kbps
 ↓
Whisper Large V3 Turbo
 ↓
timestamp transcript TXT
```

따라서 추출된 오디오는 다음처럼 그대로 보존한다.

```text
data/youtube/audio/{video_id}.opus
```

현재는 다음 기능을 구현하지 않는다.

```text
❌ Whisper 성공 후 audio 자동 삭제
❌ DELETE_AUDIO_AFTER_TRANSCRIBE 옵션
❌ 오래된 audio 정리 작업
❌ 자동 cleanup 정책
```

오디오 파일은 추후 전체 파이프라인이 안정화된 후 별도의 정리 정책을 설계한다.

# 20. 다운로드 오류 처리

다음 오류를 구분해 로그에 남긴다.

```text
HTTP 403
HTTP 429
Sign in to confirm you're not a bot
Video unavailable
Private video
Age restricted
Network timeout
```

429나 bot protection 성격의 오류가 연속으로 발생하면 계속 요청하지 않는다.

예:

```text
연속 3회 rate-limit / bot 차단
 ↓
현재 다운로드 batch 중단
 ↓
checkpoint 저장
```

---

# 21. Retry / Backoff

일시적인 네트워크 오류:

```text
retry 1 → 15~30초
retry 2 → 30~60초
retry 3 → 60~120초
```

exponential backoff + jitter를 적용한다.

```python
delay = min(BASE_DELAY * (2 ** retry), MAX_DELAY)
delay += random.uniform(0, JITTER)
```

최대:

```text
MAX_RETRIES = 3
```

---

# 22. Config

```python
MODEL_ID = "openai/whisper-large-v3-turbo"

DOWNLOAD_SLEEP_MIN = 8
DOWNLOAD_SLEEP_MAX = 20

MAX_DOWNLOAD_RETRIES = 3

AUDIO_CODEC = "opus"
AUDIO_BITRATE = "32k"
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1

WHISPER_CHUNK_LENGTH_S = 30
WHISPER_BATCH_SIZE = 1

```

---

# 23. Logging

예:

```text
[AUDIO] 1/127 VIDEO_ID
[AUDIO WAIT] 14.2 sec
[AUDIO DOWNLOADING]
[AUDIO DONE]

[FFMPEG] converting
[FFMPEG DONE] 16kHz / mono / 32kbps opus

[WHISPER] model loaded on cuda:0 / fp16

[TRANSCRIPT] 영상 제목

[00:00:00.000 --> 00:00:04.240] 안녕하세요 여러분.
[00:00:04.240 --> 00:00:08.160] 오늘은 요즘 정말 많이 보이는 아이템을 가져왔어요.

[TRANSCRIPT SAVED] data/youtube/transcripts/VIDEO_ID.txt
```

---

# 24. 설치 패키지

```bash
pip install -U yt-dlp
pip install -U transformers accelerate torch
```

FFmpeg는 필수 권장 의존성으로 사용한다.

Windows 확인:

```powershell
ffmpeg -version
```

프로그램 시작 시:

```python
import shutil

if shutil.which("ffmpeg") is None:
    raise RuntimeError(
        "FFmpeg를 찾을 수 없습니다. "
        "FFmpeg 설치 후 PATH를 설정하세요."
    )
```

---

# 25. 현재 구현 범위

**이번 단계에서는 무엇보다 "YouTube 오디오 추출 → Whisper STT → timestamp TXT 생성"을 우선한다.**

현재 구현 범위는 정확히 다음까지이다.

```text
YouTube 영상 탐색/목록
 ↓
yt-dlp 오디오 다운로드
 ↓
FFmpeg 경량 Opus 변환
 ↓
오디오 파일 보존
 ↓
Whisper Large V3 Turbo
 ↓
timestamp transcript 생성
 ↓
영상 제목 + timestamp TXT 저장
```

이번 단계에서 다음 기능은 구현하지 않는다.

```text
❌ 내부 metadata JSON 저장
❌ 별도 metadata 파일 생성
❌ DB 상태 저장
❌ DB schema 확장
❌ checkpoint DB 구현
❌ 성공 후 오디오 삭제
❌ 자동 cleanup
❌ Fashion Chunker 연결
❌ Fashion relevance 판별
❌ Fashion entity 추출
❌ TREND_SIGNAL
❌ UP / DOWN / NEUTRAL 분류
❌ 트렌드 점수 계산
❌ 추천 시스템 연결
```

Codex는 위 기능들을 미리 구현하지 않는다.

현재 목표는 **오디오 추출과 Whisper transcription이 안정적으로 끝까지 동작하는지 확인하는 것**이다.

# 26. 구현 우선순위

## Milestone 1 — 단일 영상 오디오 추출

```text
YouTube
→ yt-dlp
→ FFmpeg
→ 16kHz / mono / Opus 32kbps
```

오디오가 정상적으로 저장되는지 먼저 확인한다.

## Milestone 2 — 단일 영상 Whisper transcription

```text
Opus
→ FFmpeg 메모리 decode
→ Whisper Large V3 Turbo
→ timestamp transcript TXT
```

최종 출력이 다음 형태인지 확인한다.

```text
영상 제목

[00:00:00.000 --> 00:00:04.240] 문장
[00:00:04.240 --> 00:00:08.160] 문장
```

## Milestone 3 — GPU 안정화

8GB VRAM 기준:

```text
FP16
batch_size=1
chunk_length_s=30
```

으로 안정적으로 동작하는지 확인한다.

## Milestone 4 — 여러 영상 순차 처리

우선 5개 영상으로 테스트한다.

```text
영상 1 다운로드
→ Whisper
→ TXT 저장
→ 오디오 보존
→ 8~20초 랜덤 대기
→ 영상 2
```

동시 다운로드나 동시 Whisper 처리는 하지 않는다.

## Milestone 5 — 전체 대상 확대

5개 영상 테스트가 안정적이면 전체 대상 영상으로 확대한다.

이 단계에서도 DB/metadata/Fashion Chunker는 구현하지 않는다.

# 27. 테스트 체크리스트

```text
[ ] 단일 YouTube 영상 audio-only 다운로드 성공
[ ] FFmpeg Opus 변환 성공
[ ] 16kHz 확인
[ ] mono 확인
[ ] 32kbps 수준 확인
[ ] 추출된 Opus 파일이 삭제되지 않고 남아 있음
[ ] Whisper GPU 실행
[ ] FP16 사용
[ ] 8GB VRAM OOM 없음
[ ] 한국어 STT 정상
[ ] timestamp 생성
[ ] timestamp가 HH:MM:SS.mmm 형태
[ ] 시작/종료 시간이 --> 로 연결됨
[ ] 영상 제목이 transcript 최상단에 표시됨
[ ] transcript TXT 저장
[ ] 모델 1회만 로드
[ ] 5개 영상 순차 처리
[ ] 영상 간 8~20초 랜덤 sleep
[ ] metadata JSON을 만들지 않음
[ ] DB 기능을 추가하지 않음
[ ] audio 자동 삭제를 하지 않음
[ ] Fashion Chunker를 구현하지 않음
```

# 28. 하지 말아야 할 것

```text
❌ youtube-transcript-api를 메인 transcript 소스로 사용
❌ 영상 전체 mp4 다운로드
❌ FFmpeg 제거
❌ WAV 장기 보관
❌ 수십 개 동시 다운로드
❌ 무제한 retry
❌ Whisper 성공 후 Opus 자동 삭제
❌ 내부 metadata JSON 저장
❌ DB 상태 관리 기능 추가
❌ DB schema 확장
❌ 영상마다 Whisper 모델 reload
❌ Fashion Chunker 구현
❌ TREND_SIGNAL 구현
```

# 29. 최종 목표

```text
[START]

127 videos discovered

GPU: NVIDIA ...
VRAM: 8GB
Whisper: openai/whisper-large-v3-turbo
dtype: float16

[1/127]
wait 12.8 sec

yt-dlp
 ↓
FFmpeg
 ↓
16kHz mono 32kbps opus
 ↓
Whisper
 ↓

영상 제목

[00:00:00.000 --> 00:00:04.240] ...
[00:00:04.240 --> 00:00:08.160] ...
[00:00:08.160 --> 00:00:13.520] ...

 ↓
TXT saved
 ↓
Opus audio retained

[DONE]
```

최우선 기준:

```text
1. YouTube 요청을 느리고 안정적으로 수행
2. 중복 다운로드 방지
3. 저장 공간 최소화
4. 8GB VRAM 내 안정적인 Whisper 실행
5. [HH:MM:SS.mmm --> HH:MM:SS.mmm] timestamp 보존
6. 영상 제목 + 사람이 읽기 쉬운 transcript TXT 생성
7. 추출된 Opus 오디오 보존
8. metadata/DB/Fashion Chunker 이후 단계는 현재 구현하지 않음
```

---

# 30. 참고 공식 문서

- Whisper Large V3 Turbo  
  https://huggingface.co/openai/whisper-large-v3-turbo

- yt-dlp  
  https://github.com/yt-dlp/yt-dlp

Codex는 기존 코드베이스를 먼저 분석한 후 현재 구조를 최대한 유지하면서 최소 변경으로 통합한다.

기존 기능을 무작정 삭제하지 말고, 수정 전 기존 YouTube 수집 흐름과 DB schema를 파악한다.

구현 완료 후 다음을 보고한다.

```text
1. 수정한 파일 목록
2. 각 파일에서 변경한 내용
3. 설치해야 하는 패키지
4. 실행 명령어
5. 단일 영상 테스트 결과
6. GPU / VRAM 사용 상태
7. 생성된 오디오 크기
8. transcript TXT 예시
9. 오디오 보존 여부
10. 남아 있는 문제
```
