"""Helpers for the fixed three-level Pricing category hierarchy."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


MAX_CATEGORY_DEPTH = 2


def category_ancestry(category: Any | None) -> list[Any]:
    """Return the category path from its Main Category to the selected folder."""
    path: list[Any] = []
    seen: set[int] = set()
    current = category
    while current is not None:
        identity = getattr(current, "id", None)
        marker = identity if identity is not None else id(current)
        if marker in seen:
            break
        seen.add(marker)
        path.append(current)
        current = getattr(current, "parent", None)
    path.reverse()
    return path


def category_depth(category: Any | None) -> int:
    return max(0, len(category_ancestry(category)) - 1)


def category_path_label(category: Any | None, separator: str = " / ") -> str:
    return separator.join(str(entry.name) for entry in category_ancestry(category))


def category_descendants(category: Any) -> list[Any]:
    descendants: list[Any] = []
    pending = list(getattr(category, "children", ()) or ())
    seen: set[int] = set()
    while pending:
        entry = pending.pop(0)
        identity = getattr(entry, "id", None)
        marker = identity if identity is not None else id(entry)
        if marker in seen:
            continue
        seen.add(marker)
        descendants.append(entry)
        pending.extend(list(getattr(entry, "children", ()) or ()))
    return descendants


def category_subtree_height(category: Any) -> int:
    children = list(getattr(category, "children", ()) or ())
    if not children:
        return 0
    return 1 + max(category_subtree_height(child) for child in children)


def category_root(category: Any | None) -> Any | None:
    path = category_ancestry(category)
    return path[0] if path else None


def category_tree(categories: Iterable[Any]) -> list[dict[str, Any]]:
    """Create a sorted JSON-safe tree for browser folder pickers."""
    nodes = {
        entry.id: {
            "id": entry.id,
            "name": entry.name,
            "label": category_path_label(entry),
            "parent_id": entry.parent_id,
            "depth": category_depth(entry),
            "children": [],
        }
        for entry in categories
    }
    roots: list[dict[str, Any]] = []
    for entry in categories:
        node = nodes[entry.id]
        parent = nodes.get(entry.parent_id)
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)

    def sort_nodes(entries: list[dict[str, Any]]) -> None:
        entries.sort(key=lambda node: node["name"].casefold())
        for node in entries:
            sort_nodes(node["children"])

    sort_nodes(roots)
    return roots


def flatten_category_tree(roots: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    pending = list(roots)
    while pending:
        node = pending.pop(0)
        result.append(node)
        pending[0:0] = node.get("children", [])
    return result
