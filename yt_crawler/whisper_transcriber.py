"""Sequential YouTube audio transcription with Whisper Large V3 Turbo.

This module intentionally owns only audio download, conversion, transcription,
and timestamped TXT output. It does not write transcript metadata to SQLite or
run the fashion chunker.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

MODEL_ID = "openai/whisper-large-v3-turbo"
DOWNLOAD_SLEEP_MIN = 8.0
DOWNLOAD_SLEEP_MAX = 20.0
MAX_DOWNLOAD_RETRIES = 3
AUDIO_BITRATE = "32k"
AUDIO_SAMPLE_RATE = 16_000
AUDIO_CHANNELS = 1

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "youtube"
AUDIO_DIR = DATA_DIR / "audio"
TMP_DIR = DATA_DIR / "tmp"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
FFMPEG_BINARY: str | None = None

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")


def ensure_ffmpeg() -> str:
    """Resolve FFmpeg from PATH or the standard Windows WinGet install location."""
    global FFMPEG_BINARY
    if FFMPEG_BINARY:
        return FFMPEG_BINARY

    candidates = [shutil.which("ffmpeg")]
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        candidates.extend(
            str(path)
            for path in winget_packages.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe")
            if path.is_file()
        )
    FFMPEG_BINARY = next((candidate for candidate in candidates if candidate), None)
    if not FFMPEG_BINARY:
        raise RuntimeError("FFmpeg was not found. Install FFmpeg and add it to PATH before running transcription.")
    logging.info("[FFMPEG] using %s", FFMPEG_BINARY)
    return FFMPEG_BINARY


def scalar_to_float(value: Any) -> float:
    """Convert Python and PyTorch scalar values into a plain float."""
    if value is None:
        return 0.0
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "item"):
        value = value.item()
    return float(value)


def format_timestamp(seconds: Any) -> str:
    seconds = scalar_to_float(seconds)
    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    secs = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def format_segment(start: float | None, end: float | None, text: str) -> str:
    return f"[{format_timestamp(start)} --> {format_timestamp(end)}] {text.strip()}"


def audio_filename(video_title: str, video_id: str) -> str:
    """Return a Windows-safe filename for transient Opus audio."""
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", video_title).strip().rstrip(".")
    normalized = re.sub(r"\s+", " ", normalized)
    return f"{(normalized or video_id)[:180]}.opus"


def decode_audio_for_whisper(path: Path) -> np.ndarray:
    process = subprocess.run(
        [ensure_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", str(AUDIO_SAMPLE_RATE), "pipe:1"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return np.frombuffer(process.stdout, dtype=np.float32)


def select_korean_audio_format(formats: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Choose Korean original audio, preferring HLS streams over DASH.

    YouTube format IDs are not stable across videos, so selection is based on
    format metadata rather than a hard-coded ID such as ``234-2``. HLS audio is
    preferred because it currently avoids the GVS PO-token checks affecting
    many DASH HTTPS streams.
    """
    candidates: list[dict[str, Any]] = []
    for item in formats:
        if item.get("vcodec") not in (None, "none") or not item.get("acodec"):
            continue
        language = str(item.get("language") or "").lower()
        if language not in {"ko", "kor", "korean"}:
            continue
        candidates.append(item)

    if not candidates:
        raise RuntimeError("No Korean audio-only format was available for this video.")

    def priority(item: dict[str, Any]) -> tuple[int, int, float, float]:
        audio_track = item.get("audio_track") or {}
        is_original = bool(audio_track.get("audio_is_original"))
        protocol = str(item.get("protocol") or "").lower()
        is_hls = protocol.startswith("m3u8")
        return (
            int(is_original),
            int(is_hls),
            float(item.get("abr") or 0),
            float(item.get("asr") or 0),
        )

    return max(candidates, key=priority)


