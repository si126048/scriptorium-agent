"""ACP v1 context agent. No shell, implicit network, provider key or hidden inference."""

import json
import sys
import threading
import uuid
from pathlib import Path

from .. import __version__
from .core import ResearchTools


class PromptCancelled(Exception):
    pass


class ContextAgent:
    def __init__(self, workspace: str, database: str | None = None):
        self.root = Path(workspace).resolve(strict=True)
        self.database = database
        self.sessions = {}
        self.initialized = False
        self.output_lock = threading.Lock()

    def send(self, value):
        with self.output_lock:
            print(json.dumps(value, ensure_ascii=False), flush=True)

    def result(self, request_id, value):
        self.send({"jsonrpc": "2.0", "id": request_id, "result": value})

    def error(self, request_id, code, message):
        self.send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def update(self, sid, update):
        self.send(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"sessionId": sid, "update": update},
            }
        )

    def prompt(self, request_id, sid, blocks, session):
        reply = {"jsonrpc": "2.0", "id": request_id, "result": {"stopReason": "end_turn"}}
        try:
            texts = []
            for block in blocks:
                if session["cancel"].is_set():
                    raise PromptCancelled()
                if block.get("type") == "text":
                    texts.append(block["text"])
                elif block.get("type") == "resource" and isinstance(
                    block.get("resource", {}).get("text"), str
                ):
                    resource = block["resource"]
                    session["tools"].import_source(
                        resource["text"], resource.get("uri", "host-context")
                    )
                else:
                    raise ValueError("UNSUPPORTED_PROMPT_CONTENT")
            question = "\n".join(texts)
            if session["cancel"].is_set():
                raise PromptCancelled()
            tool_id = "prepare-" + uuid.uuid4().hex[:12]
            self.update(
                sid,
                {
                    "sessionUpdate": "tool_call",
                    "toolCallId": tool_id,
                    "title": "准备材料、引用与研究方法",
                    "kind": "search",
                    "status": "in_progress",
                },
            )
            context = session["tools"].prepare(question)
            if session["cancel"].is_set():
                self.update(
                    sid,
                    {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tool_id,
                        "status": "failed",
                    },
                )
                raise PromptCancelled()
            self.update(
                sid,
                {"sessionUpdate": "tool_call_update", "toolCallId": tool_id, "status": "completed"},
            )
            content = (
                "## 研究交接包\n\n当前为宿主推理模式：以下是材料与方法上下文，不是已完成的学术分析。"
                "\n\n```json\n" + json.dumps(context, ensure_ascii=False, indent=2) + "\n```"
            )
            self.update(
                sid,
                {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": content},
                },
            )
        except PromptCancelled:
            reply["result"]["stopReason"] = "cancelled"
        except (ValueError, KeyError, TypeError) as exc:
            reply = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": str(exc)[:200]},
            }
        except Exception:  # noqa: BLE001 -- isolate protocol requests without leaking internals
            reply = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": "RESEARCH_CONTEXT_FAILED"},
            }
        finally:
            session["busy"].release()
            self.send(reply)

    def dispatch(self, message):
        request_id, method = message.get("id"), message.get("method")
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise TypeError("PARAMS_MUST_BE_OBJECT")
        if method == "session/cancel":
            session = self.sessions.get(params.get("sessionId"))
            if session:
                session["cancel"].set()
            return
        if "id" not in message:
            return
        if method == "initialize":
            if type(params.get("protocolVersion")) is not int:
                raise ValueError("PROTOCOL_VERSION_REQUIRED")
            self.initialized = True
            self.result(
                request_id,
                {
                    "protocolVersion": 1,
                    "agentInfo": {"name": "scriptorium", "version": __version__},
                    "agentCapabilities": {
                        "promptCapabilities": {"embeddedContext": True},
                        "sessionCapabilities": {"close": {}},
                    },
                    "authMethods": [],
                },
            )
        elif not self.initialized:
            self.error(request_id, -32002, "INITIALIZE_REQUIRED")
        elif method == "session/new":
            cwd = Path(params.get("cwd", str(self.root))).resolve(strict=True)
            if not cwd.is_relative_to(self.root) or not cwd.is_dir():
                raise ValueError("WORKSPACE_OUTSIDE_CONFIGURED_ROOT")
            if params.get("mcpServers"):
                raise ValueError("EXTERNAL_MCP_ATTACHMENT_NOT_SUPPORTED_USE_DIRECT_MCP")
            tools = ResearchTools(str(cwd), self.database)
            sid = "sess_" + uuid.uuid4().hex
            self.sessions[sid] = {
                "tools": tools,
                "busy": threading.Lock(),
                "cancel": threading.Event(),
            }
            self.result(request_id, {"sessionId": sid})
        elif method == "session/prompt":
            sid = params.get("sessionId")
            session = self.sessions.get(sid)
            if not session:
                raise ValueError("UNKNOWN_SESSION")
            if not isinstance(params.get("prompt"), list):
                raise ValueError("PROMPT_BLOCKS_REQUIRED")
            if not session["busy"].acquire(blocking=False):
                self.error(request_id, -32000, "SESSION_BUSY")
                return
            session["cancel"].clear()
            threading.Thread(
                target=self.prompt, args=(request_id, sid, params["prompt"], session), daemon=True
            ).start()
        elif method == "session/close":
            session = self.sessions.get(params.get("sessionId"))
            if not session:
                raise ValueError("UNKNOWN_SESSION")
            if not session["busy"].acquire(blocking=False):
                self.error(request_id, -32000, "CANCEL_AND_WAIT_BEFORE_CLOSE")
                return
            session["tools"].close()
            del self.sessions[params["sessionId"]]
            self.result(request_id, {})
        else:
            self.error(request_id, -32601, "METHOD_NOT_FOUND")

    def run(self):
        limit = 4 * 1024 * 1024
        while True:
            line = sys.stdin.readline(limit + 1)
            if not line:
                return
            request_id = None
            try:
                if len(line) > limit:
                    while line and not line.endswith("\n"):
                        line = sys.stdin.readline(limit + 1)
                    raise ValueError("MESSAGE_TOO_LARGE")
                message = json.loads(line)
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise ValueError("INVALID_REQUEST")
                request_id = message.get("id")
                self.dispatch(message)
            except json.JSONDecodeError:
                self.error(None, -32700, "PARSE_ERROR")
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.error(request_id, -32602, str(exc)[:200])


def main():
    from .__main__ import serve

    serve("acp")
