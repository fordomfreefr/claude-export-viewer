"""Building a site from conversations given in the test itself, through the archive (as the program does)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from claude_export_viewer.archive import Archive
from claude_export_viewer.html_builder import build_site_from_archive
from claude_export_viewer.loader import ExportDate
from claude_export_viewer.models import Conversation

EXPORT_DATE = ExportDate(datetime(2026, 10, 23, tzinfo=timezone.utc), "test")


@dataclass
class ExportData:
    users: list[Any] = field(default_factory=list)
    conversations: list[Any] = field(default_factory=list)


@dataclass
class Built:
    written: int  # conversations in the index
    skipped_empty: int


def raw(convo: Any) -> dict[str, Any]:
    """The export form (a dict) of a conversation written as a model in a test."""
    return convo.model_dump(mode="json", exclude_none=True) if isinstance(convo, BaseModel) else convo


def build_site(data: ExportData, output_dir: Path, skip_empty: bool = True) -> Built:
    archive = Archive(output_dir)
    records = [(r, Conversation.model_validate(r)) for r in map(raw, data.conversations)]
    stats = archive.import_export(records, EXPORT_DATE, skip_empty=skip_empty,
                                  users={u.uuid: u.full_name for u in data.users})
    archive.save()
    render = build_site_from_archive(archive, output_dir)
    return Built(render.total, stats.skipped_empty)
