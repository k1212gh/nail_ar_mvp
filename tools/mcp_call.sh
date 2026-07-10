#!/bin/sh
# mcp_call.sh <tool> <json-args> — call Unity-MCP over raw streamable-HTTP.
# Session id cached in /tmp/mcp_sid.txt (created by the initialize handshake).
SID=$(cat /tmp/mcp_sid.txt 2>/dev/null)
[ -z "$SID" ] && { echo "no session id"; exit 1; }
TOOL="$1"; ARGS="${2:-{}}"
curl -s -X POST http://127.0.0.1:8080/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "mcp-session-id: $SID" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"$TOOL\",\"arguments\":$ARGS}}" \
  | sed -n 's/^data: //p'
