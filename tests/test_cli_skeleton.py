"""Smoke tests for the CLI skeleton itself - subparser wiring, dispatch.
Each command group's real logic is tested in its own test module as it's
ported; this file only checks the CLI plumbing stays correct.
"""
import pytest

from slackbackup.cli import build_parser


@pytest.mark.parametrize(
    "argv",
    [
        ["workspace", "register", "f3test", "xoxd-cookie"],
        ["workspace", "list"],
        ["channel", "register", "f3test", "general"],
        ["channel", "list", "f3test"],
        ["channel", "validate", "channels.json"],
        ["catalog", "show", "f3test"],
        ["backup", "channel", "C1", "general", "f3test", "/tmp/archive"],
        ["backup", "run", "channels.json", "/tmp/archive"],
        ["export", "monthly", "--from", "2026-01-01", "--to", "2026-01-31",
         "--workspace", "f3test", "--channel", "general",
         "--archive-root", "/tmp/archive", "--out", "/tmp/out"],
        ["files", "fetch", "/tmp/search-root"],
        ["files", "index", "/tmp/out", "/tmp/index.json",
         "--archive-root", "/tmp/archive", "--search-root", "/tmp/search"],
        ["search", "messages", "convergence"],
    ],
)
def test_every_documented_command_parses_and_dispatches(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    assert callable(args.handler)


def test_unknown_group_is_rejected():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus-group"])


def test_missing_required_subcommand_is_rejected():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["workspace"])
