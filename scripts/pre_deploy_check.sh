#!/usr/bin/env bash
#
# scripts/pre_deploy_check.sh
#
# Прогоняет весь чеклист проверки перед деплоем, по порядку.
# Останавливается на первой стадии, которая упала — чтобы не тратить
# время на следующие шаги пока не починена текущая проблема.
#
# Запуск:
#   chmod +x scripts/pre_deploy_check.sh
#   ./scripts/pre_deploy_check.sh

set -e  # остановиться при первой ошибке

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

step() {
    echo -e "\n${YELLOW}━━━ $1 ━━━${NC}"
}

ok() {
    echo -e "${GREEN}✓ $1${NC}"
}

fail() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# ──────────────────────────────────────────────────────────────────
# Стадия 0: проверка что .env существует и не закоммичен
# ──────────────────────────────────────────────────────────────────

step "0. Проверка .env и секретов"

if [ ! -f .env ]; then
    fail ".env не найден. Скопируй .env.example -> .env и заполни GEMINI_API_KEY"
fi

if [ ! -d .git ]; then
    echo "  Папка ещё не git-репозиторий (нет .git/) — проверка .gitignore через git пропущена."
    if grep -qE "^\.env$|^\.env\.\*" .gitignore 2>/dev/null; then
        ok ".env присутствует в .gitignore (текстовая проверка, т.к. git init ещё не выполнен)"
    else
        fail ".env не найден в .gitignore — добавь строку '.env'"
    fi
elif git check-ignore -q .env 2>/dev/null; then
    ok ".env корректно игнорируется git"
else
    fail ".env НЕ в .gitignore — есть риск закоммитить секреты!"
fi

if grep -rE "AIzaSy[A-Za-z0-9_-]{20,}" --include="*.py" . 2>/dev/null | grep -v ".venv"; then
    fail "Найден захардкоженный API-ключ Gemini прямо в коде!"
else
    ok "Нет захардкоженных Gemini-ключей в .py файлах"
fi

# ──────────────────────────────────────────────────────────────────
# Стадия 1: статика и линтинг
# ──────────────────────────────────────────────────────────────────

step "1. Статика и линтинг"

python3 -m py_compile mcp_server/*.py agents/*.py a2a/*.py api/*.py tests/*.py
ok "Синтаксис всех .py файлов корректен (py_compile)"

if command -v ruff &> /dev/null; then
    ruff check . && ok "ruff check пройден" || fail "ruff нашёл проблемы — см. вывод выше"
else
    echo "  ruff не установлен, пропускаем (pip install ruff чтобы включить)"
fi

if command -v mypy &> /dev/null; then
    mypy . && ok "mypy проверка типов пройдена" || fail "mypy нашёл проблемы — см. вывод выше"
else
    echo "  mypy не установлен, пропускаем (pip install mypy чтобы включить)"
fi

# ──────────────────────────────────────────────────────────────────
# Стадия 2: юнит-тесты
# ──────────────────────────────────────────────────────────────────

step "2. Юнит-тесты"

pytest tests/ -v --tb=short
ok "Все юнит-тесты прошли"

# ──────────────────────────────────────────────────────────────────
# Стадия 3: локальный E2E через uvicorn
# ──────────────────────────────────────────────────────────────────

step "3. Локальный запуск FastAPI (health-check)"

uvicorn api.main:app --port 8000 &
SERVER_PID=$!
sleep 3

if curl -sf http://localhost:8000/health > /dev/null; then
    ok "FastAPI поднялся, /health отвечает"
else
    kill $SERVER_PID 2>/dev/null
    fail "FastAPI не отвечает на /health — смотри логи выше"
fi

for agent in parser analyzer coach guard; do
    if curl -sf "http://localhost:8000/agents/${agent}/a2a/health" > /dev/null; then
        ok "Агент ${agent} отвечает на /a2a/health"
    else
        kill $SERVER_PID 2>/dev/null
        fail "Агент ${agent} НЕ отвечает на /a2a/health"
    fi
done

kill $SERVER_PID 2>/dev/null
ok "Локальный сервер остановлен после проверки"

# ──────────────────────────────────────────────────────────────────
# Стадия 4: Docker сборка (опционально, если установлен docker)
# ──────────────────────────────────────────────────────────────────

step "4. Docker сборка"

if command -v docker &> /dev/null; then
    docker build -t clearmind:pre-deploy-check . && ok "Docker образ собрался успешно"
else
    echo "  docker не найден локально, пропускаем (проверится на Cloud Build)"
fi

# ──────────────────────────────────────────────────────────────────

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Все проверки пройдены — можно деплоить${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"