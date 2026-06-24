#!/usr/bin/env python3
"""Argparse-based CLI entry point: `slackbackup <group> <command> ...`.

Each subcommand group lives in its own module (workspace, channel, catalog,
backup, export, files, search). This file only wires argparse subparsers to
those modules' `register(subparsers)` / handler functions - it holds no
business logic itself.
"""
import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slackbackup")
    groups = parser.add_subparsers(dest="group", required=True)

    from . import backup, catalog, channel, export, files, search, workspace

    for module in (workspace, channel, catalog, backup, export, files, search):
        module.register(groups)

    help_parser = groups.add_parser("help", help="list every command with a brief description")
    help_parser.set_defaults(handler=lambda args: _print_help(parser))

    return parser


def iter_commands(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()):
    """Walks the argparse subparser tree, yielding (("group", "command"),
    help_text) for every leaf command. Auto-generated from whatever
    register() calls actually wired up, so it can't drift out of sync with
    the real command set."""
    subparsers_action = next(
        (a for a in parser._subparsers._group_actions if isinstance(a, argparse._SubParsersAction)),
        None,
    ) if parser._subparsers else None
    if subparsers_action is None:
        return

    for choice_action in subparsers_action._choices_actions:
        name = choice_action.dest
        subparser = subparsers_action.choices[name]
        new_prefix = prefix + (name,)
        if subparser._subparsers:
            yield from iter_commands(subparser, new_prefix)
        else:
            yield new_prefix, (choice_action.help or "")


def _print_help(root_parser: argparse.ArgumentParser) -> int:
    print("slackbackup commands:\n")
    rows = list(iter_commands(root_parser))
    width = max(len(" ".join(path)) for path, _ in rows)
    for path, help_text in rows:
        print(f"  {' '.join(path):<{width}}  {help_text}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
