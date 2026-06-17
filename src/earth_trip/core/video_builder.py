"""
Encodes frames to H.264 MP4 via ffmpeg subprocess pipe.
Requires ffmpeg installed and on PATH.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import numpy as np

_W, _H = 1080, 1920
_FPS = 30


def _check_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg is not installed. Run: brew install ffmpeg"
        )


def build_video(
    frames: Iterator[np.ndarray],
    output_path: str | Path,
    fps: int = _FPS,
    on_frame: callable | None = None,
) -> Path:
    """
    Write an iterable of RGB numpy arrays (shape H×W×3) to an H.264 MP4.
    on_frame(frame_index) is called after each frame.
    """
    _check_ffmpeg()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{_W}x{_H}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "pipe:0",
        "-vcodec", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert proc.stdin is not None

    i = 0
    for frame in frames:
        if frame.shape != (_H, _W, 3):
            raise ValueError(f"Expected frame shape ({_H}, {_W}, 3), got {frame.shape}")
        proc.stdin.write(frame.tobytes())
        if on_frame:
            on_frame(i)
        i += 1

    proc.stdin.close()
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"ffmpeg exited with code {ret}")

    return out
