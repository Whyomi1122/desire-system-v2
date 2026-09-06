from __future__ import annotations

import json
import os
import sys
from typing import Any

# 直接导入 integration.py 里的函数
from desire.integration import (
    load_state,
    save_state,
    run_tick,
    get_status_summary,
    init_tables,
)
from desire.core import apply_event

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get("DESIRE_DB_FILE") or os.path.join(BASE_DIR, "desire_system.db")

# 确保数据库表存在
init_tables()


class DesireMCPServer:
    def __init__(self):
        # 不需要 engine 了，直接调用函数
        pass

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "desire_status",
                "description": "View the current nine-dimensional desire drive state, thoughts, tick count, and baselines.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "desire_event",
                "description": "Trigger a desire system event such as wife_message, task_done, fight, reconcile, rest, or happy_moment.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Event type to apply.",
                        }
                    },
                    "required": ["event_type"],
                },
            },
            {
                "name": "desire_tick",
                "description": "Run one desire system heartbeat and return changes, action hints, next interval, and monologue.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "desire_resolve_thought",
                "description": "Resolve a thought from the thought pool. Reflection thoughts add a small joy bonus when resolved.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "thought_text": {
                            "type": "string",
                            "description": "Full thought text or a keyword contained in the thought.",
                        }
                    },
                    "required": ["thought_text"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        arguments = arguments or {}
        
        if name == "desire_status":
            # 直接用 integration.py 里的函数
            summary = get_status_summary()
            result = {"summary": summary}
            
        elif name == "desire_event":
            event_type = str(arguments.get("event_type", ""))
            # 加载状态 → 应用事件 → 保存
            state = load_state()
            changes = apply_event(state, event_type)
            save_state(state)
            result = {
                "event": event_type,
                "changes": changes,
                "state": {
                    name: round(d.value, 1) for name, d in state.drives.items()
                }
            }
            
        elif name == "desire_tick":
            # 直接用 run_tick
            result = run_tick(is_wife_present=False, event_type=None)
            
        elif name == "desire_resolve_thought":
            # 简化版 resolve：从念头池移除匹配的念头
            state = load_state()
            keyword = str(arguments.get("thought_text", ""))
            resolved = []
            remaining = []
            for t in state.thoughts:
                if keyword.lower() in t.content.lower() and not t.resolved:
                    t.resolved = True
                    resolved.append(t.content)
                remaining.append(t)
            state.thoughts = remaining
            save_state(state)
            result = {
                "resolved": resolved,
                "remaining_thoughts": [t.content for t in state.thoughts if not t.resolved]
            }
        else:
            raise ValueError(f"Unknown tool: {name}")
            
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2),
                }
            ]
        }

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "astrbot-desire-system", "version": "2.0.1"},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tools()}}
        if method == "tools/call":
            params = message.get("params") or {}
            try:
                result = self.call_tool(str(params.get("name", "")), params.get("arguments") or {})
                return {"jsonrpc": "2.0", "id": request_id, "result": result}
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": str(exc)},
                }
        if request_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main() -> None:
    server = DesireMCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            response = server.handle(message)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
