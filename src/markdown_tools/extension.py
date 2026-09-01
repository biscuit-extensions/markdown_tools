from __future__ import annotations

import re
import typing
from dataclasses import dataclass, field
from typing import Any

from biscuit.extensions import Extension

if typing.TYPE_CHECKING:
    from biscuit.api import ExtensionsAPI


class TableAlignment:
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


def parse_alignment(cell: str) -> str:
    """Parse column alignment from delimiter cell."""
    c = cell.strip()
    if c.startswith(":") and c.endswith(":"):
        return TableAlignment.CENTER
    if c.endswith(":"):
        return TableAlignment.RIGHT
    return TableAlignment.LEFT


def format_table(table_text: str) -> str:
    """Format a single Markdown pipe table with aligned columns and standard delimiters."""
    lines = [line.strip() for line in table_text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return table_text

    def split_row(row_str: str) -> list[str]:
        s = row_str.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    raw_rows = [split_row(line) for line in lines]

    # Find delimiter row index
    delimiter_idx = -1
    for idx, row in enumerate(raw_rows):
        if row and all(bool(re.match(r"^:?-{3,}:?$", c) or re.match(r"^:?-+:?$", c)) for c in row if c):
            delimiter_idx = idx
            break

    if delimiter_idx == -1:
        return table_text

    num_cols = max(len(row) for row in raw_rows)
    for row in raw_rows:
        while len(row) < num_cols:
            row.append("")

    delim_row = raw_rows[delimiter_idx]
    alignments = [parse_alignment(delim_row[i] if i < len(delim_row) else "") for i in range(num_cols)]

    col_widths = [3] * num_cols
    for row_idx, row in enumerate(raw_rows):
        if row_idx == delimiter_idx:
            continue
        for col_idx, cell in enumerate(row):
            col_widths[col_idx] = max(col_widths[col_idx], len(cell))

    formatted_lines: list[str] = []
    for row_idx, row in enumerate(raw_rows):
        if row_idx == delimiter_idx:
            sep_cells = []
            for col_idx in range(num_cols):
                w = col_widths[col_idx]
                align = alignments[col_idx]
                if align == TableAlignment.CENTER:
                    sep = ":" + "-" * max(1, w - 2) + ":"
                elif align == TableAlignment.RIGHT:
                    sep = "-" * max(2, w - 1) + ":"
                else:
                    sep = ":" + "-" * max(2, w - 1)
                sep_cells.append(sep)
            formatted_lines.append("| " + " | ".join(sep_cells) + " |")
        else:
            cells = []
            for col_idx in range(num_cols):
                w = col_widths[col_idx]
                cell = row[col_idx]
                align = alignments[col_idx]
                if align == TableAlignment.CENTER:
                    cells.append(cell.center(w))
                elif align == TableAlignment.RIGHT:
                    cells.append(cell.rjust(w))
                else:
                    cells.append(cell.ljust(w))
            formatted_lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(formatted_lines)


def format_tables_in_markdown(content: str) -> str:
    """Detect and format all pipe tables within markdown content, preserving other text."""
    lines = content.splitlines()
    result_lines: list[str] = []
    table_buffer: list[str] = []
    in_code_block = False

    def flush_table():
        if not table_buffer:
            return
        raw_table = "\n".join(table_buffer)
        has_delim = any(
            re.search(r"\|?\s*:?-{2,}:?\s*\|", line)
            for line in table_buffer
        )
        if len(table_buffer) >= 2 and has_delim:
            formatted = format_table(raw_table)
            result_lines.extend(formatted.splitlines())
        else:
            result_lines.extend(table_buffer)
        table_buffer.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_table()
            in_code_block = not in_code_block
            result_lines.append(line)
            continue

        if in_code_block:
            result_lines.append(line)
            continue

        if "|" in line and (stripped.startswith("|") or stripped.endswith("|") or " | " in line):
            table_buffer.append(line)
        else:
            flush_table()
            result_lines.append(line)

    flush_table()
    return "\n".join(result_lines)


def slugify(text: str) -> str:
    """Generate anchor slug from heading text compatible with standard markdown anchors."""
    clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    clean = re.sub(r"[`*_~]", "", clean)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = clean.strip().lower()
    clean = re.sub(r"[^\w\s-]", "", clean)
    clean = re.sub(r"[\s_]+", "-", clean)
    clean = re.sub(r"-+", "-", clean).strip("-")
    return clean or "heading"


@dataclass
class HeadingNode:
    level: int
    title: str
    slug: str
    line_number: int
    children: list[HeadingNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "title": self.title,
            "slug": self.slug,
            "line_number": self.line_number,
            "children": [c.to_dict() for c in self.children],
        }


def parse_headings(content: str) -> list[HeadingNode]:
    """Parse all headings from markdown string, skipping code blocks."""
    lines = content.splitlines()
    headings: list[HeadingNode] = []
    in_code_block = False
    slug_counts: dict[str, int] = {}

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        match = re.match(r"^(#{1,6})\s+(.+?)(?:\s+#+)?$", stripped)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            base_slug = slugify(title)
            if base_slug in slug_counts:
                slug_counts[base_slug] += 1
                unique_slug = f"{base_slug}-{slug_counts[base_slug]}"
            else:
                slug_counts[base_slug] = 0
                unique_slug = base_slug

            headings.append(
                HeadingNode(
                    level=level,
                    title=title,
                    slug=unique_slug,
                    line_number=idx,
                )
            )

    return headings


def generate_toc(
    content: str,
    max_depth: int = 6,
    min_depth: int = 1,
    indent_spaces: int = 2,
    bullet_char: str = "-",
) -> str:
    """Generate Markdown Table of Contents bullet list with anchor links."""
    headings = parse_headings(content)
    filtered = [h for h in headings if min_depth <= h.level <= max_depth]
    if not filtered:
        return ""

    base_level = min(h.level for h in filtered)
    toc_lines: list[str] = []
    for h in filtered:
        indent = " " * ((h.level - base_level) * indent_spaces)
        toc_lines.append(f"{indent}{bullet_char} [{h.title}](#{h.slug})")

    return "\n".join(toc_lines)


def extract_outline(content: str) -> list[HeadingNode]:
    """Extract hierarchical heading outline tree from markdown content."""
    headings = parse_headings(content)
    if not headings:
        return []

    root_nodes: list[HeadingNode] = []
    stack: list[HeadingNode] = []

    for h in headings:
        node = HeadingNode(
            level=h.level,
            title=h.title,
            slug=h.slug,
            line_number=h.line_number,
        )
        while stack and stack[-1].level >= node.level:
            stack.pop()

        if stack:
            stack[-1].children.append(node)
        else:
            root_nodes.append(node)
        stack.append(node)

    return root_nodes


class MarkdownTools(Extension):
    """Markdown table formatter, TOC generator, and document outline parser."""

    def __init__(self, api: ExtensionsAPI) -> None:
        super().__init__(api)
        self.api = api

    def _get_active_editor_text(self) -> tuple[Any, str]:
        editor = getattr(getattr(self.api, "editors", None), "active_editor", None)
        if not editor:
            return None, ""
        text_widget = getattr(editor, "text", None) or getattr(getattr(editor, "content", None), "text", None)
        if not text_widget or not hasattr(text_widget, "get"):
            return None, ""
        try:
            content = text_widget.get("1.0", "end-1c")
            return text_widget, content
        except Exception:
            return text_widget, ""

    def _set_active_editor_text(self, text_widget: Any, new_content: str) -> None:
        if text_widget and hasattr(text_widget, "delete") and hasattr(text_widget, "insert"):
            try:
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", new_content)
            except Exception:
                pass

    def format_table(self, text: str | None = None) -> str:
        """Format markdown tables in provided text or active editor."""
        if text is not None:
            return format_table(text)

        text_widget, content = self._get_active_editor_text()
        if content:
            formatted = format_tables_in_markdown(content)
            self._set_active_editor_text(text_widget, formatted)
            if hasattr(self.api, "notifications") and self.api.notifications:
                self.api.notifications.info("Markdown tables formatted.")
            return formatted
        return ""

    def generate_toc(
        self,
        content: str | None = None,
        max_depth: int = 6,
        min_depth: int = 1,
    ) -> str:
        """Generate Table of Contents from content or active editor."""
        if content is None:
            _, doc_text = self._get_active_editor_text()
            content = doc_text

        toc = generate_toc(content, max_depth=max_depth, min_depth=min_depth)
        if toc and hasattr(self.api, "notifications") and self.api.notifications:
            self.api.notifications.info("Table of Contents generated.")
        return toc

    def extract_outline(self, content: str | None = None) -> list[HeadingNode]:
        """Extract hierarchical heading outline from content or active editor."""
        if content is None:
            _, doc_text = self._get_active_editor_text()
            content = doc_text
        return extract_outline(content)

    def insert_link(self, title: str = "Link", url: str = "https://") -> str:
        """Generate or insert markdown link [title](url)."""
        link = f"[{title}]({url})"
        text_widget, _ = self._get_active_editor_text()
        if text_widget and hasattr(text_widget, "insert"):
            try:
                text_widget.insert("insert", link)
            except Exception:
                pass
        return link

    def install(self) -> None:
        """Register commands for Markdown Tools."""
        if hasattr(self.api, "commands") and hasattr(self.api.commands, "register_command"):
            self.api.commands.register_command("markdown.format_table", self.format_table)
            self.api.commands.register_command("markdown.generate_toc", self.generate_toc)
            self.api.commands.register_command("markdown.extract_outline", self.extract_outline)
            self.api.commands.register_command("markdown.insert_link", self.insert_link)

        if hasattr(self.api, "logger") and self.api.logger:
            self.api.logger.info("Markdown Tools extension installed.")
