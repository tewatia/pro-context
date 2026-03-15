"""CLI entrypoint for ProContext — argparse dispatcher."""

from __future__ import annotations

import argparse
import asyncio
import sys

from pydantic import ValidationError

from procontext.config import Settings
from procontext.logging_config import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="procontext",
        description="MCP server for accurate, up-to-date library documentation.",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("setup", help="Download the library registry")
    doctor_parser = sub.add_parser("doctor", help="Run system health checks")
    doctor_parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to auto-repair detected issues",
    )
    db_parser = sub.add_parser("db", help="Cache database maintenance commands")
    db_sub = db_parser.add_subparsers(dest="db_command")
    db_sub.required = True
    db_sub.add_parser("recreate", help="Delete and recreate the cache database")

    args = parser.parse_args()

    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)  # noqa: T201
        sys.exit(1)

    setup_logging(settings)

    # Deferred imports: each command module pulls in different heavy
    # dependencies (MCP SDK, aiosqlite, httpx).  Importing only the
    # selected command keeps CLI startup fast.
    if args.command == "setup":
        from procontext.cli.cmd_setup import run_setup

        asyncio.run(run_setup(settings))
    elif args.command == "doctor":
        from procontext.cli.cmd_doctor import run_doctor

        asyncio.run(run_doctor(settings, fix=args.fix))
    elif args.command == "db":
        if args.db_command == "recreate":
            from procontext.cli.cmd_db import run_db_recreate

            asyncio.run(run_db_recreate(settings))
    else:
        from procontext.cli.cmd_serve import run_server

        run_server(settings)


if __name__ == "__main__":
    main()
