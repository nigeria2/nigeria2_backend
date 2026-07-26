#!/usr/bin/env python
"""DEPRECATED — superseded by scripts/penalties.py.

All penalty rules now live in one place (scripts/penalties.py) with a rule registry.
This shim forwards to it so old invocations keep working, running ONLY the original
rule (minor_party_over_2000) so it can never accidentally re-apply a different rule.

    python -m scripts.penalize_evidence --commit
      == python -m scripts.penalties --rules minor_party_over_2000 --commit
"""
import sys

from scripts.penalties import main as _main

if __name__ == "__main__":
    # force the single original rule regardless of args (drop any --rules the caller passed)
    argv = [a for a in sys.argv[1:] if not a.startswith("--rules")]
    # crude: also drop a following value if --rules was given as two tokens
    sys.argv = [sys.argv[0], "--rules", "minor_party_over_2000", *argv]
    _main()
