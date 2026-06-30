"""Command-line interface for git-undigest.

Commands:
    git-undigest DIGEST [OUTPUT]      Reconstruct a repository.
    git-undigest validate DIGEST      Validate a digest without writing.
    git-undigest inspect DIGEST       Show a human summary of the digest.
    git-undigest list DIGEST          List all files in the digest.
    git-undigest stats DIGEST         Show numeric statistics.
"""

from __future__ import annotations

import argparse
import sys

from . import inspect as inspect_api
from . import list_files as list_files_api
from . import reconstruct as reconstruct_api
from . import stats as stats_api
from . import validate as validate_api
from .exceptions import GitUndigestError
from .models import ReconstructionResult
from .utils import human_size


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-undigest",
        description=(
            "Reconstruct a full repository from a GitIngest-style digest " "file."
        ),
    )
    parser.add_argument("--version", action="version", version=_version_string())

    subparsers = parser.add_subparsers(dest="command")

    def add_common_overwrite_flags(sp: argparse.ArgumentParser) -> None:
        group = sp.add_mutually_exclusive_group()
        group.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing files instead of erroring.",
        )
        group.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip files that already exist instead of erroring.",
        )
        sp.add_argument(
            "--backup",
            action="store_true",
            help="Back up existing files to '<name>.bak' before writing.",
        )
        sp.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without writing anything.",
        )
        sp.add_argument(
            "--force",
            action="store_true",
            help="Alias for --overwrite.",
        )
        verbosity = sp.add_mutually_exclusive_group()
        verbosity.add_argument(
            "--verbose", action="store_true", help="Print detailed per-file output."
        )
        verbosity.add_argument(
            "--quiet", action="store_true", help="Suppress non-essential output."
        )

    # Default reconstruction: `git-undigest digest.txt [output]`
    recon = subparsers.add_parser(
        "reconstruct", help="Reconstruct a repository from a digest (default command)."
    )
    recon.add_argument("digest", help="Path to the digest file.")
    recon.add_argument(
        "output",
        nargs="?",
        default="output",
        help="Output directory (default: output).",
    )
    add_common_overwrite_flags(recon)

    validate_p = subparsers.add_parser("validate", help="Validate a digest file.")
    validate_p.add_argument("digest", help="Path to the digest file.")

    inspect_p = subparsers.add_parser(
        "inspect", help="Show repository name, languages, tree, and largest files."
    )
    inspect_p.add_argument("digest", help="Path to the digest file.")

    list_p = subparsers.add_parser("list", help="List every file in the digest.")
    list_p.add_argument("digest", help="Path to the digest file.")

    stats_p = subparsers.add_parser(
        "stats", help="Show numeric statistics about a digest."
    )
    stats_p.add_argument("digest", help="Path to the digest file.")

    return parser


def _version_string() -> str:
    from . import __version__

    return f"git-undigest {__version__}"


def _print_reconstruction_result(
    result: ReconstructionResult, *, verbose: bool, quiet: bool
) -> None:
    if quiet:
        return

    if verbose:
        for r in result.results:
            label = {
                "created": "CREATE",
                "would_create": "WOULD CREATE",
                "overwritten": "OVERWRITE",
                "would_overwrite": "WOULD OVERWRITE",
                "skipped": "SKIP",
                "backed_up": "BACKUP",
            }.get(r.action, r.action.upper())
            print(f"  [{label}] {r.path}")

    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)

    prefix = "Would write" if result.dry_run else "Wrote"
    print(
        f"{prefix} {len(result.created)} created, "
        f"{len(result.overwritten)} overwritten, "
        f"{len(result.skipped)} skipped, "
        f"{len(result.backed_up)} backed up "
        f"({human_size(result.total_bytes_written)}) to {result.output_dir}"
    )


def _cmd_reconstruct(args: argparse.Namespace) -> int:
    result = reconstruct_api(
        args.digest,
        args.output,
        overwrite=args.overwrite or args.force,
        skip_existing=args.skip_existing,
        backup=args.backup,
        dry_run=args.dry_run,
    )
    _print_reconstruction_result(result, verbose=args.verbose, quiet=args.quiet)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    summary = validate_api(args.digest)
    print(f"OK: digest is valid ({summary.file_count} files).")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    info = inspect_api(args.digest)
    print(f"Repository: {info['repo_name']}")
    print(f"Files: {info['file_count']}")
    if info["languages"]:
        print("Languages:")
        for lang, count in info["languages"].items():
            print(f"  {lang}: {count}")
    if info["largest_files"]:
        print("Largest files:")
        for path, size in info["largest_files"]:
            print(f"  {human_size(size):>10}  {path}")
    print("Directory tree:")
    print(info["tree"])
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    for path in list_files_api(args.digest):
        print(path)
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    s = stats_api(args.digest)
    print(f"Files:            {s.file_count}")
    print(f"Folders:          {s.folder_count}")
    print(f"Total size:       {human_size(s.total_bytes)}")
    if s.largest_file:
        print(f"Largest file:     {s.largest_file} ({human_size(s.largest_file_size)})")
    print(f"Average size:     {human_size(s.average_file_size)}")
    print(f"Estimated tokens: {s.estimated_tokens:,}")
    if s.extension_counts:
        print("Extensions:")
        for ext, count in s.extension_counts.items():
            print(f"  .{ext}: {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``git-undigest`` console script.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 on success, 1 on a handled error, 2 on
        argument-parsing errors (raised by argparse itself).
    """
    raw_args = sys.argv[1:] if argv is None else argv

    # Support the bare `git-undigest digest.txt [output]` form by
    # injecting the implicit "reconstruct" subcommand when the first
    # token isn't a known subcommand or flag.
    known_commands = {"reconstruct", "validate", "inspect", "list", "stats"}
    args_to_parse = list(raw_args)
    if (
        args_to_parse
        and args_to_parse[0] not in known_commands
        and not args_to_parse[0].startswith("-")
    ):
        args_to_parse = ["reconstruct", *args_to_parse]
    elif not args_to_parse:
        args_to_parse = ["--help"]

    parser = _build_parser()
    args = parser.parse_args(args_to_parse)

    if args.command is None:
        parser.print_help()
        return 0

    handlers = {
        "reconstruct": _cmd_reconstruct,
        "validate": _cmd_validate,
        "inspect": _cmd_inspect,
        "list": _cmd_list,
        "stats": _cmd_stats,
    }

    try:
        return handlers[args.command](args)
    except GitUndigestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
