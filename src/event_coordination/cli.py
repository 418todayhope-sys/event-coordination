"""Command-line entry point for the implemented planning stages."""

import argparse
from pathlib import Path


def main() -> int:
    """Display help or explicitly generate Stage 1 from preserved local evidence."""
    parser = argparse.ArgumentParser(
        prog="event-coordination",
        description=(
            "Event Planning & Coordination Brief. "
            "Generate evidence-backed planning drafts. Only Stage 1 is implemented."
        ),
    )
    commands = parser.add_subparsers(dest="command")
    stage = commands.add_parser("stage1", help="Generate and validate the Stage 1 snapshot")
    stage.add_argument("--project-root", type=Path, default=Path.cwd())
    stage.add_argument("--run-id", help="Run identifier to retain for later stages")
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0
    from event_coordination.stages.scope import write_snapshot
    from jsonschema import ValidationError
    try:
        path, digest = write_snapshot(args.project_root.resolve(), args.run_id)
    except (OSError, ValueError, ValidationError) as exc:
        parser.exit(1, f"Stage 1 failed: {exc}\n")
    print(f"Validated Stage 1 draft: {path}\n{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
