#!/bin/sh
# PostToolUse: форматирует файл, который только что отредактировал агент.
# Если форматтер недоступен — молча пропускает, правку не блокирует.
f=$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')
[ -f "$f" ] || exit 0
root="$CLAUDE_PROJECT_DIR"
case "$f" in
  *.py)
    if command -v ruff >/dev/null 2>&1; then
      ruff check --fix --quiet "$f" && ruff format --quiet "$f"
    else
      # ruff установлен в контейнере api; backend/ смонтирован туда как /app
      case "$f" in
        "$root"/backend/*)
          rel=${f#"$root"/backend/}
          cd "$root" && docker compose exec -T api sh -c \
            "ruff check --fix --quiet '$rel'; ruff format --quiet '$rel'" >/dev/null 2>&1
          ;;
      esac
    fi
    ;;
  *.ts|*.tsx|*.css|*.json)
    p="$root/frontend/node_modules/.bin/prettier"
    [ -x "$p" ] && "$p" --write --log-level warn "$f" >/dev/null 2>&1
    ;;
esac
exit 0
