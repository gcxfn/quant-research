from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='quant')
    parser.add_argument('--version', action='store_true')
    args = parser.parse_args(argv)
    if args.version:
        from quant import __version__

        print(json.dumps({'version': __version__}))
        return 0
    parser.print_usage(sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
