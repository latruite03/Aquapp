from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Photo:
    id: str
    created_at: str
    source: str
    filename: str
    filepath: str
    content_type: str


@dataclass
class Analysis:
    id: str
    photo_id: str
    created_at: str
    model: str
    json_text: str | None
    raw_text: str
    success: bool
