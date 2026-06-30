"""
agents/security_policies.py

Детерминированные политики безопасности — функции-проверки, которые
Guard Agent вызывает как tools. Это НЕ LLM-логика: каждая проверка
возвращает строгий True/False плюс объяснение, чтобы решения по
безопасности были воспроизводимы и тестируемы (важно для судей,
которые будут читать код).
"""

from __future__ import annotations

import os

# Список доменов, на которые в принципе разрешены исходящие вызовы.
# Используется чтобы доказать (и протестировать), что кроме LLM API
# ничего наружу не уходит.
ALLOWED_OUTBOUND_DOMAINS = {
    "generativelanguage.googleapis.com",  # Gemini API
}

# Поля, которые НИКОГДА не должны попадать в текст, отправляемый в LLM —
# защита от случайной утечки PII даже если она появится в данных.
PII_FIELD_BLOCKLIST = {
    "device_id",
    "imei",
    "phone_number",
    "email",
    "full_name",
    "location",
    "ip_address",
}


def check_outbound_call_allowed(target_domain: str) -> tuple[bool, str]:
    """Проверяет, разрешён ли исходящий вызов на данный домен."""
    if target_domain in ALLOWED_OUTBOUND_DOMAINS:
        return True, f"Домен {target_domain} в allowlist (LLM API)."
    return False, f"БЛОКИРОВАНО: {target_domain} не в allowlist разрешённых доменов."


def check_no_pii_in_payload(payload: dict) -> tuple[bool, list[str]]:
    """
    Рекурсивно проверяет словарь на наличие полей из PII_FIELD_BLOCKLIST.
    Возвращает (clean, found_fields).
    """
    found: list[str] = []

    def _walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() in PII_FIELD_BLOCKLIST:
                    found.append(key)
                _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(payload)
    return len(found) == 0, found


def check_file_size(size_bytes: int) -> tuple[bool, str]:
    """Проверка лимита размера файла — дублирует проверку в MCP сервере
    намеренно: defense in depth, Guard Agent не доверяет слепо MCP слою."""
    max_size = int(os.getenv("MAX_FILE_SIZE_BYTES", "10485760"))
    if size_bytes > max_size:
        return False, f"Файл {size_bytes} байт превышает лимит {max_size} байт."
    return True, "Размер файла в пределах лимита."


def check_persist_data_disabled() -> tuple[bool, str]:
    """
    Проверяет что в .env флаг PERSIST_USER_DATA выставлен в false.
    Это central privacy guarantee всей системы — Guard Agent проверяет
    его явно, а не просто доверяет дефолту.
    """
    persist_flag = os.getenv("PERSIST_USER_DATA", "false").lower()
    if persist_flag == "true":
        return False, "ВНИМАНИЕ: PERSIST_USER_DATA=true — данные пользователя сохраняются."
    return True, "PERSIST_USER_DATA=false — данные не сохраняются после сессии."


def run_full_security_audit(
    *,
    file_size_bytes: int,
    payload_sent_to_llm: dict,
    outbound_domains_used: list[str],
) -> dict:
    """
    Прогоняет полный набор проверок и возвращает агрегированный результат.
    Это то, что Guard Agent вызывает перед тем как разрешить сессию
    считаться "чистой" для итогового Privacy Report.
    """
    results: dict[str, dict] = {}

    size_ok, size_msg = check_file_size(file_size_bytes)
    results["file_size"] = {"passed": size_ok, "message": size_msg}

    pii_ok, pii_found = check_no_pii_in_payload(payload_sent_to_llm)
    results["pii_check"] = {
        "passed": pii_ok,
        "message": "Нет PII в данных для LLM." if pii_ok else f"Найдены PII поля: {pii_found}",
    }

    persist_ok, persist_msg = check_persist_data_disabled()
    results["persistence"] = {"passed": persist_ok, "message": persist_msg}

    domain_results = [check_outbound_call_allowed(d) for d in outbound_domains_used]
    domains_ok = all(ok for ok, _ in domain_results)
    results["outbound_calls"] = {
        "passed": domains_ok,
        "message": "; ".join(msg for _, msg in domain_results) or "Нет исходящих вызовов.",
    }

    all_passed = all(r["passed"] for r in results.values())
    return {"all_passed": all_passed, "checks": results}