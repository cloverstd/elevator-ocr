from __future__ import annotations

import importlib
import re
from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import cv2
import numpy as np

from app.config import Settings
from app.feedback_store import FeedbackStore
from app.ml_runtime import OptionalClassifier
from app.models import ROI, RecognitionCandidate, RecognitionResult

FLOOR_PATTERN = re.compile(r"^-?\d+$")
SYMBOL_CANVAS = (64, 96)
DIR_CANVAS = (64, 64)
FLOOR_CANVAS = (180, 120)
FLOOR_RAW_CANVAS = (120, 80)


def normalize_floor_text(raw_text: str, allowed_floors: list[str]) -> str | None:
    cleaned = raw_text.strip().replace(" ", "")
    if not cleaned:
        return None

    cleaned = cleaned.replace("—", "-").replace("–", "-")
    if re.search(r"[^0-9-]", cleaned):
        return None
    if not FLOOR_PATTERN.match(cleaned):
        return None

    sign = ""
    number = cleaned
    if cleaned.startswith("-"):
        sign = "-"
        number = cleaned[1:]
    number = number.lstrip("0") or "0"
    normalized = f"{sign}{number}"
    return normalized if normalized in allowed_floors else None


def crop_roi(frame: np.ndarray, roi: ROI) -> np.ndarray:
    if abs(roi.angle) < 0.001:
        y_slice, x_slice = roi.as_slice()
        return frame[y_slice, x_slice]

    source = np.array(roi.corners(), dtype=np.float32)
    target = np.array(
        [
            [0, 0],
            [roi.w - 1, 0],
            [roi.w - 1, roi.h - 1],
            [0, roi.h - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, target)
    return cv2.warpPerspective(frame, transform, (roi.w, roi.h))


def preprocess_floor_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=5.0, fy=5.0, interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
    _, thresholded = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )
    white_ratio = float(np.count_nonzero(thresholded)) / float(thresholded.size or 1)
    if white_ratio < 0.45:
        thresholded = cv2.bitwise_not(thresholded)
    return cv2.copyMakeBorder(
        thresholded,
        18,
        18,
        18,
        18,
        cv2.BORDER_CONSTANT,
        value=255,
    )


def preprocess_floor_variants(image: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=5.0, fy=5.0, interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    variants: list[np.ndarray] = []
    for candidate in (otsu, adaptive):
        white_ratio = float(np.count_nonzero(candidate)) / float(candidate.size or 1)
        prepared = cv2.bitwise_not(candidate) if white_ratio < 0.45 else candidate
        variants.append(
            cv2.copyMakeBorder(
                prepared,
                18,
                18,
                18,
                18,
                cv2.BORDER_CONSTANT,
                value=255,
            )
        )
        variants.append(
            cv2.copyMakeBorder(
                cv2.dilate(prepared, np.ones((2, 2), dtype=np.uint8), iterations=1),
                18,
                18,
                18,
                18,
                cv2.BORDER_CONSTANT,
                value=255,
            )
        )
    return variants


def _load_pytesseract() -> Any:
    return importlib.import_module("pytesseract")


def run_floor_ocr(
    image: np.ndarray,
    allowed_floors: list[str],
    tesseract_cmd: str | None = None,
) -> tuple[str | None, float | None]:
    full_template_text, full_template_confidence = classify_floor_label_with_templates(
        image,
        allowed_floors,
    )
    if (
        full_template_text is not None
        and (full_template_confidence is None or full_template_confidence >= 0.58)
    ):
        return full_template_text, (full_template_confidence or 0.0) * 100.0

    template_text, template_confidence = classify_floor_with_templates(image, allowed_floors)
    if template_text is not None and (template_confidence is None or template_confidence >= 0.60):
        return template_text, (template_confidence or 0.0) * 100.0

    pytesseract = _load_pytesseract()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    best_text = None
    best_confidence = None
    best_score = None
    variants = [image] if len(image.shape) == 2 else preprocess_floor_variants(image)
    configs = (
        "--psm 7 -c tessedit_char_whitelist=0123456789-",
        "--psm 8 -c tessedit_char_whitelist=0123456789-",
        "--psm 13 -c tessedit_char_whitelist=0123456789-",
    )
    for variant in variants:
        for config in configs:
            data = pytesseract.image_to_data(
                variant,
                config=config,
                output_type=pytesseract.Output.DICT,
            )
            for raw_text, confidence in zip(data["text"], data["conf"], strict=False):
                try:
                    confidence_value = float(confidence)
                except (TypeError, ValueError):
                    continue
                if confidence_value < 0:
                    continue

                normalized = normalize_floor_text(raw_text, allowed_floors)
                if normalized is None:
                    continue

                score = confidence_value + (len(normalized.replace("-", "")) * 8)
                if best_score is None or score > best_score:
                    best_score = score
                    best_text = normalized
                    best_confidence = confidence_value

    segmented_text, segmented_confidence = run_segmented_floor_ocr(
        image,
        allowed_floors,
        tesseract_cmd,
    )

    if segmented_text is not None:
        if best_text is None:
            return segmented_text, segmented_confidence
        if len(segmented_text.replace("-", "")) > len(best_text.replace("-", "")):
            return segmented_text, segmented_confidence
        if (
            segmented_confidence is not None
            and best_confidence is not None
            and segmented_confidence >= best_confidence - 8
        ):
            return segmented_text, segmented_confidence

    if best_confidence is not None and best_confidence < 25:
        return None, best_confidence

    return best_text, best_confidence


def run_segmented_floor_ocr(
    image: np.ndarray,
    allowed_floors: list[str],
    tesseract_cmd: str | None = None,
) -> tuple[str | None, float | None]:
    variants = preprocess_floor_variants(image)
    best_text = None
    best_confidence = None
    best_score = None

    for variant in variants:
        for segment_images in split_character_candidates(variant):
            chars: list[str] = []
            confidences: list[float] = []
            for segment in segment_images:
                char, confidence = run_symbol_ocr(segment, tesseract_cmd)
                if char is None or confidence is None:
                    chars = []
                    break
                chars.append(char)
                confidences.append(confidence)
            if not chars:
                continue

            candidate = "".join(chars)
            normalized = normalize_floor_text(candidate, allowed_floors)
            if normalized is None:
                continue

            confidence_value = sum(confidences) / len(confidences)
            score = confidence_value + (len(normalized.replace("-", "")) * 10)
            if best_score is None or score > best_score:
                best_score = score
                best_text = normalized
                best_confidence = confidence_value

    return best_text, best_confidence


def split_character_candidates(image: np.ndarray) -> list[list[np.ndarray]]:
    mask = (image < 180).astype(np.uint8)
    col_sum = mask.sum(axis=0)
    nonzero = np.where(col_sum > 0)[0]
    if len(nonzero) == 0:
        return []

    left = max(0, int(nonzero[0]) - 2)
    right = min(image.shape[1] - 1, int(nonzero[-1]) + 2)
    working = image[:, left : right + 1]
    mask = (working < 180).astype(np.uint8)
    col_sum = mask.sum(axis=0)

    candidates: list[list[np.ndarray]] = [[working]]
    splits = find_split_positions(col_sum)
    for split in splits:
        left_img = working[:, :split]
        right_img = working[:, split:]
        candidates.append([left_img, right_img])
    return [normalize_segment_list(parts) for parts in candidates]


def find_split_positions(col_sum: np.ndarray) -> list[int]:
    width = len(col_sum)
    if width < 12:
        return []

    max_col = int(col_sum.max() or 0)
    if max_col == 0:
        return []

    search_start = max(6, width // 4)
    search_end = min(width - 6, (width * 3) // 4)
    if search_end <= search_start:
        return []

    minima: list[int] = []
    threshold = max(2, int(max_col * 0.45))
    for idx in range(search_start + 1, search_end - 1):
        value = int(col_sum[idx])
        if value > threshold:
            continue
        if value <= int(col_sum[idx - 1]) and value <= int(col_sum[idx + 1]):
            minima.append(idx)

    if not minima:
        center = int(np.argmin(col_sum[search_start:search_end])) + search_start
        if int(col_sum[center]) <= max(4, int(max_col * 0.55)):
            return [center]
        return []

    return [minima[len(minima) // 2]]


def normalize_segment_list(parts: list[np.ndarray]) -> list[np.ndarray]:
    normalized: list[np.ndarray] = []
    for part in parts:
        mask = (part < 180).astype(np.uint8)
        rows = np.where(mask.sum(axis=1) > 0)[0]
        cols = np.where(mask.sum(axis=0) > 0)[0]
        if len(rows) == 0 or len(cols) == 0:
            continue
        cropped = part[max(0, rows[0] - 2) : rows[-1] + 3, max(0, cols[0] - 2) : cols[-1] + 3]
        normalized.append(cropped)
    return normalized


def run_symbol_ocr(
    image: np.ndarray,
    tesseract_cmd: str | None = None,
) -> tuple[str | None, float | None]:
    pytesseract = _load_pytesseract()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    prepared = cv2.resize(image, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    prepared = cv2.copyMakeBorder(
        prepared,
        16,
        16,
        16,
        16,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    best_char = None
    best_confidence = None
    for config in (
        "--psm 10 -c tessedit_char_whitelist=0123456789-",
        "--psm 13 -c tessedit_char_whitelist=0123456789-",
    ):
        data = pytesseract.image_to_data(
            prepared,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
        for raw_text, confidence in zip(data["text"], data["conf"], strict=False):
            raw_text = raw_text.strip()
            if len(raw_text) != 1 or raw_text not in "0123456789-":
                continue
            try:
                confidence_value = float(confidence)
            except (TypeError, ValueError):
                continue
            if confidence_value < 0:
                continue
            if best_confidence is None or confidence_value > best_confidence:
                best_char = raw_text
                best_confidence = confidence_value
    return best_char, best_confidence


def _build_arrow_template(direction: str, size: int = 64) -> np.ndarray:
    image = np.zeros((size, size), dtype=np.uint8)
    if direction == "up":
        points = np.array(
            [
                [size // 2, size // 8],
                [size // 8, size // 2],
                [size // 3, size // 2],
                [size // 3, size - size // 8],
                [2 * size // 3, size - size // 8],
                [2 * size // 3, size // 2],
                [7 * size // 8, size // 2],
            ],
            dtype=np.int32,
        )
    elif direction == "down":
        points = np.array(
            [
                [size // 3, size // 8],
                [2 * size // 3, size // 8],
                [2 * size // 3, size // 2],
                [7 * size // 8, size // 2],
                [size // 2, size - size // 8],
                [size // 8, size // 2],
                [size // 3, size // 2],
            ],
            dtype=np.int32,
        )
    else:
        raise ValueError(f"Unsupported direction template: {direction}")
    cv2.fillConvexPoly(image, points, 255)
    return image


UP_TEMPLATE = _build_arrow_template("up")
DOWN_TEMPLATE = _build_arrow_template("down")


def preprocess_direction_image(image: np.ndarray, size: int = 96) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=6.0, fy=6.0, interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
    _, thresholded = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )
    white_ratio = float(np.count_nonzero(thresholded)) / float(thresholded.size or 1)
    if white_ratio > 0.55:
        thresholded = cv2.bitwise_not(thresholded)
    thresholded = cv2.morphologyEx(
        thresholded,
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
    )
    return cv2.resize(thresholded, (size, size), interpolation=cv2.INTER_AREA)


def detect_direction(image: np.ndarray, threshold: float) -> tuple[str, float]:
    processed = preprocess_direction_image(image)
    active_ratio = float(np.count_nonzero(processed)) / float(processed.size or 1)
    if active_ratio < 0.01:
        return "idle", 1.0

    template_direction, template_score = classify_direction_with_templates(image)
    if template_direction is not None and template_score >= 0.55:
        return template_direction, template_score

    points = cv2.findNonZero(processed)
    if points is None:
        return "idle", 1.0

    x, y, w, h = cv2.boundingRect(points)
    cropped = processed[y : y + h, x : x + w]
    if cropped.size == 0:
        return "unknown", 0.0

    moments = cv2.moments(cropped)
    centroid_y = 0.5
    if moments["m00"] > 0:
        centroid_y = float(moments["m01"] / moments["m00"]) / max(1.0, cropped.shape[0] - 1)

    rows = (cropped > 0).sum(axis=1).astype(np.float32)
    split = max(1, len(rows) // 2)
    top_energy = float(rows[:split].sum())
    bottom_energy = float(rows[split:].sum())
    balance = (top_energy - bottom_energy) / max(1.0, top_energy + bottom_energy)

    resized = cv2.resize(cropped, (64, 64), interpolation=cv2.INTER_AREA)
    up_score = float(cv2.matchTemplate(resized, UP_TEMPLATE, cv2.TM_CCOEFF_NORMED)[0][0])
    down_score = float(
        cv2.matchTemplate(resized, DOWN_TEMPLATE, cv2.TM_CCOEFF_NORMED)[0][0]
    )

    if max(up_score, down_score) >= threshold:
        if up_score > down_score:
            return "up", max(up_score, abs(balance), abs(centroid_y - 0.5) * 2)
        return "down", max(down_score, abs(balance), abs(centroid_y - 0.5) * 2)

    if centroid_y >= 0.58:
        return "up", min(0.99, (centroid_y - 0.5) * 3)
    if centroid_y <= 0.42:
        return "down", min(0.99, (0.5 - centroid_y) * 3)

    if abs(balance) >= 0.08:
        return ("up" if balance > 0 else "down"), min(0.99, abs(balance) * 3)

    return "unknown", max(up_score, down_score, abs(balance))


def classify_floor_with_templates(
    image: np.ndarray,
    allowed_floors: list[str],
) -> tuple[str | None, float | None]:
    templates = load_floor_symbol_templates()
    if not templates:
        return None, None

    best_text = None
    best_score = None
    for mask in preprocess_floor_masks(image):
        for parts in split_mask_candidates(mask):
            chars: list[str] = []
            scores: list[float] = []
            for part in parts:
                symbol, score = classify_mask_symbol(part, templates, SYMBOL_CANVAS)
                if symbol is None or score is None:
                    chars = []
                    break
                chars.append(symbol)
                scores.append(score)
            if not chars:
                continue

            candidate = "".join(chars)
            normalized = normalize_floor_text(candidate, allowed_floors)
            if normalized is None:
                continue

            score = sum(scores) / len(scores)
            if best_score is None or score > best_score:
                best_text = normalized
                best_score = score

    return best_text, best_score


def classify_floor_label_with_templates(
    image: np.ndarray,
    allowed_floors: list[str],
) -> tuple[str | None, float | None]:
    templates = load_floor_label_templates()
    if not templates:
        return None, None

    allowed = set(allowed_floors)
    best_label = None
    best_score = None
    second_best = None
    gray_variants = preprocess_floor_gray_variants(image)
    mask_variants = preprocess_floor_masks(image)
    for mask, gray in zip(mask_variants, gray_variants, strict=False):
        digit_hint = estimate_digit_count_from_mask(mask)
        candidate_ratio = mask_aspect_ratio(mask)
        candidate = canonicalize_mask(mask, FLOOR_CANVAS).astype(np.float32) / 255.0
        candidate_gray = canonicalize_gray(gray, FLOOR_RAW_CANVAS)
        for label, variants in templates.items():
            if label not in allowed:
                continue
            for template in variants:
                mask_score = 1.0 - float(np.mean(np.abs(candidate - template["mask"])))
                raw_score = 1.0 - float(np.mean(np.abs(candidate_gray - template["gray"])))
                score = (mask_score * 0.45) + (raw_score * 0.55)
                if digit_hint is not None and template["digit_count"] != digit_hint:
                    score -= 0.12
                score -= min(0.18, abs(candidate_ratio - template["aspect_ratio"]) * 0.16)
                if best_score is None or score > best_score:
                    second_best = best_score
                    best_label = label
                    best_score = score
                elif second_best is None or score > second_best:
                    second_best = score
    if best_score is None:
        return None, None
    if second_best is not None and best_score - second_best < 0.06:
        return None, best_score
    return best_label, best_score


def classify_direction_with_templates(image: np.ndarray) -> tuple[str | None, float]:
    templates = load_direction_templates()
    if not templates:
        return None, 0.0

    mask = direction_match_mask(image)
    label, score = classify_mask_symbol(mask, templates, DIR_CANVAS)
    return label, score or 0.0


def floor_sample_features(image: np.ndarray) -> dict[str, np.ndarray | float | int | None]:
    masks = preprocess_floor_masks(image)
    grays = preprocess_floor_gray_variants(image)
    mask = masks[0] if masks else np.zeros((FLOOR_CANVAS[1], FLOOR_CANVAS[0]), dtype=np.uint8)
    gray = grays[0] if grays else np.zeros((FLOOR_RAW_CANVAS[1], FLOOR_RAW_CANVAS[0]), dtype=np.uint8)
    return {
        "mask": canonicalize_mask(mask, FLOOR_CANVAS).astype(np.float32) / 255.0,
        "gray": canonicalize_gray(gray, FLOOR_RAW_CANVAS),
        "aspect_ratio": mask_aspect_ratio(mask),
        "digit_count": estimate_digit_count_from_mask(mask),
    }


def direction_sample_features(image: np.ndarray) -> dict[str, np.ndarray]:
    return {"mask": canonicalize_mask(direction_match_mask(image), DIR_CANVAS).astype(np.float32) / 255.0}


@dataclass(slots=True)
class SamplePrototypeMatcher:
    kind: str
    settings: Settings
    feedback_store: FeedbackStore
    enabled: bool = False
    _variants: dict[str, list[dict[str, Any]]] | None = None

    def __post_init__(self) -> None:
        self._variants = {}
        self.reload()

    def reload(self) -> bool:
        variants: dict[str, list[dict[str, Any]]] = {}
        rows = self.feedback_store.labeled_samples("floor" if self.kind == "floor" else "direction")
        for row in rows:
            label = str(row["confirmed_label"])
            if self.kind == "floor" and label not in self.settings.allowed_floors:
                continue
            if self.kind == "direction" and label not in {"up", "down", "idle", "unknown"}:
                continue
            path = Path(str(row["image_path"]))
            image = cv2.imread(str(path))
            if image is None:
                continue
            feature = (
                floor_sample_features(image)
                if self.kind == "floor"
                else direction_sample_features(image)
            )
            variants.setdefault(label, []).append(feature)
        self._variants = variants
        self.enabled = bool(variants)
        return self.enabled

    def predict(self, image: np.ndarray) -> tuple[str | None, float | None]:
        ranked = self.rank(image, limit=2)
        if not ranked:
            return None, None
        if len(ranked) > 1 and ranked[0].score - ranked[1].score < 0.03:
            return None, ranked[0].score
        return ranked[0].label, ranked[0].score

    def rank(self, image: np.ndarray, limit: int = 3) -> list[RecognitionCandidate]:
        if not self.enabled:
            return []
        feature = floor_sample_features(image) if self.kind == "floor" else direction_sample_features(image)
        scored: list[tuple[str, float]] = []
        for label, variants in self._variants.items():
            label_best = None
            for variant in variants:
                score = self._score(feature, variant)
                if label_best is None or score > label_best:
                    label_best = score
            if label_best is None:
                continue
            scored.append((label, label_best))

        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            RecognitionCandidate(label=label, score=score, source="sample")
            for label, score in scored[:limit]
        ]

    def _score(self, candidate: dict[str, Any], variant: dict[str, Any]) -> float:
        if self.kind == "direction":
            return 1.0 - float(np.mean(np.abs(candidate["mask"] - variant["mask"])))

        mask_score = 1.0 - float(np.mean(np.abs(candidate["mask"] - variant["mask"])))
        gray_score = 1.0 - float(np.mean(np.abs(candidate["gray"] - variant["gray"])))
        score = (gray_score * 0.68) + (mask_score * 0.32)
        candidate_digit_count = candidate["digit_count"]
        variant_digit_count = variant["digit_count"]
        if candidate_digit_count is not None and variant_digit_count is not None and candidate_digit_count != variant_digit_count:
            score -= 0.12
        score -= min(
            0.18,
            abs(float(candidate["aspect_ratio"]) - float(variant["aspect_ratio"])) * 0.16,
        )
        return score


def preprocess_floor_masks(image: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=8.0, fy=8.0, interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
    otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        5,
    )
    variants: list[np.ndarray] = []
    for candidate in (otsu, adaptive):
        if float(np.count_nonzero(candidate)) / float(candidate.size or 1) > 0.5:
            candidate = cv2.bitwise_not(candidate)
        candidate = cv2.morphologyEx(
            candidate,
            cv2.MORPH_OPEN,
            np.ones((2, 2), dtype=np.uint8),
        )
        variants.append(candidate)
        variants.append(cv2.dilate(candidate, np.ones((2, 2), dtype=np.uint8), iterations=1))
    return variants


def preprocess_floor_gray_variants(image: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=6.0, fy=6.0, interpolation=cv2.INTER_CUBIC)
    equalized = cv2.equalizeHist(scaled)
    denoised = cv2.GaussianBlur(equalized, (3, 3), 0)
    sharpened = cv2.addWeighted(equalized, 1.35, denoised, -0.35, 0)
    softened = cv2.GaussianBlur(sharpened, (5, 5), 0)
    return [sharpened, softened]


def direction_match_mask(image: np.ndarray) -> np.ndarray:
    processed = preprocess_direction_image(image)
    if float(np.count_nonzero(processed)) / float(processed.size or 1) > 0.5:
        processed = cv2.bitwise_not(processed)
    return processed


def split_mask_candidates(mask: np.ndarray) -> list[list[np.ndarray]]:
    col_sum = (mask > 0).sum(axis=0)
    nonzero = np.where(col_sum > 0)[0]
    if len(nonzero) == 0:
        return []

    left = max(0, int(nonzero[0]) - 2)
    right = min(mask.shape[1] - 1, int(nonzero[-1]) + 2)
    working = mask[:, left : right + 1]
    col_sum = (working > 0).sum(axis=0)

    candidates: list[list[np.ndarray]] = [normalize_mask_segments([working])]
    for split in find_split_positions(col_sum):
        left_img = working[:, :split]
        right_img = working[:, split:]
        segments = normalize_mask_segments([left_img, right_img])
        if segments:
            candidates.append(segments)
    return [parts for parts in candidates if parts]


def normalize_mask_segments(parts: list[np.ndarray]) -> list[np.ndarray]:
    normalized: list[np.ndarray] = []
    for part in parts:
        rows = np.where((part > 0).sum(axis=1) > 0)[0]
        cols = np.where((part > 0).sum(axis=0) > 0)[0]
        if len(rows) == 0 or len(cols) == 0:
            continue
        cropped = part[max(0, rows[0] - 2) : rows[-1] + 3, max(0, cols[0] - 2) : cols[-1] + 3]
        normalized.append(cropped)
    return normalized


def canonicalize_mask(mask: np.ndarray, canvas: tuple[int, int]) -> np.ndarray:
    rows = np.where((mask > 0).sum(axis=1) > 0)[0]
    cols = np.where((mask > 0).sum(axis=0) > 0)[0]
    if len(rows) == 0 or len(cols) == 0:
        return np.zeros((canvas[1], canvas[0]), dtype=np.uint8)

    cropped = mask[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
    target_w, target_h = canvas
    scale = min(target_w / max(1, cropped.shape[1]), target_h / max(1, cropped.shape[0]))
    resized = cv2.resize(
        cropped,
        (max(1, int(round(cropped.shape[1] * scale))), max(1, int(round(cropped.shape[0] * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    canvas_img = np.zeros((target_h, target_w), dtype=np.uint8)
    x = (target_w - resized.shape[1]) // 2
    y = (target_h - resized.shape[0]) // 2
    canvas_img[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas_img


def canonicalize_gray(image: np.ndarray, canvas: tuple[int, int]) -> np.ndarray:
    gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    rows = np.where((255 - gray).sum(axis=1) > 0)[0]
    cols = np.where((255 - gray).sum(axis=0) > 0)[0]
    if len(rows) == 0 or len(cols) == 0:
        return np.zeros((canvas[1], canvas[0]), dtype=np.float32)

    cropped = gray[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
    target_w, target_h = canvas
    scale = min(target_w / max(1, cropped.shape[1]), target_h / max(1, cropped.shape[0]))
    resized = cv2.resize(
        cropped,
        (max(1, int(round(cropped.shape[1] * scale))), max(1, int(round(cropped.shape[0] * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    canvas_img = np.zeros((target_h, target_w), dtype=np.uint8)
    x = (target_w - resized.shape[1]) // 2
    y = (target_h - resized.shape[0]) // 2
    canvas_img[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas_img.astype(np.float32) / 255.0


def mask_aspect_ratio(mask: np.ndarray) -> float:
    rows = np.where((mask > 0).sum(axis=1) > 0)[0]
    cols = np.where((mask > 0).sum(axis=0) > 0)[0]
    if len(rows) == 0 or len(cols) == 0:
        return 1.0
    width = max(1, int(cols[-1] - cols[0] + 1))
    height = max(1, int(rows[-1] - rows[0] + 1))
    return width / height


def estimate_digit_count_from_mask(mask: np.ndarray) -> int | None:
    rows = np.where((mask > 0).sum(axis=1) > 0)[0]
    cols = np.where((mask > 0).sum(axis=0) > 0)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    cropped = mask[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
    ratio = cropped.shape[1] / max(1, cropped.shape[0])
    if ratio >= 0.9:
        return 2
    return 1


def classify_mask_symbol(
    mask: np.ndarray,
    templates: dict[str, list[np.ndarray]],
    canvas: tuple[int, int],
) -> tuple[str | None, float | None]:
    candidate = canonicalize_mask(mask, canvas).astype(np.float32) / 255.0
    best_label = None
    best_score = None
    for label, variants in templates.items():
        for template in variants:
            score = 1.0 - float(np.mean(np.abs(candidate - template)))
            if best_score is None or score > best_score:
                best_label = label
                best_score = score
    return best_label, best_score


@lru_cache(maxsize=1)
def load_floor_symbol_templates() -> dict[str, list[np.ndarray]]:
    root = Path(__file__).resolve().parent.parent / "img"
    templates: dict[str, list[np.ndarray]] = {}
    if not root.exists():
        return templates

    for path in root.glob("*.png"):
        label = path.stem
        if label in {"up", "down"}:
            continue
        image = cv2.imread(str(path))
        if image is None:
            continue
        masks = preprocess_floor_masks(image)
        segments = None
        for mask in masks:
            for candidate in split_mask_candidates(mask):
                if len(candidate) == len(label):
                    segments = candidate
                    break
            if segments is not None:
                break
        if segments is None:
            continue
        for ch, segment in zip(label, segments, strict=False):
            templates.setdefault(ch, []).append(canonicalize_mask(segment, SYMBOL_CANVAS).astype(np.float32) / 255.0)
    return templates


@lru_cache(maxsize=1)
def load_floor_label_templates() -> dict[str, list[dict[str, Any]]]:
    root = Path(__file__).resolve().parent.parent / "img"
    templates: dict[str, list[dict[str, Any]]] = {}
    if not root.exists():
        return templates

    for path in root.glob("*.png"):
        label = path.stem
        if label in {"up", "down"}:
            continue
        image = cv2.imread(str(path))
        if image is None:
            continue
        masks = preprocess_floor_masks(image)
        grays = preprocess_floor_gray_variants(image)
        for mask, gray in zip(masks, grays, strict=False):
            templates.setdefault(label, []).append(
                {
                    "mask": canonicalize_mask(mask, FLOOR_CANVAS).astype(np.float32) / 255.0,
                    "gray": canonicalize_gray(gray, FLOOR_RAW_CANVAS),
                    "aspect_ratio": mask_aspect_ratio(mask),
                    "digit_count": 1 if label.startswith("-") and len(label) == 2 else len(label.lstrip("-")),
                }
            )
    return templates


@lru_cache(maxsize=1)
def load_direction_templates() -> dict[str, list[np.ndarray]]:
    root = Path(__file__).resolve().parent.parent / "img"
    templates: dict[str, list[np.ndarray]] = {}
    if not root.exists():
        return templates

    for label in ("up", "down"):
        path = root / f"{label}.png"
        image = cv2.imread(str(path))
        if image is None:
            continue
        mask = direction_match_mask(image)
        templates.setdefault(label, []).append(canonicalize_mask(mask, DIR_CANVAS).astype(np.float32) / 255.0)
    return templates


@dataclass(slots=True)
class FrameRecognizer:
    settings: Settings
    floor_sample_matcher: SamplePrototypeMatcher | None = None
    direction_sample_matcher: SamplePrototypeMatcher | None = None
    floor_classifier: OptionalClassifier | None = None
    direction_classifier: OptionalClassifier | None = None

    def recognize(self, frame: np.ndarray, observed_at: datetime) -> RecognitionResult:
        floor_image = crop_roi(frame, self.settings.floor_roi)
        floor, confidence = run_floor_ocr(
            floor_image,
            self.settings.allowed_floors,
            self.settings.tesseract_cmd,
        )
        floor_source = "ocr"
        floor_candidates = (
            [RecognitionCandidate(label=floor, score=max(0.0, min(1.0, (confidence or 0.0) / 100.0)), source="ocr")]
            if floor is not None
            else []
        )
        if self.floor_sample_matcher is not None:
            ranked = self.floor_sample_matcher.rank(floor_image, limit=3)
            prediction = ranked[0].label if ranked else None
            match_score = ranked[0].score if ranked else None
            floor_candidates = ranked or floor_candidates
            if (
                prediction is not None
                and prediction in self.settings.allowed_floors
                and match_score is not None
                and match_score >= self.settings.floor_sample_match_threshold
            ):
                floor = prediction
                confidence = match_score * 100.0
                floor_source = "sample"
        if self.floor_classifier is not None:
            ranked = self.floor_classifier.predict_topk(floor_image, limit=3)
            prediction = self.floor_classifier.predict(floor_image)
            if floor_source != "sample" and ranked:
                floor_candidates = ranked
            if (
                prediction is not None
                and prediction.label in self.settings.allowed_floors
                and prediction.confidence >= self.settings.floor_model_min_confidence
            ):
                floor = prediction.label
                confidence = prediction.confidence * 100.0
                floor_source = "model"
                floor_candidates = ranked or floor_candidates

        direction_image = crop_roi(frame, self.settings.direction_roi)
        direction, direction_score = detect_direction(
            direction_image,
            threshold=self.settings.direction_match_threshold,
        )
        direction_source = "template"
        direction_candidates = [
            RecognitionCandidate(
                label=direction,
                score=direction_score,
                source="template",
            )
        ]
        if self.direction_sample_matcher is not None:
            ranked = self.direction_sample_matcher.rank(direction_image, limit=3)
            prediction = ranked[0].label if ranked else None
            match_score = ranked[0].score if ranked else None
            direction_candidates = ranked or direction_candidates
            if (
                prediction is not None
                and prediction in {"up", "down", "idle", "unknown"}
                and match_score is not None
                and match_score >= self.settings.direction_sample_match_threshold
            ):
                direction = prediction
                direction_source = "sample"
        if self.direction_classifier is not None:
            ranked = self.direction_classifier.predict_topk(direction_image, limit=3)
            prediction = self.direction_classifier.predict(direction_image)
            if direction_source != "sample" and ranked:
                direction_candidates = ranked
            if (
                prediction is not None
                and prediction.label in {"up", "down", "idle", "unknown"}
                and prediction.confidence >= self.settings.direction_model_min_confidence
            ):
                direction = prediction.label
                direction_source = "model"
                direction_candidates = ranked or direction_candidates
        return RecognitionResult(
            floor=floor,
            direction=direction,
            confidence=confidence,
            observed_at=observed_at,
            floor_source=floor_source,
            direction_source=direction_source,
            floor_candidates=floor_candidates,
            direction_candidates=direction_candidates,
        )
