#!/usr/bin/env python3
"""Installed project entrypoint; only local managed draft execution, no approvals."""
import sys
from event_coordination.cli import main

if __name__ == '__main__':
    sys.argv.insert(1, 'execute')
    raise SystemExit(main())
