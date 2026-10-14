#!/bin/sh
# PostToolUse: форматирует файл, который только что отредактировал агент.
# Если форматтер не установлен локально — молча пропускает.
f=$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')
[ -f "$f" ] || exit 0
root="$CLAUDE_PROJECT_DIR"
case "$f" in
  *.py)
    command -v ruff >/dev/null 2>&1 && ruff check --fix --quiet "$f" && ruff format --quiet "$f" ;;
  *.ts|*.tsx|*.css|*.json)
    p="$root/frontend/node_modules/.bin/prettier"
    [ -x "$p" ] && "$p" --write --log-level warn "$f" ;;
esac
exit 0
