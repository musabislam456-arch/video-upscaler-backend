#!/usr/bin/env python3
"""
Classical CPU-Only Video Upscaling and Enhancement Engine (V2)
----------------------------------------------------------------
Zero-AI classical signal-processing video upscaler using Python, FFmpeg,
OpenCV and NumPy. The web backend invokes this file as a worker process.

Supported CLI examples:
  python ai_studio_code.py -i input.mp4 -o output.mp4 --scale 2 --quality balanced
  python ai_studio_code.py -i input.mp4 -o output.mp4 --height 1080 --quality quality
  python ai_studio_code.py -i input.mp4 -o output.mp4 --height 2160 --quality max

No AI / ML / neural network / GPU dependency is used.
"""

import argparse
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np


class UpscalerError(Exception):
    pass


class DependencyError(UpscalerError):
    pass


class ProbeError(UpscalerError):
    pass


class AnalysisError(UpscalerError):
    pass


class EncodingError(UpscalerError):
    pass


class ValidationError(UpscalerError):
    pass


logger = logging.getLogger("ClassicalUpscaler")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def low_memory_mode_enabled() -> bool:
    return os.getenv("UPSCALE_LOW_MEMORY_MODE", "false").strip().lower() == "true"


@dataclass
class VideoMetadata:
    filepath: Path
    width: int
    height: int
    fps: float
    r_frame_rate: str
    avg_frame_rate: str
    duration: float
    nb_frames: int
    codec: str
    pix_fmt: str
    bit_depth: int
    color_space: Optional[str]
    color_transfer: Optional[str]
    color_primaries: Optional[str]
    color_range: Optional[str]
    is_vfr: bool
    is_interlaced: bool
    field_order: str
    audio_stream_count: int
    subtitle_stream_count: int
    file_size_bytes: int


@dataclass
class FrameMetrics:
    timestamp: float
    laplacian_var: float
    sobel_energy: float
    compound_sharpness: float
    flat_noise_var: float
    blockiness_score: float
    dynamic_range: float
    core_dynamic_range: float
    mean_luma: float
    p5_luma: float
    p50_luma: float
    p95_luma: float
    shadow_clip_ratio: float
    highlight_clip_ratio: float
    mean_saturation: float
    mean_b: float
    mean_g: float
    mean_r: float
    motion_sad: float
    is_scene_cut: bool


@dataclass
class AggregatedProfile:
    avg_sharpness: float
    avg_noise: float
    avg_blockiness: float
    avg_contrast: float
    avg_motion: float
    avg_luma: float
    avg_shadow_clip: float
    avg_highlight_clip: float
    avg_saturation: float
    color_cast_rb: float
    color_cast_g: float
    color_cast_detected: bool
    scene_cuts_count: int
    category: str
    exposure_category: str
    recommended_scaler: str
    needs_deband: bool


@dataclass
class FrameFilterSettings:
    timestamp: float
    cas_strength: float
    hqdn_spatial: float
    hqdn_tmp: float
    eq_contrast: float
    eq_brightness: float
    eq_gamma: float
    eq_saturation: float


@dataclass
class JobResult:
    success: bool
    input_path: str
    output_path: str
    metadata: Dict[str, Any]
    analysis_summary: Dict[str, Any]
    filtergraph: str
    execution_time_sec: float
    output_size_mb: float
    effective_fps: float
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


def escape_filter_path(p: Path) -> str:
    return p.resolve().as_posix().replace(":", r"\:")


def check_environment(verbose: bool = False) -> Tuple[bool, Dict[str, Any]]:
    status: Dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
        "opencv_version": cv2.__version__,
        "ffmpeg_installed": False,
        "ffprobe_installed": False,
        "ffmpeg_version": "unknown",
        "filters": {},
    }
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    status["ffmpeg_installed"] = ffmpeg_bin is not None
    status["ffprobe_installed"] = ffprobe_bin is not None
    if not ffmpeg_bin or not ffprobe_bin:
        return False, status

    try:
        version = subprocess.run([ffmpeg_bin, "-version"], capture_output=True, text=True, check=True)
        first_line = version.stdout.splitlines()[0] if version.stdout else ""
        match = re.search(r"ffmpeg version ([^\s]+)", first_line)
        if match:
            status["ffmpeg_version"] = match.group(1)
    except Exception as exc:
        status["ffmpeg_error"] = str(exc)
        return False, status

    required_filters = ["scale", "hqdn3d", "cas", "deband", "bwdif", "sendcmd", "eq", "format", "colorbalance"]
    try:
        filters = subprocess.run([ffmpeg_bin, "-filters"], capture_output=True, text=True, check=True).stdout
        for name in required_filters:
            status["filters"][name] = re.search(rf"\s{name}\s", filters) is not None
    except Exception as exc:
        status["filters_error"] = str(exc)
        return False, status

    ready = status["ffmpeg_installed"] and status["ffprobe_installed"] and all(status["filters"].values())
    if verbose:
        logger.info(
            "Environment: Python %s, NumPy %s, OpenCV %s, FFmpeg %s",
            status["python_version"],
            status["numpy_version"],
            status["opencv_version"],
            status["ffmpeg_version"],
        )
        for name, ok in status["filters"].items():
            logger.info("Filter %-14s %s", name, "[OK]" if ok else "[MISSING]")
    return ready, status


