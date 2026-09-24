from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_repository() -> None:
    path = Path("db/repository.py")
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from utils.timeutils import now_utc_naive\n",
        "from utils.timeutils import now_utc_naive\nfrom utils.json_safety import strict_json_safe\n",
        "repository json_safety import",
    )
    text = replace_once(
        text,
        "                meta=meta or {},\n            )\n            session.add(dl)",
        "                meta=strict_json_safe(meta or {}),\n            )\n            session.add(dl)",
        "direct decision meta sanitation",
    )
    text = replace_once(
        text,
        '                "meta": dict(meta or {}),\n            })\n            logging.getLogger(__name__).info(',
        '                "meta": strict_json_safe(dict(meta or {})),\n            })\n            logging.getLogger(__name__).info(',
        "decision retry queue sanitation",
    )
    text = replace_once(
        text,
        '            "reason": str(row.get("reason") or "")[:1000] or None, "meta": dict(row.get("meta") or {}),\n',
        '            "reason": str(row.get("reason") or "")[:1000] or None, "meta": strict_json_safe(dict(row.get("meta") or {})),\n',
        "decision batch sanitation",
    )
    text = replace_once(
        text,
        "            session.add_all([DecisionLog(**item) for item in batch])\n",
        "            session.add_all([\n                DecisionLog(**{**item, \"meta\": strict_json_safe(item.get(\"meta\") or {})})\n                for item in batch\n            ])\n",
        "decision retry flush sanitation",
    )
    path.write_text(text, encoding="utf-8")


def patch_railway_main() -> None:
    path = Path("railway_main.py")
    text = path.read_text(encoding="utf-8")
    anchor = '''    _monitor_tasks.append(asyncio.create_task(_run_deployment_diagnostics_once()))\n    _monitor_tasks[-1].add_done_callback(lambda t: _log_task_failure(t, "deployment-diagnostics"))\n'''
    replacement = anchor + '''\n    # Bound append-only learning telemetry. Disabled by default and enabled per\n    # environment so production retention can be longer than staging retention.\n    if _db_ready and startup_work_enabled and _env_bool("LEARNING_HISTORY_RETENTION_ENABLED", False):\n        try:\n            from db.storage_maintenance import learning_history_maintenance_loop\n\n            _monitor_tasks.append(asyncio.create_task(learning_history_maintenance_loop()))\n            _monitor_tasks[-1].add_done_callback(\n                lambda t: _log_task_failure(t, "learning-history-retention")\n            )\n            logger.info("[storage_maintenance] periodic learning-history retention task started")\n        except Exception as exc:\n            logger.warning("[storage_maintenance] could not start retention loop: %s", exc)\n'''
    text = replace_once(text, anchor, replacement, "railway retention task")
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_repository()
    patch_railway_main()
    print("staging storage hotfix applied")
