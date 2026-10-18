"""Command-line entry point for the implemented planning stages."""

import argparse
import json
from pathlib import Path


def main() -> int:
    """Display help or explicitly generate Stage 1 from preserved local evidence."""
    parser = argparse.ArgumentParser(
        prog="event-coordination",
        description=(
            "Event Planning & Coordination Brief. "
            "Generate evidence-backed planning drafts. Stage 1 or isolated Stages 01–09."
        ),
    )
    commands = parser.add_subparsers(dest="command")
    stage = commands.add_parser("stage1", help="Generate and validate the Stage 1 snapshot")
    stage.add_argument("--project-root", type=Path, default=Path.cwd())
    stage.add_argument("--run-id", help="Run identifier to retain for later stages")
    run = commands.add_parser("run-stages", help="Run Stages 01–09 from registered local evidence in a new workspace")
    run.add_argument("--source-root", type=Path, required=True)
    run.add_argument("--workspace", type=Path, required=True, help="Absent directory outside the source project; existing parent required")
    run.add_argument("--through-stage", type=int, choices=(8, 9), default=9, help="Final stage; defaults to 9")
    execute = commands.add_parser("execute", help="Managed Stages 01–09 with semantic changes, history and recovery")
    execute.add_argument("--source-root", type=Path, required=True)
    execute.add_argument("--workspace", type=Path, required=True)
    execute.add_argument("--recover", action="store_true", help="Explicitly recover incomplete/corrupt managed outputs")
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "execute":
        from event_coordination.execution import execute
        try:
            report = execute(args.source_root, args.workspace, recover=args.recover)
        except (OSError, ValueError, KeyError):
            parser.exit(1, "Managed execution failed. Inspect deliverables/failure.json and preserved attempts; unsafe workspace failures may prevent a receipt.\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-stages":
        from event_coordination.pipeline import run_stages
        try:
            report = run_stages(args.source_root, args.workspace, args.through_stage)
        except (OSError, ValueError, KeyError, StopIteration):
            parser.exit(1, "Stages 01–09 failed; no success is claimed. Preserve any workspace for review.\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
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