class VideoProbe:
    @staticmethod
    def probe(input_path: Path) -> VideoMetadata:
        if not input_path.exists():
            raise ProbeError(f"Input file not found: {input_path}")
        if input_path.stat().st_size == 0:
            raise ProbeError("Input file is 0 bytes.")

        cmd = [
            "ffprobe", "-v", "error",
            "-show_format", "-show_streams",
            "-of", "json", str(input_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
        except subprocess.CalledProcessError as exc:
            raise ProbeError(exc.stderr.strip() or "ffprobe failed.") from exc
        except json.JSONDecodeError as exc:
            raise ProbeError("Unable to parse ffprobe JSON.") from exc

        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        subtitles = [s for s in streams if s.get("codec_type") == "subtitle"]
        if not video:
            raise ProbeError("No video stream found.")

        def parse_rate(value: str) -> float:
            try:
                n, d = value.split("/", 1)
                return float(n) / float(d) if float(d) else 25.0
            except Exception:
                return 25.0

        r_rate = str(video.get("r_frame_rate", "25/1"))
        avg_rate = str(video.get("avg_frame_rate", "25/1"))
        r_fps = parse_rate(r_rate)
        avg_fps = parse_rate(avg_rate)
        is_vfr = abs(r_fps - avg_fps) > 0.05 and avg_fps > 0
        fps = avg_fps if is_vfr else r_fps

        fmt = data.get("format", {})
        duration = float(video.get("duration") or fmt.get("duration") or 1.0)
        nb_frames = int(video.get("nb_frames") or 0)
        if nb_frames <= 0:
            nb_frames = max(1, int(duration * fps))

        pix_fmt = str(video.get("pix_fmt", "unknown"))
        bits_raw = video.get("bits_per_raw_sample")
        bit_depth = int(bits_raw) if bits_raw and str(bits_raw).isdigit() else (10 if "10" in pix_fmt else 12 if "12" in pix_fmt else 8)
        field_order = str(video.get("field_order", "progressive"))
        is_interlaced = field_order in {"tt", "bb", "tb", "bt"}

        return VideoMetadata(
            filepath=input_path,
            width=int(video.get("width", 0)),
            height=int(video.get("height", 0)),
            fps=max(0.1, fps),
            r_frame_rate=r_rate,
            avg_frame_rate=avg_rate,
            duration=max(0.01, duration),
            nb_frames=nb_frames,
            codec=str(video.get("codec_name", "unknown")),
            pix_fmt=pix_fmt,
            bit_depth=bit_depth,
            color_space=video.get("color_space"),
            color_transfer=video.get("color_transfer"),
            color_primaries=video.get("color_primaries"),
            color_range=video.get("color_range"),
            is_vfr=is_vfr,
            is_interlaced=is_interlaced,
            field_order=field_order,
            audio_stream_count=len(audio),
            subtitle_stream_count=len(subtitles),
            file_size_bytes=input_path.stat().st_size,
        )


class VideoAnalyzer:
    SHADOW_CLIP_LUMA = 16
    HIGHLIGHT_CLIP_LUMA = 240

    def __init__(self, meta: VideoMetadata, quality_mode: str):
        self.meta = meta
        if quality_mode == "fast":
            self.max_width, self.sample_fps = 320, 1.0
        elif quality_mode == "balanced":
            self.max_width, self.sample_fps = 480, 2.0
        elif quality_mode == "quality":
            self.max_width, self.sample_fps = 640, 3.0
        else:
            self.max_width, self.sample_fps = 640, 4.0

        self.sample_fps = min(self.sample_fps, self.meta.fps)
        ratio = min(1.0, self.max_width / max(1, self.meta.width))
        self.analysis_w = max(16, int(self.meta.width * ratio) // 2 * 2)
        self.analysis_h = max(16, int(self.meta.height * ratio) // 2 * 2)

    def analyze(self) -> List[FrameMetrics]:
        logger.info(
            "Analyzing stream: %.1f FPS at %dx%d",
            self.sample_fps, self.analysis_w, self.analysis_h
        )
        cmd = [
            "ffmpeg", "-v", "error", "-i", str(self.meta.filepath),
            "-vf", f"scale={self.analysis_w}:{self.analysis_h}:flags=bilinear,fps={self.sample_fps}",
            "-pix_fmt", "bgr24", "-f", "image2pipe", "-vcodec", "rawvideo", "-"
        ]
        frame_bytes = self.analysis_w * self.analysis_h * 3
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes * 2
        )
        assert proc.stdout is not None
        results: List[FrameMetrics] = []
        previous_gray: Optional[np.ndarray] = None
        previous_hist: Optional[np.ndarray] = None
        running_motion = 0.0
        have_baseline = False
        index = 0

        while True:
            raw = proc.stdout.read(frame_bytes)
            if not raw or len(raw) != frame_bytes:
                break

            bgr = np.frombuffer(raw, dtype=np.uint8).reshape((self.analysis_h, self.analysis_w, 3))
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            sx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            grad = np.sqrt(sx * sx + sy * sy)
            sobel_energy = float(np.mean(grad * grad))
            mean_luma = float(np.mean(gray))
            sharpness = math.sqrt(max(0.0, lap) * (sobel_energy + 1e-4)) / max(10.0, mean_luma)

            flat_threshold = float(np.percentile(grad, 35))
            flat_mask = grad < flat_threshold
            residual = cv2.absdiff(gray, cv2.medianBlur(gray, 3))
            flat_noise = float(np.var(residual[flat_mask])) if np.any(flat_mask) else float(np.var(residual))

            h, w = gray.shape
            if h >= 16 and w >= 16:
                boundary_cols = np.arange(8, w - 1, 8)
                interior_cols = np.arange(4, w - 1, 8)
                diff_b = float(np.mean(np.abs(
                    gray[:, boundary_cols].astype(np.float32) -
                    gray[:, boundary_cols - 1].astype(np.float32)
                ))) if len(boundary_cols) else 0.0
                diff_i = float(np.mean(np.abs(
                    gray[:, interior_cols].astype(np.float32) -
                    gray[:, interior_cols - 1].astype(np.float32)
                ))) if len(interior_cols) else 1.0
                blockiness = diff_b / (diff_i + 1e-5)
            else:
                blockiness = 1.0

            p1, p5, p50, p95, p99 = [float(v) for v in np.percentile(gray, [1, 5, 50, 95, 99])]
            shadow_clip = float(np.mean(gray < self.SHADOW_CLIP_LUMA))
            highlight_clip = float(np.mean(gray > self.HIGHLIGHT_CLIP_LUMA))
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            saturation = float(np.mean(hsv[:, :, 1])) / 255.0
            mean_b, mean_g, mean_r = [float(v) for v in cv2.mean(bgr)[:3]]

            motion = 0.0
            cut = False
            curr_hist = cv2.normalize(
                cv2.calcHist([gray], [0], None, [32], [0, 256]),
                None
            ).flatten()

            if previous_gray is not None and previous_hist is not None:
                motion = float(np.mean(np.abs(
                    gray.astype(np.float32) - previous_gray.astype(np.float32)
                )))
                corr = float(cv2.compareHist(curr_hist, previous_hist, cv2.HISTCMP_CORREL))
                hard = max(28.0, running_motion * 3.2) if have_baseline else 28.0
                soft = max(16.0, running_motion * 1.8) if have_baseline else 16.0
                cut = motion > hard or (motion > soft and corr < 0.65)

            if cut or not have_baseline:
                running_motion = motion
                have_baseline = True
            else:
                running_motion = 0.08 * motion + 0.92 * running_motion

            results.append(FrameMetrics(
                timestamp=index / max(0.01, self.sample_fps),
                laplacian_var=lap,
                sobel_energy=sobel_energy,
                compound_sharpness=sharpness,
                flat_noise_var=flat_noise,
                blockiness_score=float(blockiness),
                dynamic_range=p99 - p1,
                core_dynamic_range=p95 - p5,
                mean_luma=mean_luma,
                p5_luma=p5,
                p50_luma=p50,
                p95_luma=p95,
                shadow_clip_ratio=shadow_clip,
                highlight_clip_ratio=highlight_clip,
                mean_saturation=saturation,
                mean_b=mean_b,
                mean_g=mean_g,
                mean_r=mean_r,
                motion_sad=motion,
                is_scene_cut=cut,
            ))
            previous_gray = gray.copy()
            previous_hist = curr_hist.copy()
            index += 1

        proc.wait()
        if not results:
            raise AnalysisError("Zero frames analyzed. Video may be corrupt or unreadable.")
        return results


class ProfilePlanner:
    @staticmethod
    def evaluate_global(metrics: List[FrameMetrics]) -> AggregatedProfile:
        avg_sharp = float(np.mean([m.compound_sharpness for m in metrics]))
        avg_noise = float(np.mean([m.flat_noise_var for m in metrics]))
        avg_block = float(np.mean([m.blockiness_score for m in metrics]))
        avg_contrast = float(np.mean([m.dynamic_range for m in metrics]))
        avg_motion = float(np.mean([m.motion_sad for m in metrics]))
        avg_luma = float(np.mean([m.mean_luma for m in metrics]))
        avg_shadow = float(np.mean([m.shadow_clip_ratio for m in metrics]))
        avg_highlight = float(np.mean([m.highlight_clip_ratio for m in metrics]))
        avg_sat = float(np.mean([m.mean_saturation for m in metrics]))
        avg_r = float(np.mean([m.mean_r for m in metrics]))
        avg_g = float(np.mean([m.mean_g for m in metrics]))
        avg_b = float(np.mean([m.mean_b for m in metrics]))

        rb = avg_r - avg_b
        g_cast = avg_g - ((avg_r + avg_b) / 2.0)
        color_cast = abs(rb) > 8.0 or abs(g_cast) > 6.0

        if avg_noise > 6.0:
            category = "VERY_NOISY"
        elif avg_noise > 3.0:
            category = "NOISY"
        elif avg_block > 1.25:
            category = "COMPRESSED"
        elif avg_sharp < 15.0:
            category = "SOFT_BLURRY"
        elif avg_sharp > 60.0:
            category = "SHARP_CLEAN"
        else:
            category = "BALANCED_CLEAN"

        if avg_luma < 55.0 or avg_shadow > 0.18:
            exposure = "VERY_DARK"
        elif avg_luma < 95.0 or avg_shadow > 0.08:
            exposure = "DARK"
        elif avg_luma > 185.0 and avg_highlight > 0.05:
            exposure = "BRIGHT_CLIPPED"
        elif avg_contrast < 90.0:
            exposure = "FLAT_LOW_CONTRAST"
        else:
            exposure = "NORMAL"

        if category in {"SHARP_CLEAN", "BALANCED_CLEAN"} and avg_noise < 2.0 and avg_block < 1.15:
            scaler = "lanczos"
        else:
            scaler = "spline"

        needs_deband = avg_block > 1.18 or avg_contrast < 120.0 or exposure in {"DARK", "VERY_DARK"}

        return AggregatedProfile(
            avg_sharpness=avg_sharp,
            avg_noise=avg_noise,
            avg_blockiness=avg_block,
            avg_contrast=avg_contrast,
            avg_motion=avg_motion,
            avg_luma=avg_luma,
            avg_shadow_clip=avg_shadow,
            avg_highlight_clip=avg_highlight,
            avg_saturation=avg_sat,
            color_cast_rb=rb,
            color_cast_g=g_cast,
            color_cast_detected=color_cast,
            scene_cuts_count=sum(1 for m in metrics if m.is_scene_cut),
            category=category,
            exposure_category=exposure,
            recommended_scaler=scaler,
            needs_deband=needs_deband,
        )

    @staticmethod
    def generate_timeline_settings(
        metrics: List[FrameMetrics],
        quality_mode: str,
        enable_exposure: bool = True,
    ) -> List[FrameFilterSettings]:
        sharp = np.array([m.compound_sharpness for m in metrics], dtype=np.float64)
        p10, p90 = [float(v) for v in np.percentile(sharp, [10, 90])]
        span = max(1e-3, p90 - p10)
        raw: List[FrameFilterSettings] = []

        for m in metrics:
            norm = float(np.clip((m.compound_sharpness - p10) / span, 0.0, 1.0))
            cas = 0.56 - norm * (0.56 - 0.12)
            if m.flat_noise_var > 1.8:
                cas *= max(0.35, 1.0 - (m.flat_noise_var - 1.8) * 0.12)
            if m.blockiness_score > 1.2:
                cas *= 0.80
            if m.motion_sad > 8.0:
                cas *= 0.85
            cas = float(np.clip(cas, 0.05, 0.58))

            if m.flat_noise_var < 1.2:
                hqdn_s = 0.0
            else:
                hqdn_s = min(6.0, (m.flat_noise_var - 1.2) * 1.1)
            if m.blockiness_score > 1.25:
                hqdn_s = min(6.5, hqdn_s + 0.6)

            if m.motion_sad < 2.0:
                hqdn_t = hqdn_s * 1.25
            elif m.motion_sad < 6.0:
                hqdn_t = hqdn_s * 0.60
            else:
                hqdn_t = hqdn_s * 0.15

            gamma = 1.0
            brightness = 0.0
            contrast = 1.0
            saturation = 1.0
            if enable_exposure:
                if m.mean_luma < 60.0:
                    gamma = 1.0 + min(0.55, (60.0 - m.mean_luma) / 60.0 * 0.55)
                elif m.mean_luma < 100.0:
                    gamma = 1.0 + (100.0 - m.mean_luma) / 100.0 * 0.30
                elif m.mean_luma > 175.0 and m.highlight_clip_ratio > 0.04:
                    gamma = 1.0 - min(0.15, (m.mean_luma - 175.0) / 175.0 * 0.15)
                if m.shadow_clip_ratio > 0.10:
                    gamma += min(0.25, (m.shadow_clip_ratio - 0.10) * 1.5)
                gamma = float(np.clip(gamma, 0.85, 1.65))

                if m.mean_luma < 90.0:
                    brightness = min(0.05, (90.0 - m.mean_luma) / 90.0 * 0.05)
                elif m.mean_luma > 190.0:
                    brightness = -min(0.04, (m.mean_luma - 190.0) / 65.0 * 0.04)

                if m.core_dynamic_range < 100.0:
                    contrast = 1.0 + min(0.22, (100.0 - m.core_dynamic_range) / 100.0 * 0.22)
                if m.highlight_clip_ratio > 0.06:
                    contrast *= max(0.88, 1.0 - (m.highlight_clip_ratio - 0.06) * 1.2)
                contrast = float(np.clip(contrast, 0.85, 1.30))

                if m.mean_saturation < 0.28 and m.flat_noise_var < 3.5:
                    saturation = 1.0 + min(0.18, (0.28 - m.mean_saturation) / 0.28 * 0.18)
                saturation = float(np.clip(saturation, 0.9, 1.25))

            raw.append(FrameFilterSettings(
                timestamp=m.timestamp,
                cas_strength=cas,
                hqdn_spatial=hqdn_s,
                hqdn_tmp=hqdn_t,
                eq_contrast=contrast,
                eq_brightness=brightness,
                eq_gamma=gamma,
                eq_saturation=saturation,
            ))

        alpha = 0.22
        limits = {
            "cas_strength": (0.06, 0.010),
            "hqdn_spatial": (1.20, 0.150),
            "hqdn_tmp": (1.20, 0.150),
            "eq_contrast": (0.05, 0.008),
            "eq_brightness": (0.02, 0.004),
            "eq_gamma": (0.08, 0.012),
            "eq_saturation": (0.05, 0.008),
        }

        def stabilize(name: str, current: float, previous: float) -> float:
            max_delta, deadband = limits[name]
            value = alpha * current + (1.0 - alpha) * previous
            delta = value - previous
            if abs(delta) > max_delta:
                value = previous + math.copysign(max_delta, delta)
            return previous if abs(value - previous) < deadband else value

        out: List[FrameFilterSettings] = []
        for i, current in enumerate(raw):
            if i == 0 or metrics[i].is_scene_cut:
                out.append(current)
                continue
            previous = out[-1]
            out.append(FrameFilterSettings(
                timestamp=current.timestamp,
                cas_strength=stabilize("cas_strength", current.cas_strength, previous.cas_strength),
                hqdn_spatial=stabilize("hqdn_spatial", current.hqdn_spatial, previous.hqdn_spatial),
                hqdn_tmp=stabilize("hqdn_tmp", current.hqdn_tmp, previous.hqdn_tmp),
                eq_contrast=stabilize("eq_contrast", current.eq_contrast, previous.eq_contrast),
                eq_brightness=stabilize("eq_brightness", current.eq_brightness, previous.eq_brightness),
                eq_gamma=stabilize("eq_gamma", current.eq_gamma, previous.eq_gamma),
                eq_saturation=stabilize("eq_saturation", current.eq_saturation, previous.eq_saturation),
            ))
        return out

    @staticmethod
    def write_sendcmd_script(settings: List[FrameFilterSettings], out_path: Path) -> None:
        with out_path.open("w", encoding="utf-8") as handle:
            for item in settings:
                t = max(0.0, item.timestamp)
                handle.write(f"{t:.3f} hqdn3d luma_spatial {item.hqdn_spatial:.3f};\n")
                handle.write(f"{t:.3f} hqdn3d chroma_spatial {item.hqdn_spatial * 0.75:.3f};\n")
                handle.write(f"{t:.3f} hqdn3d luma_tmp {item.hqdn_tmp:.3f};\n")
                handle.write(f"{t:.3f} hqdn3d chroma_tmp {item.hqdn_tmp * 0.75:.3f};\n")
                handle.write(f"{t:.3f} cas strength {item.cas_strength:.3f};\n")
                handle.write(f"{t:.3f} eq contrast {item.eq_contrast:.3f};\n")
                handle.write(f"{t:.3f} eq brightness {item.eq_brightness:.3f};\n")
                handle.write(f"{t:.3f} eq gamma {item.eq_gamma:.3f};\n")
                handle.write(f"{t:.3f} eq saturation {item.eq_saturation:.3f};\n")


class FilterGraphBuilder:
    @staticmethod
    def build(
        meta: VideoMetadata,
        cmd_file: Path,
        target_w: int,
        target_h: int,
        scaler: str,
        quality_mode: str,
        profile: AggregatedProfile,
        deinterlace_request: bool,
        multi_stage_4x: bool = False,
        enable_color_balance: bool = True,
        low_memory_mode: bool = False,
    ) -> str:
        filters: List[str] = []
        if meta.is_interlaced or deinterlace_request:
            filters.append("bwdif=mode=0:parity=-1:deint=1")

        if quality_mode in {"quality", "max"} and not low_memory_mode:
            filters.append("format=yuv420p10le")

        # On very small RAM services, every low-memory quality mode uses a
        # deliberately simple filter path. This prevents the adaptive
        # sendcmd/hqdn3d/deband pipeline from competing with a 1440p/4K encoder
        # for the same ~512 MB container memory.
        simple_low_memory = low_memory_mode

        if not simple_low_memory:
            filters.append(f"sendcmd=f='{escape_filter_path(cmd_file)}'")
            filters.append("hqdn3d=0:0:0:0")

            if profile.needs_deband or quality_mode == "max":
                threshold = 0.03 + (0.015 if profile.exposure_category in {"DARK", "VERY_DARK"} else 0.0)
                filters.append(
                    f"deband=1thr={threshold:.3f}:2thr={threshold:.3f}:3thr={threshold:.3f}:range=16:blur=1"
                )

        if multi_stage_4x and quality_mode == "max":
            mid_w = max(2, (meta.width * 2) // 2 * 2)
            mid_h = max(2, (meta.height * 2) // 2 * 2)
            filters.append(f"scale={mid_w}:{mid_h}:flags={scaler}+accurate_rnd")
            filters.append("cas=strength=0.20:planes=1")
            filters.append(f"scale={target_w}:{target_h}:flags={scaler}+accurate_rnd")
        else:
            filters.append(f"scale={target_w}:{target_h}:flags={scaler}+accurate_rnd")

        if not simple_low_memory:
            filters.append("cas=strength=0:planes=1")
        else:
            # Keep a very small classical edge enhancement after scaling.
            filters.append("cas=strength=0.08:planes=1")

        if (not simple_low_memory) and enable_color_balance and profile.color_cast_detected:
            strength = 0.5
            rb = float(np.clip((-profile.color_cast_rb / 255.0) * 2.0 * strength, -0.15, 0.15))
            gg = float(np.clip((-profile.color_cast_g / 255.0) * 2.0 * strength, -0.12, 0.12))
            filters.append(
                "colorbalance="
                f"rs={rb * 0.35:.3f}:gs={gg * 0.35:.3f}:bs={-rb * 0.35:.3f}:"
                f"rm={rb * 0.60:.3f}:gm={gg * 0.60:.3f}:bm={-rb * 0.60:.3f}:"
                f"rh={rb * 0.30:.3f}:gh={gg * 0.30:.3f}:bh={-rb * 0.30:.3f}"
            )

        if not simple_low_memory:
            filters.append("eq=contrast=1.0:brightness=0.0:gamma=1.0:saturation=1.0")
        filters.append(f"format={'yuv420p10le' if quality_mode == 'max' and not low_memory_mode else 'yuv420p'}")
        return ",".join(filters)


def build_color_args(meta: VideoMetadata) -> List[str]:
    args: List[str] = []
    if meta.color_primaries and meta.color_primaries != "unknown":
        args += ["-color_primaries", meta.color_primaries]
    else:
        args += ["-color_primaries", "bt709" if meta.width >= 1280 or meta.height >= 720 else "smpte170m"]

    if meta.color_transfer and meta.color_transfer != "unknown":
        args += ["-color_trc", meta.color_transfer]
    else:
        args += ["-color_trc", "bt709" if meta.width >= 1280 or meta.height >= 720 else "smpte170m"]

    if meta.color_space and meta.color_space != "unknown":
        args += ["-colorspace", meta.color_space]
    else:
        args += ["-colorspace", "bt709" if meta.width >= 1280 or meta.height >= 720 else "smpte170m"]

    if meta.color_range and meta.color_range != "unknown":
        args += ["-color_range", meta.color_range]
    return args


class OutputValidator:
    @staticmethod
    def validate(output_path: Path, expected_w: int, expected_h: int, source: VideoMetadata) -> None:
        if not output_path.exists():
            raise ValidationError(f"Output was not created: {output_path}")
        if output_path.stat().st_size == 0:
            raise ValidationError("Output file is empty.")

        result = VideoProbe.probe(output_path)
        if result.width != expected_w or result.height != expected_h:
            raise ValidationError(
                f"Output dimensions {result.width}x{result.height} do not match {expected_w}x{expected_h}."
            )
        if abs(result.duration - source.duration) > max(2.0, source.duration * 0.08):
            raise ValidationError(
                f"Output duration {result.duration:.2f}s deviates from source {source.duration:.2f}s."
            )
        if source.audio_stream_count > 0 and result.audio_stream_count == 0:
            raise ValidationError("Source audio stream is missing from output.")

        sanity = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(output_path), "-frames:v", "2", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30
        )
        if sanity.returncode != 0:
            raise ValidationError(f"Output decode sanity check failed: {sanity.stderr.strip()}")


class VideoUpscalerEngine:
    def __init__(
        self,
        input_path: str,
        output_path: str,
        scale_factor: Optional[float] = 2.0,
        target_width: Optional[int] = None,
        target_height: Optional[int] = None,
        quality_mode: str = "quality",
        scaler: str = "auto",
        codec: str = "h264",
        crf: int = 18,
        deinterlace: bool = False,
        auto_exposure: bool = True,
        auto_color_balance: bool = True,
    ):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.scale_factor = scale_factor
        self.target_width = target_width
        self.target_height = target_height
        self.quality_mode = quality_mode
        self.scaler = scaler
        self.codec = codec
        self.crf = int(np.clip(crf, 0, 51))
        self.deinterlace = deinterlace
        self.auto_exposure = auto_exposure
        self.auto_color_balance = auto_color_balance
        self.low_memory_mode = low_memory_mode_enabled()

        ready, details = check_environment()
        if not ready:
            missing = [k for k, ok in details.get("filters", {}).items() if not ok]
            suffix = f" Missing filters: {', '.join(missing)}." if missing else ""
            raise DependencyError("FFmpeg/ffprobe/OpenCV environment is not ready." + suffix)

        self.meta = VideoProbe.probe(self.input_path)
        self._compute_output_dimensions()

    def _compute_output_dimensions(self) -> None:
        src_w, src_h = self.meta.width, self.meta.height
        if self.target_width and self.target_height:
            out_w, out_h = self.target_width, self.target_height
        elif self.target_width:
            out_w = self.target_width
            out_h = int(src_h * out_w / max(1, src_w))
        elif self.target_height:
            out_h = self.target_height
            out_w = int(src_w * out_h / max(1, src_h))
        else:
            factor = self.scale_factor or 2.0
            out_w, out_h = int(src_w * factor), int(src_h * factor)

        self.out_w = max(2, out_w - (out_w % 2))
        self.out_h = max(2, out_h - (out_h % 2))

    def run(
        self,
        progress_callback: Optional[Callable[[float, Dict[str, Any]], None]] = None,
    ) -> JobResult:
        started = time.time()
        warnings: List[str] = []
        report = lambda p, info=None: progress_callback(float(p), info or {}) if progress_callback else None

        logger.info(
            "Target: %dx%d -> %dx%d (%s, low-memory=%s)",
            self.meta.width, self.meta.height, self.out_w, self.out_h,
            self.quality_mode.upper(), self.low_memory_mode
        )
        report(5.0, {"phase": "probe", "status": "Probing source video"})

        with tempfile.TemporaryDirectory(prefix="classical_upscale_") as temp:
            temp_dir = Path(temp)
            command_file = temp_dir / f"commands_{uuid.uuid4().hex[:8]}.txt"

            report(10.0, {"phase": "analysis", "status": "Analyzing source"})
            metrics = VideoAnalyzer(self.meta, self.quality_mode).analyze()
            profile = ProfilePlanner.evaluate_global(metrics)
            report(28.0, {"phase": "planning", "status": "Building adaptive processing profile"})

            active_scaler = profile.recommended_scaler if self.scaler == "auto" else self.scaler
            settings = ProfilePlanner.generate_timeline_settings(
                metrics, self.quality_mode, enable_exposure=self.auto_exposure
            )
            ProfilePlanner.write_sendcmd_script(settings, command_file)

            is_4x = self.out_w >= self.meta.width * 3.8
            filtergraph = FilterGraphBuilder.build(
                meta=self.meta,
                cmd_file=command_file,
                target_w=self.out_w,
                target_h=self.out_h,
                scaler=active_scaler,
                quality_mode=self.quality_mode,
                profile=profile,
                deinterlace_request=self.deinterlace,
                multi_stage_4x=is_4x,
                enable_color_balance=self.auto_color_balance,
                low_memory_mode=self.low_memory_mode,
            )

            vcodec = "libx265" if self.codec in {"hevc", "h265"} else "libx264"
            if self.low_memory_mode:
                preset = {"fast": "ultrafast", "balanced": "veryfast", "quality": "faster", "max": "fast"}.get(
                    self.quality_mode, "veryfast"
                )
            else:
                preset = {"fast": "faster", "balanced": "medium", "quality": "slow", "max": "veryslow"}.get(
                    self.quality_mode, "medium"
                )

            cmd = [
                "ffmpeg", "-y",
                "-progress", "pipe:1",
                "-nostats", "-loglevel", "warning",
                "-threads", "1",
                "-filter_threads", "1",
                "-filter_complex_threads", "1",
                "-i", str(self.meta.filepath),
                "-filter_complex", f"[0:v]{filtergraph}[vout]",
                "-map", "[vout]",
                "-c:v", vcodec,
                "-crf", str(self.crf),
                "-preset", preset,
            ]
            if self.low_memory_mode and vcodec == "libx264":
                # Reduce x264's frame/lookahead buffering on 512 MB-class containers.
                cmd += ["-tune", "zerolatency", "-x264-params", "threads=1:rc-lookahead=0:ref=1:bframes=0"]
            cmd += build_color_args(self.meta)

            if self.meta.audio_stream_count:
                cmd += ["-map", "0:a?", "-c:a", "copy"]
            else:
                warnings.append("Input contains no audio streams.")

            if self.meta.subtitle_stream_count and self.output_path.suffix.lower() == ".mkv":
                cmd += ["-map", "0:s?", "-c:s", "copy"]

            cmd += ["-map_metadata", "0"]
            if self.output_path.suffix.lower() in {".mp4", ".mov"}:
                cmd += ["-movflags", "+faststart"]
            cmd.append(str(self.output_path))

            report(35.0, {"phase": "encoding", "status": "Starting FFmpeg encoding"})
            logger.info("Encoding with %s / %s preset", vcodec, preset)

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            assert proc.stderr is not None

            progress_data: Dict[str, str] = {}
            for line in proc.stdout:
                line = line.strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                progress_data[key] = value
                if key != "progress":
                    continue

                try:
                    out_time_us = int(progress_data.get("out_time_us", "0"))
                except ValueError:
                    out_time_us = 0
                current = out_time_us / 1_000_000.0
                pct = min(100.0, current / max(self.meta.duration, 0.001) * 100.0)
                fps_value = float(progress_data.get("fps", "0") or 0.0)
                speed = progress_data.get("speed", "0x")
                eta = max(0.0, self.meta.duration - current) / max(
                    0.01, fps_value / max(0.1, self.meta.fps)
                )
                report(35.0 + pct * 0.64, {
                    "phase": "encoding",
                    "status": f"Encoding · {speed}",
                    "fps": fps_value,
                    "speed": speed,
                    "time_sec": current,
                    "eta_sec": eta,
                })

            stderr_output = proc.stderr.read()
            proc.wait()

            if proc.returncode != 0:
                audio_issue = "Could not write header" in stderr_output or "audio" in stderr_output.lower()
                if audio_issue and self.meta.audio_stream_count:
                    warnings.append("Audio stream was re-encoded to AAC because direct stream copy failed.")
                    retry = []
                    replaced = False
                    for i, arg in enumerate(cmd):
                        if arg == "-c:a" and i + 1 < len(cmd) and cmd[i + 1] == "copy":
                            retry = cmd.copy()
                            retry[i + 1] = "aac"
                            retry[i + 1:i + 1] = ["-b:a", "192k"]
                            replaced = True
                            break
                    if not replaced:
                        raise EncodingError(stderr_output.strip() or "FFmpeg encoding failed.")
                    result = subprocess.run(retry, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise EncodingError(result.stderr.strip() or "FFmpeg retry failed.")
                else:
                    raise EncodingError(stderr_output.strip() or f"FFmpeg exited with code {proc.returncode}")

        report(99.0, {"phase": "validation", "status": "Validating output"})
        OutputValidator.validate(self.output_path, self.out_w, self.out_h, self.meta)

        elapsed = max(0.01, time.time() - started)
        output_mb = self.output_path.stat().st_size / (1024 * 1024)
        effective_fps = self.meta.duration * self.meta.fps / elapsed
        report(100.0, {"phase": "complete", "status": "Completed"})

        return JobResult(
            success=True,
            input_path=str(self.input_path),
            output_path=str(self.output_path),
            metadata=asdict(self.meta),
            analysis_summary=asdict(profile),
            filtergraph=filtergraph,
            execution_time_sec=round(elapsed, 2),
            output_size_mb=round(output_mb, 2),
            effective_fps=round(effective_fps, 2),
            warnings=warnings,
        )


def upscale_video(
    input_path: str,
    output_path: str,
    scale_factor: Optional[float] = 2.0,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    quality: str = "quality",
    scaler: str = "auto",
    codec: str = "h264",
    crf: int = 18,
    deinterlace: bool = False,
    auto_exposure: bool = True,
    auto_color_balance: bool = True,
    progress_callback: Optional[Callable[[float, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    try:
        engine = VideoUpscalerEngine(
            input_path=input_path,
            output_path=output_path,
            scale_factor=scale_factor,
            target_width=target_width,
            target_height=target_height,
            quality_mode=quality,
            scaler=scaler,
            codec=codec,
            crf=crf,
            deinterlace=deinterlace,
            auto_exposure=auto_exposure,
            auto_color_balance=auto_color_balance,
        )
        return asdict(engine.run(progress_callback=progress_callback))
    except Exception as exc:
        logger.exception("Upscale job failed")
        return {
            "success": False,
            "input_path": input_path,
            "output_path": output_path,
            "error_message": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Classical Zero-AI CPU Video Upscaler")
    parser.add_argument("-i", "--input", required=False, help="Input video path")
    parser.add_argument("-o", "--output", default="output.mp4", help="Output video path")
    parser.add_argument("--scale", type=float, default=None, help="Scaling factor, e.g. 2 or 4")
    parser.add_argument("--width", type=int, default=None, help="Explicit target width")
    parser.add_argument("--height", type=int, default=None, help="Explicit target height")
    parser.add_argument("--quality", choices=["fast", "balanced", "quality", "max"], default="quality")
    parser.add_argument("--scaler", choices=["auto", "spline", "lanczos", "bicubic"], default="auto")
    parser.add_argument("--codec", choices=["h264", "hevc"], default="h264")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--deinterlace", action="store_true")
    parser.add_argument("--no-auto-exposure", action="store_true")
    parser.add_argument("--no-color-balance", action="store_true")
    parser.add_argument("--job-id", default=None, help="Optional backend job identifier for logging")
    parser.add_argument("--check-environment", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.check_environment:
        ok, details = check_environment(verbose=True)
        if args.json:
            print(json.dumps(details))
        raise SystemExit(0 if ok else 1)

    if not args.input:
        parser.error("-i/--input is required unless --check-environment is used")

    def console_progress(percent: float, info: Dict[str, Any]) -> None:
        speed = info.get("speed", "0x")
        fps = float(info.get("fps", 0.0) or 0.0)
        eta = int(float(info.get("eta_sec", 0.0) or 0.0))
        phase = info.get("phase", "processing")
        status = info.get("status", phase)
        sys.stdout.write(
            f"\rProgress: {percent:5.1f}% | Speed: {speed} | FPS: {fps:4.1f} | ETA: {eta}s | {status}"
        )
        sys.stdout.flush()

    result = upscale_video(
        input_path=args.input,
        output_path=args.output,
        scale_factor=args.scale,
        target_width=args.width,
        target_height=args.height,
        quality=args.quality,
        scaler=args.scaler,
        codec=args.codec,
        crf=args.crf,
        deinterlace=args.deinterlace,
        auto_exposure=not args.no_auto_exposure,
        auto_color_balance=not args.no_color_balance,
        progress_callback=None if args.json else console_progress,
    )
    if not args.json:
        print()
    if args.json:
        print(json.dumps(result, indent=2))
    if not result.get("success"):
        message = result.get("error_message") or "Python engine failed without a diagnostic message."
        logger.error("ENGINE_FAILED: %s", message)
        print(json.dumps({"success": False, "error_message": message}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
