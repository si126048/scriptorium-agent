import argparse
import json
import sys
from pathlib import Path


def configuration(host: str, workspace: str, python: str | None = None):
    command = python or sys.executable
    root = str(Path(workspace).resolve(strict=True))
    args = ["-m", "scriptorium.plugin", "mcp", "--workspace", root]
    server = {"command": command, "args": args}
    if host == "codex":
        return (
            "[mcp_servers.scriptorium]\ncommand = "
            + json.dumps(command)
            + "\nargs = "
            + json.dumps(args)
            + "\n"
        )
    if host == "zed":
        return {
            "agent_servers": {
                "Scriptorium": {
                    "type": "custom",
                    "command": command,
                    "args": ["-m", "scriptorium.plugin", "acp", "--workspace", root],
                }
            }
        }
    if host == "dsh":
        return [
            {
                "id": "mcp-scriptorium",
                "name": "@deepseek-ai/dsh-mcp-client",
                "config": {
                    "serverName": "scriptorium",
                    "transport": "stdio",
                    **server,
                    "cwd": root,
                    "failOnStartupError": True,
                },
            }
        ]
    if host == "vscode":
        return {"servers": {"scriptorium": {"type": "stdio", **server}}}
    return {"mcpServers": {"scriptorium": server}}


def serve(kind, argv=None):
    parser = argparse.ArgumentParser(description=f"Scriptorium {kind.upper()} research plugin")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    parser.add_argument(
        "--database",
        help="Optional explicit SQLite store; never points at the desktop database automatically",
    )
    args = parser.parse_args(argv)
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if kind == "mcp":
        from .mcp import create_server

        server, tools = create_server(args.workspace, args.database)
        try:
            server.run(transport="stdio")
        finally:
            tools.close()
    else:
        from .acp import ContextAgent

        ContextAgent(args.workspace, args.database).run()


def main():
    if len(sys.argv) > 1 and sys.argv[1] in {"mcp", "acp"}:
        serve(sys.argv[1], sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description="Scriptorium headless research plugin")
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser(
        "config", help="Print a host configuration fragment; does not edit host settings"
    )
    config.add_argument(
        "--host",
        required=True,
        choices=["codex", "cursor", "claude", "qoder", "vscode", "zed", "dsh"],
    )
    config.add_argument("--workspace", default=str(Path.cwd()))
    config.add_argument("--python")
    commands.add_parser(
        "doctor", help="Check the local plugin without model calls or desktop startup"
    )
    args = parser.parse_args()
    if args.command == "config":
        value = configuration(args.host, args.workspace, args.python)
        print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
    else:
        from importlib.util import find_spec

        from .. import __version__

        print(
            json.dumps(
                {
                    "version": __version__,
                    "mcp_available": find_spec("mcp") is not None,
                    "transports": ["mcp-stdio", "acp-v1-stdio-context"],
                    "model_mode": "host",
                    "requires": ["Python 3.12+"],
                    "desktop_required": False,
                    "postgres_required": False,
                    "automatic_model_calls": False,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
