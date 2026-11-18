"""Command-line wrapper shared by seed commands.

Typical use in ``seed/<category>/<command>.py``::

    from seed.common import add_data_dir_argument, build_parser, data_dir, run

    async def _main(args):
        ...
        return 0

    def main(argv=None):
        parser = build_parser("Load the playbook seed.", prog="python -m seed.playbooks.load")
        add_data_dir_argument(parser, data_dir("playbooks"))
        return run(_main, parser, argv)

    if __name__ == "__main__":
        raise SystemExit(main())
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from seed.common.errors import SeedError

Handler = Callable[[argparse.Namespace], "int | None | Awaitable[int | None]"]


def build_parser(description: str, *, prog: str | None = None) -> argparse.ArgumentParser:
    """Return a parser that already has ``--dry-run`` (``args.dry_run``, default False)."""
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do everything except commit: report what would change and write nothing",
    )
    return parser


def add_data_dir_argument(parser: argparse.ArgumentParser, default: Path | str) -> None:
    """Add the optional positional ``data_dir`` argument (``args.data_dir``, a ``Path``)."""
    default_path = Path(default)
    parser.add_argument(
        "data_dir",
        nargs="?",
        type=Path,
        default=default_path,
        help=f"folder of seed files (default: {default_path})",
    )


def run(
    handler: Handler,
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None = None,
) -> int:
    """Parse ``argv``, call ``handler(args)`` and return a process exit status.

    ``handler`` may be a plain or an async function. Its return value is the
    exit status; ``None`` means 0. A :class:`SeedError` is printed to stderr
    and becomes status 1. Other exceptions propagate with their traceback.
    """
    args = parser.parse_args(argv)
    try:
        result = handler(args)
        if inspect.isawaitable(result):
            result = asyncio.run(_await(result))
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return int(result or 0)


async def _await(awaitable: Awaitable[int | None]) -> int | None:
    return await awaitable
