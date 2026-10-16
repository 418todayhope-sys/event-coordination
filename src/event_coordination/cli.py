"""Help-only command-line entry point for the project foundation."""

import argparse


def main() -> int:
    """Display usage without executing a planning workflow."""
    parser = argparse.ArgumentParser(
        prog="event-coordination",
        description=(
            "Event Planning & Coordination Brief. "
            "This foundation provides help only; planning commands are not yet implemented."
        ),
    )
    parser.parse_args()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
