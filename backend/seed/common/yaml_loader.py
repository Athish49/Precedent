"""YAML loading for seed content files.

Stricter than ``yaml.safe_load``: a mapping with the same key twice is an
error, because a silently dropped duplicate is the easiest mistake to make in
a long hand-written rules file.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterator
from pathlib import Path
from typing import Any

import yaml

from seed.common.errors import SeedFileError

YAML_SUFFIXES = (".yaml", ".yml")


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        seen: set[Hashable] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=True)
            try:
                duplicate = key in seen
            except TypeError:
                continue  # unhashable key; SafeLoader reports it below
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(path: Path | str) -> Any:
    """Parse one YAML file and return its content.

    Returns ``None`` for an empty file. Unquoted ISO dates come back as
    ``datetime.date``. Raises :class:`SeedFileError` if the file is missing,
    is not valid UTF-8, is not valid YAML, or repeats a mapping key.
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SeedFileError(file_path, "file not found") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise SeedFileError(file_path, f"cannot read file: {exc}") from exc
    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise SeedFileError(file_path, f"invalid YAML: {exc}") from exc


def load_yaml_mapping(path: Path | str) -> dict[str, Any]:
    """Parse one YAML file whose top level must be a mapping with string keys."""
    data = load_yaml(path)
    if not isinstance(data, dict):
        found = "an empty file" if data is None else type(data).__name__
        raise SeedFileError(path, f"top level must be a mapping, found {found}")
    for key in data:
        if not isinstance(key, str):
            raise SeedFileError(path, f"top-level key {key!r} is not a string")
    return data


def iter_yaml_files(root: Path | str, *, recursive: bool = True) -> Iterator[Path]:
    """Yield the ``.yaml`` and ``.yml`` files under ``root`` in sorted order.

    Raises :class:`SeedFileError` if ``root`` is not a directory.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        raise SeedFileError(root_path, "directory not found")
    candidates = root_path.rglob("*") if recursive else root_path.iterdir()
    yield from sorted(p for p in candidates if p.is_file() and p.suffix in YAML_SUFFIXES)
