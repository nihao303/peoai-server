"""审计日志：只追加 JSON Lines，按大小滚动。

记录内容刻意保持最小化：动作、操作者、目标、IP、结果，
不写入请求正文与密钥，避免审计日志本身成为泄漏源。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .util import now, truncate


class AuditLog:
    def __init__(
        self,
        path: Path,
        enabled: bool = True,
        max_bytes: int = 5 * 1024 * 1024,
        backups: int = 3,
    ) -> None:
        self.path = Path(path)
        self.enabled = bool(enabled)
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self.backups = max(1, int(backups))
        self._lock = threading.Lock()

    def write(
        self,
        action: str,
        actor: str = "",
        target: str = "",
        ip: str = "",
        result: str = "ok",
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.enabled:
            return
        record = {
            "ts": round(now(), 3),
            "action": action,
            "actor": truncate(actor, 80),
            "target": truncate(target, 120),
            "ip": truncate(ip, 64),
            "result": result,
        }
        if detail:
            record["detail"] = {str(k)[:40]: truncate(v, 200) for k, v in detail.items()}
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed()
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                try:
                    os.chmod(self.path, 0o600)
                except OSError:
                    pass
            except OSError:
                return

    def _rotate_if_needed(self) -> None:
        try:
            if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
                return
        except OSError:
            return
        for index in range(self.backups - 1, 0, -1):
            source = self.path.with_name(self.path.name + ".%d" % index)
            target = self.path.with_name(self.path.name + ".%d" % (index + 1))
            if source.exists():
                try:
                    os.replace(str(source), str(target))
                except OSError:
                    pass
        try:
            os.replace(str(self.path), str(self.path.with_name(self.path.name + ".1")))
        except OSError:
            pass

    def tail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """读取最近若干条审计记录（供管理端展示）。"""
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text("utf-8", errors="replace").splitlines()[-max(1, limit):]
        except OSError:
            return []
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
        records.reverse()
        return records