class WhisperTranscriber:
    def __init__(self) -> None:
        ensure_ffmpeg()
        self.model, self.processor, self.device, self.dtype = self._load_model()

    @staticmethod
    def _load_model() -> tuple[Any, Any, str, Any]:
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        use_cuda = torch.cuda.is_available()
        device = "cuda:0" if use_cuda else "cpu"
        dtype = torch.float16 if use_cuda else torch.float32
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            MODEL_ID, torch_dtype=dtype, low_cpu_mem_usage=True, use_safetensors=True,
        )
        model.to(device)
        model.eval()
        processor = AutoProcessor.from_pretrained(MODEL_ID)
        logging.info("[WHISPER] model loaded on %s / %s", device, "fp16" if use_cuda else "fp32")
        return model, processor, device, dtype

    @staticmethod
    def _temporary_audio(video_id: str) -> Path | None:
        matches = sorted(TMP_DIR.glob(f"{video_id}.*"), key=lambda item: item.stat().st_mtime, reverse=True)
        return next((item for item in matches if item.suffix != ".part"), None)

    def download_audio(self, video_id: str) -> tuple[Path, str]:
        import yt_dlp

        TMP_DIR.mkdir(parents=True, exist_ok=True)
        options = {
            "outtmpl": str(TMP_DIR / f"{video_id}.%(ext)s"),
            "noplaylist": True, "quiet": True, "retries": MAX_DOWNLOAD_RETRIES,
            "sleep_interval": int(DOWNLOAD_SLEEP_MIN), "max_sleep_interval": int(DOWNLOAD_SLEEP_MAX),
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            url = f"https://www.youtube.com/watch?v={video_id}"
            info = ydl.extract_info(url, download=False)
            selected = select_korean_audio_format(info.get("formats") or [])
            options["format"] = str(selected["format_id"])
            logging.info(
                "[AUDIO DOWNLOADING] %s (format=%s, protocol=%s, language=%s)",
                video_id, selected["format_id"], selected.get("protocol"), selected.get("language"),
            )
        # Download in a new yt-dlp instance so the chosen per-video format ID is applied.
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
        downloaded = self._temporary_audio(video_id)
        if downloaded is None:
            raise RuntimeError("yt-dlp completed without creating an audio file")
        return downloaded, str(info.get("title") or video_id)

    @staticmethod
    def convert_to_opus(source: Path, video_title: str, video_id: str) -> Path:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        destination = AUDIO_DIR / audio_filename(video_title, video_id)
        logging.info("[FFMPEG] converting %s", video_id)
        try:
            subprocess.run(
                [ensure_ffmpeg(), "-y", "-v", "error", "-i", str(source), "-vn", "-ac", str(AUDIO_CHANNELS), "-ar", str(AUDIO_SAMPLE_RATE), "-c:a", "libopus", "-b:a", AUDIO_BITRATE, str(destination)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"FFmpeg conversion failed: {exc.stderr[-500:]}") from exc
        source.unlink(missing_ok=True)
        logging.info("[FFMPEG DONE] 16000 Hz / mono / 32 kbps opus")
        return destination

    def transcribe(self, audio_path: Path) -> list[dict[str, Any]]:
        """Transcribe the full audio with Whisper's timestamp-driven long-form decoder."""
        import torch

        audio = decode_audio_for_whisper(audio_path)
        inputs = self.processor(
            audio,
            sampling_rate=AUDIO_SAMPLE_RATE,
            return_tensors="pt",
            truncation=False,
            padding="longest",
            return_attention_mask=True,
        )
        input_features = inputs.input_features.to(device=self.device, dtype=self.dtype)
        attention_mask = inputs.attention_mask.to(self.device)
        with torch.inference_mode():
            result = self.model.generate(
                input_features=input_features,
                attention_mask=attention_mask,
                return_timestamps=True,
                return_segments=True,
                language="korean",
                task="transcribe",
                condition_on_prev_tokens=True,
            )

        segments: list[dict[str, Any]] = []
        for segment in result["segments"][0]:
            text = self.processor.decode(
                segment["tokens"],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            ).strip()
            if text:
                segments.append({"start": segment["start"], "end": segment["end"], "text": text})
        return segments

    @staticmethod
    def save_transcript(video_id: str, title: str, segments: Iterable[dict[str, Any]]) -> Path:
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = TRANSCRIPT_DIR / f"{video_id}.txt"
        lines = [title.strip(), ""]
        lines.extend(format_segment(segment["start"], segment["end"], segment["text"]) for segment in segments)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logging.info("[TRANSCRIPT SAVED] %s", output_path)
        return output_path

    def process(self, video_id: str, title: str = "") -> Path:
        output_path = TRANSCRIPT_DIR / f"{video_id}.txt"
        if output_path.exists():
            logging.info("[TRANSCRIPT SKIP] %s: TXT already exists", video_id)
            return output_path
        audio_path = AUDIO_DIR / audio_filename(title, video_id)
        if not audio_path.exists():
            source, downloaded_title = self.download_audio(video_id)
            title = title or downloaded_title
            audio_path = self.convert_to_opus(source, title, video_id)
        segments = self.transcribe(audio_path)
        transcript_path = self.save_transcript(video_id, title or video_id, segments)
        audio_path.unlink(missing_ok=True)
        logging.info("[AUDIO DELETED] %s", audio_path)
        return transcript_path


def load_videos(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Download YouTube audio and transcribe it with Whisper Large V3 Turbo.")
    parser.add_argument("--input", type=Path, default=DATA_DIR / "videos_current.json")
    parser.add_argument("--video-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    videos = load_videos(args.input)
    wanted_ids = set(args.video_id)
    if wanted_ids:
        videos = [video for video in videos if str(video.get("video_id")) in wanted_ids]
    if args.limit:
        videos = videos[:args.limit]
    transcriber = WhisperTranscriber()
    failures = 0
    for index, video in enumerate(videos, start=1):
        video_id = str(video.get("video_id") or "")
        if not video_id:
            continue
        logging.info("[AUDIO] %s/%s %s", index, len(videos), video_id)
        try:
            transcriber.process(video_id, str(video.get("title") or ""))
            failures = 0
        except Exception as exc:
            failures += 1
            logging.error("[TRANSCRIBE ERROR] %s: %s", video_id, exc)
            if failures >= 3:
                raise RuntimeError("Stopping after three consecutive download/transcription failures.") from exc
        if index < len(videos):
            delay = random.uniform(DOWNLOAD_SLEEP_MIN, DOWNLOAD_SLEEP_MAX)
            logging.info("[AUDIO WAIT] %.1f sec", delay)
            time.sleep(delay)


if __name__ == "__main__":
    main()
