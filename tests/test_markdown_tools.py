from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

# Fix sys.path to ensure module is importable from extension root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.markdown_tools import setup
from src.markdown_tools.extension import (
    HeadingNode,
    MarkdownTools,
    TableAlignment,
    extract_outline,
    format_table,
    format_tables_in_markdown,
    generate_toc,
    parse_alignment,
    parse_headings,
    slugify,
)


class TestMarkdownToolsManifest:
    def test_manifest_schema_and_dependencies(self) -> None:
        manifest_path = Path(__file__).parent.parent / "extension.toml"
        assert manifest_path.exists(), "extension.toml must exist"
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))

        ext_meta = manifest.get("extension", {})
        assert ext_meta.get("id") == "markdown_tools"
        assert ext_meta.get("author") == "tomlin7"
        assert ext_meta.get("version") == "0.2.0"

        deps = manifest.get("dependencies", {})
        assert isinstance(deps.get("python"), list)
        assert isinstance(deps.get("tools"), list)

        contributes = manifest.get("contributes", {})
        commands = contributes.get("commands", [])
        assert len(commands) >= 4
        cmd_ids = [cmd["id"] for cmd in commands]
        assert "markdown.format_table" in cmd_ids
        assert "markdown.generate_toc" in cmd_ids
        assert "markdown.extract_outline" in cmd_ids
        assert "markdown.insert_link" in cmd_ids


class TestMarkdownToolsLogic:
    def test_setup_and_registration(self, app_instance) -> None:
        ext = setup(app_instance.api)
        assert ext is not None
        assert isinstance(ext, MarkdownTools)

    def test_parse_alignment(self) -> None:
        assert parse_alignment(":---") == TableAlignment.LEFT
        assert parse_alignment("---") == TableAlignment.LEFT
        assert parse_alignment("---:") == TableAlignment.RIGHT
        assert parse_alignment(":---:") == TableAlignment.CENTER
        assert parse_alignment(" :-: ") == TableAlignment.CENTER

    def test_format_table_alignment_and_padding(self) -> None:
        raw_table = """\
| Item | Price | Qty |
| :--- | :---: | ---: |
| Apple | $1.50 | 10 |
| Watermelon | $5.00 | 2 |
"""
        formatted = format_table(raw_table)
        lines = formatted.splitlines()
        assert len(lines) == 4
        assert lines[0].startswith("| Item")
        # Header column width padded to longest value (Watermelon = 10 chars)
        assert "Watermelon" in lines[3]
        assert ":---" in lines[1]
        assert "---:" in lines[1]
        assert ":---:" in lines[1]

    def test_format_table_uneven_columns(self) -> None:
        raw = """\
| Col1 | Col2 |
| --- | --- |
| Val1 |
| ValA | ValB | ValC |
"""
        formatted = format_table(raw)
        lines = formatted.splitlines()
        # All rows should have 3 columns padded
        for line in lines:
            assert line.count("|") == 4

    def test_format_tables_in_markdown(self) -> None:
        doc = """\
# Documentation

Here is a table:
| Name | Role |
| --- | --- |
| Alice | Admin |

Some explanation text.

```python
# Code block table should not be formatted
| Not | A | Real | Table |
```
"""
        result = format_tables_in_markdown(doc)
        assert "# Documentation" in result
        assert "| Alice | Admin |" in result or "| Alice" in result
        assert "```python\n# Code block table should not be formatted\n| Not | A | Real | Table |\n```" in result

    def test_slugify(self) -> None:
        assert slugify("Hello World") == "hello-world"
        assert slugify("Overview & Architecture!") == "overview-architecture"
        assert slugify("Using `print()` in Python") == "using-print-in-python"
        assert slugify("[Link Title](https://example.com)") == "link-title"
        assert slugify("  --- Multiple   Hyphens ---  ") == "multiple-hyphens"
        assert slugify("!!!") == "heading"

    def test_parse_headings_and_duplicate_slugs(self) -> None:
        doc = """\
# Introduction
## Overview
## Overview
### Details
"""
        headings = parse_headings(doc)
        assert len(headings) == 4
        assert headings[0].slug == "introduction"
        assert headings[1].slug == "overview"
        assert headings[2].slug == "overview-1"
        assert headings[3].slug == "details"

    def test_generate_toc_and_depth_filtering(self) -> None:
        doc = """\
# Title
## Section 1
### Subsection 1.1
#### Deep section
## Section 2
"""
        toc_all = generate_toc(doc, max_depth=6)
        assert "- [Title](#title)" in toc_all
        assert "  - [Section 1](#section-1)" in toc_all
        assert "    - [Subsection 1.1](#subsection-11)" in toc_all
        assert "      - [Deep section](#deep-section)" in toc_all

        toc_filtered = generate_toc(doc, max_depth=2, min_depth=2)
        assert "[Title]" not in toc_filtered
        assert "[Subsection 1.1]" not in toc_filtered
        assert "- [Section 1](#section-1)" in toc_filtered
        assert "- [Section 2](#section-2)" in toc_filtered

    def test_generate_toc_skips_code_blocks(self) -> None:
        doc = """\
# Real Heading
```python
# This is a python comment, not a markdown heading
def foo():
    pass
```
## Another Real Heading
"""
        toc = generate_toc(doc)
        assert "[Real Heading](#real-heading)" in toc
        assert "[Another Real Heading](#another-real-heading)" in toc
        assert "This is a python comment" not in toc

    def test_extract_outline(self) -> None:
        doc = """\
# Root 1
## Child 1.1
### Grandchild 1.1.1
## Child 1.2
# Root 2
"""
        outline = extract_outline(doc)
        assert len(outline) == 2
        assert outline[0].title == "Root 1"
        assert len(outline[0].children) == 2
        assert outline[0].children[0].title == "Child 1.1"
        assert len(outline[0].children[0].children) == 1
        assert outline[0].children[0].children[0].title == "Grandchild 1.1.1"
        assert outline[1].title == "Root 2"

        data = outline[0].to_dict()
        assert data["title"] == "Root 1"
        assert len(data["children"]) == 2

    def test_editor_actions(self, app_instance) -> None:
        ext = MarkdownTools(app_instance.api)
        ext.install()

        # Mock editor widget
        mock_text = MagicMock()
        mock_text.get.return_value = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        mock_editor = MagicMock()
        mock_editor.text = mock_text
        app_instance.api.editors.active_editor = mock_editor

        # Test format_table with editor
        formatted = ext.format_table()
        assert "| A   | B   |" in formatted
        mock_text.delete.assert_called_with("1.0", "end")
        mock_text.insert.assert_called()

        # Test generate_toc with editor
        mock_text.get.return_value = "# Header 1\n## Header 2"
        toc = ext.generate_toc()
        assert "- [Header 1](#header-1)" in toc

        # Test extract_outline with editor
        outline = ext.extract_outline()
        assert len(outline) == 1
        assert outline[0].title == "Header 1"

        # Test insert_link
        link = ext.insert_link("Guide", "https://docs.org")
        assert link == "[Guide](https://docs.org)"
        mock_text.insert.assert_called_with("insert", link)

    def test_empty_and_edge_inputs(self, app_instance) -> None:
        ext = MarkdownTools(app_instance.api)
        assert ext.format_table("") == ""
        assert ext.generate_toc("") == ""
        assert ext.extract_outline("") == []
        assert format_table("Single line not a table") == "Single line not a table"