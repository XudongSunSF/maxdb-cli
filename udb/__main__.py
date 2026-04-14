"""Entry point: python -m udb [binary] [options]"""

import argparse
import sys

from .cli import UDBCli
from .config import Config


def main():
    parser = argparse.ArgumentParser(
        prog="udb",
        description="UDB — Time-Travel Debugger for C++ powered by Claude AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  udb ./my_binary
  udb ./my_binary --rr
  udb ./my_binary --api-key sk-ant-...
  python -m udb ./my_binary

Environment variables:
  ANTHROPIC_API_KEY   Anthropic API key for 'explain' / 'why' command
  UDB_USE_RR          Set to 1 to use rr instead of GDB record-full
  UDB_CONTEXT_LINES   Number of source lines to show (default 10)
  UDB_DEBUG           Set to 1 for verbose GDB/MI output
""",
    )
    parser.add_argument("binary", nargs="?", help="C++ binary to debug")
    parser.add_argument("--rr", action="store_true", help="Use rr (record-and-replay) backend")
    parser.add_argument("--api-key", metavar="KEY", help="Anthropic API key")
    parser.add_argument("--context", type=int, default=10, metavar="N",
                        help="Source lines of context to show (default 10)")
    parser.add_argument("--debug", action="store_true", help="Show GDB/MI protocol traffic")
    parser.add_argument("--version", action="version", version="udb 1.0.0")

    args = parser.parse_args()

    config = Config.from_env()
    config.context_lines = args.context
    config.debug = args.debug or config.debug
    config.use_rr = args.rr or config.use_rr
    if args.api_key:
        config.anthropic_api_key = args.api_key

    cli = UDBCli(config)
    try:
        cli.run(program=args.binary, use_rr=config.use_rr)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
