"""Validation helpers for quotation installation-plan snapshots."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from .uploads import UploadError, validate_image

MAX_PLAN_STATE_BYTES = 256_000
MAX_PLAN_ITEMS = 200
MAX_PLAN_LABELS = 200
MAX_CANVAS_DIMENSION = 8_000
CAMERA_TYPES = {"dome", "bullet", "ptz"}
CAMERA_SHADES = {"black", "white"}
EQUIPMENT_VARIANTS = {
    "smart_barrier": {"left", "right"},
    "generator": {"solid", "outline"},
    "solar_pole": {"standard"},
    "solar_panel": {"solid", "outline"},
    "guard_room": {"standard"},
    "metal_pole": {"white", "black"},
    "sign": {"standard"},
}
MOUNTABLE_EQUIPMENT_KINDS = {"solar_pole", "metal_pole"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(slots=True)
class InstallationPlanSubmission:
    state: dict[str, Any]
    background_filename: str | None
    background_data: bytes | None
    output_filename: str
    output_data: bytes


def _number(
    value: object,
    label: str,
    minimum: float,
    maximum: float,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise UploadError(f"The installation plan has an invalid {label}.") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise UploadError(f"The installation plan has an invalid {label}.")
    return number


def _text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise UploadError(f"The installation plan has an invalid {label}.")
    return value


def _color(value: object, label: str) -> str:
    text = _text(value, label, 7)
    if not HEX_COLOR_RE.fullmatch(text):
        raise UploadError(f"The installation plan has an invalid {label}.")
    return text.lower()


def validate_installation_plan_state(raw: object) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if len(text.encode("utf-8")) > MAX_PLAN_STATE_BYTES:
        raise UploadError("The installation plan contains too much layout data.")
    try:
        state = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UploadError("The installation plan data could not be read.") from exc
    if not isinstance(state, dict) or state.get("version") != 1:
        raise UploadError("The installation plan version is not supported.")

    normalized: dict[str, Any] = {
        "version": 1,
        "ppm": _number(state.get("ppm"), "drawing scale", 5, 200),
        "contentW": _number(
            state.get("contentW"), "canvas width", 1, MAX_CANVAS_DIMENSION
        ),
        "contentH": _number(
            state.get("contentH"), "canvas height", 1, MAX_CANVAS_DIMENSION
        ),
        "hasBackground": bool(state.get("hasBackground")),
        "items": [],
        "labels": [],
    }

    items = state.get("items", [])
    labels = state.get("labels", [])
    if not isinstance(items, list) or len(items) > MAX_PLAN_ITEMS:
        raise UploadError("The installation plan can contain up to 200 equipment items.")
    if not isinstance(labels, list) or len(labels) > MAX_PLAN_LABELS:
        raise UploadError("The installation plan can contain up to 200 text labels.")

    for item in items:
        if not isinstance(item, dict):
            raise UploadError("The installation plan contains an unsupported equipment item.")
        kind = str(item.get("kind") or "")
        if kind in EQUIPMENT_VARIANTS:
            variant = str(item.get("variant") or "")
            if variant not in EQUIPMENT_VARIANTS[kind]:
                raise UploadError("The installation plan contains an invalid equipment variant.")
            normalized["items"].append(
                {
                    "id": _text(item.get("id"), "equipment identifier", 80),
                    "kind": kind,
                    "name": _text(item.get("name"), "equipment name", 60),
                    "variant": variant,
                    "x": _number(item.get("x"), "equipment position", -MAX_CANVAS_DIMENSION, MAX_CANVAS_DIMENSION * 2),
                    "y": _number(item.get("y"), "equipment position", -MAX_CANVAS_DIMENSION, MAX_CANVAS_DIMENSION * 2),
                    "widthMeters": _number(item.get("widthMeters"), "equipment width", 0.5, 50),
                    "rotation": _number(item.get("rotation"), "equipment rotation", 0, 360),
                    "opacity": _number(item.get("opacity"), "equipment opacity", 0.2, 1),
                }
            )
            continue
        if kind != "camera":
            raise UploadError("The installation plan contains an unsupported equipment item.")
        camera_type = str(item.get("type") or "")
        shade = str(item.get("shade") or "")
        if camera_type not in CAMERA_TYPES or shade not in CAMERA_SHADES:
            raise UploadError("The installation plan contains an invalid camera type.")
        mounted_on_id = item.get("mountedOnId")
        if mounted_on_id is not None:
            mounted_on_id = _text(mounted_on_id, "camera mounting reference", 80)
        normalized["items"].append(
            {
                "id": _text(item.get("id"), "camera identifier", 80),
                "kind": "camera",
                "name": _text(item.get("name"), "camera name", 40),
                "type": camera_type,
                "shade": shade,
                "x": _number(item.get("x"), "camera position", -MAX_CANVAS_DIMENSION, MAX_CANVAS_DIMENSION * 2),
                "y": _number(item.get("y"), "camera position", -MAX_CANVAS_DIMENSION, MAX_CANVAS_DIMENSION * 2),
                "fov": _number(item.get("fov"), "camera field of view", 5, 350),
                "range": _number(item.get("range"), "camera range", 0.5, 200),
                "rotation": _number(item.get("rotation"), "camera rotation", 0, 360),
                "color": _color(item.get("color"), "camera color"),
                "opacity": _number(item.get("opacity"), "camera opacity", 0, 1),
                "widthMeters": _number(item.get("widthMeters", 1.3), "camera width", 0.1, 10),
                "mountedOnId": mounted_on_id,
            }
        )

    mountable_equipment_ids = {
        item["id"]
        for item in normalized["items"]
        if item["kind"] in MOUNTABLE_EQUIPMENT_KINDS
    }
    if any(
        item["kind"] == "camera"
        and item["mountedOnId"] is not None
        and item["mountedOnId"] not in mountable_equipment_ids
        for item in normalized["items"]
    ):
        raise UploadError("The installation plan contains an invalid camera mounting reference.")

    for label in labels:
        if not isinstance(label, dict):
            raise UploadError("The installation plan contains an invalid text label.")
        normalized["labels"].append(
            {
                "id": _text(label.get("id"), "label identifier", 80),
                "text": _text(label.get("text"), "label text", 240),
                "x": _number(label.get("x"), "label position", -MAX_CANVAS_DIMENSION, MAX_CANVAS_DIMENSION * 2),
                "y": _number(label.get("y"), "label position", -MAX_CANVAS_DIMENSION, MAX_CANVAS_DIMENSION * 2),
                "width": _number(label.get("width"), "label width", 30, MAX_CANVAS_DIMENSION),
                "fontSize": _number(label.get("fontSize"), "label font size", 8, 160),
                "rotation": _number(label.get("rotation", 0), "label rotation", -360, 360),
                "color": _color(label.get("color"), "label color"),
            }
        )
    return normalized


def validate_installation_plan_submission(
    raw_state: object,
    *,
    background_filename: str | None,
    background_data: bytes | None,
    output_filename: str | None,
    output_data: bytes | None,
) -> InstallationPlanSubmission | None:
    state = validate_installation_plan_state(raw_state)
    has_files = bool(background_data or output_data)
    if state is None:
        if has_files:
            raise UploadError("The installation plan data is missing.")
        return None
    if not output_data:
        raise UploadError("The installation plan preview is missing. Generate it again.")
    output_filename = output_filename or "camera-installation-plan.png"
    validate_image(output_filename, output_data)
    if state["hasBackground"]:
        if not background_data:
            raise UploadError("The installation plan background is missing. Upload it again.")
        validate_image(background_filename or "floor-plan.png", background_data)
    elif background_data:
        validate_image(background_filename or "floor-plan.png", background_data)
    return InstallationPlanSubmission(
        state=state,
        background_filename=(background_filename or "floor-plan.png") if background_data else None,
        background_data=background_data,
        output_filename=output_filename,
        output_data=output_data,
    )
