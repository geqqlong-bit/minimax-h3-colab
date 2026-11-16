"""Optional IndexTTS2 post-processing. Media tools run as bounded subprocesses."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def scene_prompt(prompt, voice):
    """Give the H3 rewriter the same dialogue that IndexTTS2 will synthesize."""
    if voice and not isinstance(voice, dict):
        raise ValueError("聲音克隆設定格式錯誤")
    if not voice or not voice.get("enabled"):
        return prompt
    text = voice.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError("請填寫 1–2000 字的克隆台詞")
    return (prompt + "\nDialogue override: replace any other spoken dialogue in the scene with the "
            "following exact text, delivered by a single speaker within the target duration. "
            "Preserve this text and its language verbatim in the official H3 output format. "
            "Do not add other speech. Dialogue: " + text.strip())


def media_duration(path):
    probe = shutil.which("ffprobe")
    if not probe:
        raise ValueError("聲音克隆需要 ffprobe，請先安裝 ffmpeg")
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    seconds = float(json.loads(result.stdout)["format"]["duration"])
    if not 0 < seconds < 3600:
        raise ValueError("讀不到有效的媒體長度")
    return seconds


def validate_request(cfg, req, get_asset, library):
    voice = req.get("voice_clone") or {}
    if not isinstance(voice, dict):
        raise ValueError("聲音克隆設定格式錯誤")
    if not voice.get("enabled"):
        return None
    config = cfg.get("voice_clone", {})
    if not config.get("enabled"):
        raise ValueError("尚未安裝 IndexTTS2；請執行 Colab ②-b 下載聲音模型，再重跑 ③")
    if req.get("mode", "ref") not in ("ref", "frames", "text"):
        raise ValueError("聲音克隆只適用單支影片")
    if any(item.get("extend") for item in req.get("tray", [])):
        raise ValueError("聲音克隆目前不支援延伸影片，請先生成單支影片")
    text = voice.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError("請填寫 1–2000 字的克隆台詞")
    reference_id = voice.get("reference_id")
    if not isinstance(reference_id, str) or not reference_id:
        raise ValueError("請上傳自己的參考聲音")
    reference = get_asset(reference_id)
    if reference.get("kind") != "audio":
        raise ValueError("克隆聲音的參考素材必須是音訊")
    if not shutil.which("ffmpeg"):
        raise ValueError("聲音克隆需要 ffmpeg")
    duration = media_duration(Path(library) / reference["file"])
    if not 3 <= duration <= 30:
        raise ValueError("參考聲音請使用 3–30 秒的清晰單人錄音")
    if not Path(config.get("python", "")).is_file():
        raise ValueError("找不到 IndexTTS2 的獨立 Python 環境")
    if not (Path(config.get("model_dir", "")) / "config.yaml").is_file():
        raise ValueError("IndexTTS2 模型尚未下載完成")
    return {"enabled": True, "reference_id": reference_id, "text": text.strip(),
            "keep_background": voice.get("keep_background", True) is not False}


def replace_soundtrack(video, speech, output, background=None):
    """Keep video frames untouched; modestly speed speech if needed, otherwise pad silence."""
    duration, spoken = media_duration(video), media_duration(speech)
    speed = max(1.0, spoken / duration)
    if speed > 1.25:
        raise ValueError("克隆台詞長於影片太多，請縮短台詞或增加影片秒數；原片仍可下載")
    filters = f"atempo={speed:.8f},apad,atrim=duration={duration:.8f},asetpts=PTS-STARTPTS"
    command = [shutil.which("ffmpeg"), "-y", "-v", "error", "-i", str(video), "-i", str(speech)]
    if background:
        command += ["-i", str(background), "-filter_complex",
                    f"[1:a]{filters}[speech];"
                    f"[2:a]apad,atrim=duration={duration:.8f},asetpts=PTS-STARTPTS[bg];"
                    "[speech][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:latency=1[mix]",
                    "-map", "0:v:0", "-map", "[mix]"]
    else:
        command += ["-map", "0:v:0", "-map", "1:a:0", "-af", filters]
    subprocess.run(
        command + ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(duration),
                   "-movflags", "+faststart", str(output)],
        check=True, capture_output=True, timeout=180,
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("克隆配音影片未成功寫入")


def synthesize_and_replace(config, reference, text, video, destination, runner, keep_background=True):
    """The isolated process exits before returning, releasing all IndexTTS2 GPU memory."""
    with tempfile.TemporaryDirectory(prefix="h3voice-", dir=destination.parent) as directory:
        work = Path(directory)
        ref = work / "reference.wav"
        subprocess.run(
            [shutil.which("ffmpeg"), "-y", "-v", "error", "-i", str(reference),
             "-vn", "-ac", "1", "-ar", "24000", str(ref)],
            check=True, capture_output=True, timeout=60,
        )
        text_file = work / "speech.txt"
        text_file.write_text(text, encoding="utf-8")
        speech = work / "speech.wav"
        log = work / "inference.log"
        # Upstream can log prompts, so keep inference output local and do not return it to the browser.
        with log.open("wb") as stream:
            result = subprocess.run(
                [config["python"], str(runner), "--repo-dir", config["repo_dir"],
                 "--model-dir", config["model_dir"], "--reference", str(ref),
                 "--text-file", str(text_file), "--output", str(speech)],
                stdout=stream, stderr=subprocess.STDOUT, timeout=900,
            )
        if result.returncode:
            raise RuntimeError("IndexTTS2 配音失敗；請確認模型、獨立環境及 GPU 可用")
        if not speech.is_file():
            raise RuntimeError("IndexTTS2 沒有輸出配音檔案")
        background = None
        if keep_background:
            original_audio = work / "original.wav"
            subprocess.run(
                [shutil.which("ffmpeg"), "-y", "-v", "error", "-i", str(video),
                 "-vn", "-ac", "2", "-ar", "44100", str(original_audio)],
                check=True, capture_output=True, timeout=60,
            )
            with log.open("ab") as stream:
                separated = subprocess.run(
                    [config["python"], "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs",
                     "--device", "cpu", "-o", str(work / "stems"), str(original_audio)],
                    # Official Demucs checkpoints serialize model classes; scope this legacy-load
                    # compatibility flag to the trusted model subprocess, not the TTS/Comfy runtimes.
                    env=dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1"),
                    stdout=stream, stderr=subprocess.STDOUT, timeout=900,
                )
            background = work / "stems" / "htdemucs" / "original" / "no_vocals.wav"
            if separated.returncode or not background.is_file():
                raise RuntimeError("背景音分離失敗，沒有替換音軌；原片仍可下載")
        result_video = work / "dubbed.mp4"
        replace_soundtrack(video, speech, result_video, background)
        result_video.replace(destination)
