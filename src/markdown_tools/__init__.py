from __future__ import annotations

import typing

from .extension import MarkdownTools

if typing.TYPE_CHECKING:
    from biscuit.api import ExtensionsAPI


def setup(api: "ExtensionsAPI") -> MarkdownTools:
    """Entrypoint for Biscuit to load the extension."""
    ext = MarkdownTools(api)
    api.register("markdown_tools", ext)
    return ext
