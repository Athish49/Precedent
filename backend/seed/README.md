# Seed

Everything to do with seeding lives in this folder and nowhere else: the code that validates, loads and reports on seed content, the content files themselves, and the tests for that code.

**The application does not need this folder.** With `backend/seed/` deleted the application still starts, migrates, passes its test suite and serves every feature. Seed data is demonstration and company content. Reference data the application needs in order to run (agreement types, clause families and their heading synonyms) comes from migrations, not from here.

## Layout

```text
backend/seed/
  README.md
  common/        shared helpers for seed code only: YAML loading, DB session, CLI wrapper
  playbooks/     category: playbooks. Models, validator, loader, report; content in data/halcyon/
  contracts/     category: synthetic contracts. Generator; content in data/halcyon/
  history/       category: negotiation history. Models, loader; content in data/halcyon/
  tests/         tests for seed code only
```

Each category has the same shape: code at the top, content under `data/<dataset>/`. A new category is added as another sub-folder beside the existing ones.

## Isolation rules

1. **Dependencies run one way.** Seed code may import from `app` (models, repositories, settings). Nothing under `backend/app/`, `backend/migrations/`, `backend/scripts/` or `backend/tests/` may import from `seed`, read a file under it, or call one of its commands.
2. **Seed code stays here.** No seed loader, validator, report, model or seed test anywhere else.
3. **Seed tests stay in `seed/tests/`.** They are not in the application's `testpaths` and run with their own command. The application suite must pass with this folder absent.
4. **Seed-only dependencies** go in the `seed` dependency group in `backend/pyproject.toml`, not in the application's dependencies. `pyyaml` is the first.
5. **Reference data is not seed data.** Anything the application needs in order to run is inserted by a migration.
6. **The application works with no seed data loaded.** Empty playbook, role and policy tables are a valid state.
7. **Application features are not seed.** The playbook bootstrap, the rule test runner and the publish flow live in `app` and never read files from this folder.
8. **A guard enforces rule 1:** `backend/tests/unit/test_seed_isolation.py` in the application suite, and the "Guard — nothing outside seed/ uses seed/" step in `.github/workflows/ci.yml`.

Other rules that apply to seed code:

- Files in this folder are source kept in git. Anything generated from them at run time goes to the database or the bucket, not to disk.
- Loaders write only inside the project namespace. `seed.common.seed_session` calls the application's `assert_namespace` guard before yielding a session, once the application has one.
- Do not run a loader against the remote database without the owner's go-ahead. Use `--dry-run` first.
- Content is synthetic. Halcyon Care is fictional.

## Setup

Run everything from `backend/`, in the application's environment.

```bash
cd backend
uv sync --group seed          # or: .venv/bin/python -m pip install "pyyaml>=6.0"
```

## Tests

```bash
cd backend
.venv/bin/python -m pytest seed/tests -q
```

This suite is separate from the application suite (`pytest -q`, which collects only `tests/`). `seed/tests/conftest.py` sets placeholder settings so no test can reach the real database or bucket, and makes an empty suite exit 0 instead of pytest's default status 5.

## Categories

Every command accepts `--dry-run`, which does everything except commit.

### `playbooks/`

The company's playbook content: taxonomy (clause issues), authority (context dimensions, approver roles, escalation policies, global red lines), playbooks, rules with their positions, parameters, red lines, objections, dependencies and test cases, and later versions.

| Command | What it does | Added by |
|---|---|---|
| `python -m seed.playbooks.validate [dir]` | Validates every file and runs the cross-checks. No database. | task 0.2 |
| `python -m seed.playbooks.load [dir] [--dry-run] [--only KEY ...]` | Loads the content into the database: issues, context dimensions, roles, escalation policies, global red lines, then each playbook (its own transaction, rolled back and reported on error) and its versions, rules and children. Archives any playbook in the database whose key is no longer in the directory. `--dry-run` reads and validates only; it never opens a database connection. `--only` limits which playbook(s) are written. | task 2.1 |
| `python -m seed.playbooks.report` | Prints the coverage report against the content quotas. | task 2.2 |

Content: `playbooks/data/halcyon/`. Default `dir` is that folder.

### `contracts/`

Synthetic contracts used to exercise review end to end, with the expected findings for each.

| Command | What it does | Added by |
|---|---|---|
| `python -m seed.contracts.build [--dry-run]` | Builds the contract files from their sources. | task 5.2 |

Content: `contracts/data/halcyon/` (`source/`, `docx/`, `expected.yaml`).

### `history/`

Synthetic negotiation history: past decisions on rules, which feed the outcome data.

| Command | What it does | Added by |
|---|---|---|
| `python -m seed.history.load [--dry-run]` | Loads the decisions into the database. | task 5.3 |

Content: `history/data/halcyon/decisions.yaml`.

## Shared helpers: `seed.common`

Importing `seed.common` does not import `app` and needs no environment variable, so validators run without any configuration. Only `seed_session` reads application settings, when it is called.

```python
from seed.common import (
    SEED_ROOT, data_dir,                               # paths
    load_yaml, load_yaml_mapping, iter_yaml_files,     # YAML
    seed_session, call_namespace_guard,                # database
    build_parser, add_data_dir_argument, run,          # command line
    SeedError, SeedFileError,                          # errors
)
```

| Helper | Signature | Notes |
|---|---|---|
| `SEED_ROOT` | `Path` | The `backend/seed` folder. |
| `data_dir` | `data_dir(category: str, dataset: str = "halcyon") -> Path` | `seed/<category>/data/<dataset>`. Does not check existence. |
| `load_yaml` | `load_yaml(path: Path \| str) -> Any` | Safe load; rejects duplicate mapping keys; `None` for an empty file. Raises `SeedFileError`. |
| `load_yaml_mapping` | `load_yaml_mapping(path: Path \| str) -> dict[str, Any]` | As above, and the top level must be a mapping with string keys. |
| `iter_yaml_files` | `iter_yaml_files(root: Path \| str, *, recursive: bool = True) -> Iterator[Path]` | Sorted `.yaml` and `.yml` files. |
| `seed_session` | `seed_session(*, dry_run: bool = False)` async context manager yielding `AsyncSession` | Calls the namespace guard, commits on clean exit, rolls back on `dry_run` or an exception. |
| `call_namespace_guard` | `async call_namespace_guard(session: AsyncSession) -> bool` | `False` when the application has no guard yet. |
| `build_parser` | `build_parser(description: str, *, prog: str \| None = None) -> argparse.ArgumentParser` | Has `--dry-run` (`args.dry_run`). |
| `add_data_dir_argument` | `add_data_dir_argument(parser, default: Path \| str) -> None` | Optional positional `data_dir` (`args.data_dir`). |
| `run` | `run(handler, parser, argv: Sequence[str] \| None = None) -> int` | `handler(args)` may be sync or async; `SeedError` becomes exit status 1. |

A command module looks like this:

```python
from seed.common import add_data_dir_argument, build_parser, data_dir, run, seed_session


async def _main(args) -> int:
    async with seed_session(dry_run=args.dry_run) as session:
        ...
    return 0


def main(argv=None) -> int:
    parser = build_parser("Load the playbook seed.", prog="python -m seed.playbooks.load")
    add_data_dir_argument(parser, data_dir("playbooks"))
    return run(_main, parser, argv)


if __name__ == "__main__":
    raise SystemExit(main())
```

## Removing this folder

Delete `backend/seed/` and the `seed` group in `backend/pyproject.toml`. Nothing else refers to it: the CI step that runs the seed tests is skipped when the folder is absent, and the isolation guard passes without it.
