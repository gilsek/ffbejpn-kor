"""Dynamic project inventory and quality audit for the GalTransl workspace."""

from __future__ import annotations

import csv
import base64
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from usage_monitor import ensure_runtime_files, summarize_usage
except ImportError:  # pragma: no cover - package-style imports
    from .usage_monitor import ensure_runtime_files, summarize_usage


GATEWAY_ENV = Path.home() / "litellm-gateway" / ".env"


def gateway_key() -> str:
    key = os.environ.get("LITELLM_MASTER_KEY", "").strip()
    if not key and GATEWAY_ENV.exists():
        for line in GATEWAY_ENV.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("LITELLM_MASTER_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise SystemExit(f"LITELLM_MASTER_KEY not found (env or {GATEWAY_ENV})")
    return key


PROJECT_DIR = Path(__file__).resolve().parent
ROOT_DIR = PROJECT_DIR.parents[1]
INPUT_DIR = PROJECT_DIR / "gt_input"
OUTPUT_DIR = PROJECT_DIR / "gt_output"
CACHE_DIR = PROJECT_DIR / "transl_cache"
CSV_DIR = PROJECT_DIR / "csv_exports"
META_PATH = (
    PROJECT_DIR / "script_meta.json"
    if (PROJECT_DIR / "script_meta.json").exists()
    else PROJECT_DIR / "chapter1_meta.json"
)
CONFIG_PATH = PROJECT_DIR / "config.yaml"
RUNTIME_DIR = PROJECT_DIR / "runtime"
QA_REVIEWS_PATH = RUNTIME_DIR / "qa_reviews.json"

TRANSLATION_PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek (deepseek-flash)",
    },
    "keyrouter": {
        "label": "KeyRouter (gemini-flash-lite)",
        "values": {
            "token": "not-a-secret",
            "endpoint": "http://macmini.local:4010/v1",
            "model": "gemini-flash-lite",
            "apiErrorWait": "auto",
            "maxApiRetries": "2",
            "genDicMaxApiRetries": "2",
            "gpt.numPerRequestTranslate": "16",
            "workersPerProject": "1",
            "autoAdjustWorkers": "false",
        },
    },
    "cliproxyapi": {
        "label": "LiteLLM Gateway (ds-flash)",
        "values": {
            "token": "GATEWAY_KEY",
            "endpoint": "http://127.0.0.1:4000/v1",
            "model": "ds-flash",
            "apiErrorWait": "auto",
            "maxApiRetries": "3",
            "genDicMaxApiRetries": "2",
            "gpt.numPerRequestTranslate": "16",
            "workersPerProject": "5",
            "autoAdjustWorkers": "false",
        },
    },
}

_PROFILE_FIELD_PATTERNS = {
    "token": re.compile(r"(?m)^([ \t]*-[ \t]*token:[ \t]*)([^\r\n]*)(\r?)$"),
    "endpoint": re.compile(r"(?m)^([ \t]*endpoint:[ \t]*)([^\r\n]*)(\r?)$"),
    "model": re.compile(r"(?m)^([ \t]*modelName:[ \t]*)([^\r\n]*)(\r?)$"),
    "apiErrorWait": re.compile(r"(?m)^([ \t]*apiErrorWait:[ \t]*)([^\r\n]*)(\r?)$"),
    "maxApiRetries": re.compile(r"(?m)^([ \t]*maxApiRetries:[ \t]*)([^\r\n]*)(\r?)$"),
    "genDicMaxApiRetries": re.compile(
        r"(?m)^([ \t]*genDicMaxApiRetries:[ \t]*)([^\r\n]*)(\r?)$"
    ),
    "gpt.numPerRequestTranslate": re.compile(
        r"(?m)^([ \t]*gpt\.numPerRequestTranslate:[ \t]*)([^\r\n]*)(\r?)$"
    ),
    "workersPerProject": re.compile(
        r"(?m)^([ \t]*workersPerProject:[ \t]*)([^\r\n]*)(\r?)$"
    ),
    "autoAdjustWorkers": re.compile(
        r"(?m)^([ \t]*autoAdjustWorkers:[ \t]*)([^\r\n]*)(\r?)$"
    ),
}
_REQUIRED_PROFILE_FIELDS = {"token", "endpoint", "model"}

HIRAGANA_RE = re.compile(r"[\u3040-\u309f]")
KATAKANA_RE = re.compile(r"[\u30a0-\u30ff]")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
KOREAN_RE = re.compile(r"[\uac00-\ud7a3]")
CONTROL_TAG_RE = re.compile(r"\[[A-Z][A-Z0-9_]*\]|<(?!(?:br)\s*/?>)[^>]+>", re.IGNORECASE)
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


@dataclass
class Issue:
    scope: str
    type: str
    file: str
    ffbe_id: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "scope": self.scope,
            "type": self.type,
            "file": self.file,
            "ffbe_id": self.ffbe_id,
            "detail": self.detail,
        }


@dataclass
class FileAudit:
    file: str
    row_count: int = 0
    completed_rows: int = 0
    japanese_rows: int = 0
    source_chars: int = 0
    output_chars: int = 0
    name_missing: int = 0
    output_exists: bool = False
    cache_exists: bool = False
    source_hash: str = ""
    output_hash: str = ""
    status: str = "pending"
    issues: list[Issue] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        error_count = sum(1 for issue in self.issues if issue.scope in {"source", "output"})
        return {
            "file": self.file,
            "row_count": self.row_count,
            "completed_rows": self.completed_rows,
            "japanese_rows": self.japanese_rows,
            "source_chars": self.source_chars,
            "output_chars": self.output_chars,
            "name_missing": self.name_missing,
            "output_exists": self.output_exists,
            "cache_exists": self.cache_exists,
            "source_hash": self.source_hash,
            "output_hash": self.output_hash,
            "status": self.status,
            "issue_count": error_count,
        }


class TranslationRunner:
    """Run GalTransl through its local HTTP backend and persist job metadata."""

    def __init__(
        self,
        project_dir: Path,
        backend_path: Path,
        runtime_dir: Path,
        on_line: Any = None,
    ) -> None:
        self.project_dir = project_dir
        self.backend_path = backend_path
        self.runtime_dir = runtime_dir
        self.on_line = on_line
        self.process: subprocess.Popen[str] | None = None
        self.log_path = runtime_dir / "galtransl_run.log"
        self.backend_log_path = runtime_dir / "galtransl_backend.log"
        self.ready_path = runtime_dir / "galtransl_backend_ready.json"
        self.state_path = runtime_dir / "run_state.json"
        self.server_url = ""
        self.job_id = ""
        self._monitor_thread: threading.Thread | None = None
        self._log_stream: Any = None
        self._project_log_offset = 0

    def _write_state(self, state: dict[str, Any]) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for attempt in range(5):
            try:
                temp_path.replace(self.state_path)
                return
            except PermissionError:
                if attempt < 4:
                    time.sleep(0.05)
                else:
                    try:
                        self.state_path.write_text(
                            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                    except Exception:
                        pass

    def start(self) -> dict[str, Any]:
        if self.is_running():
            raise RuntimeError("GalTransl is already running.")
        if not self.backend_path.exists():
            raise FileNotFoundError(f"GalTransl backend was not found: {self.backend_path}")

        baseline = audit_project(self.project_dir, self.runtime_dir, write_snapshot=True)
        started_at = utc_now()
        project_log_path = self.project_dir / "GalTransl.log"
        try:
            self._project_log_offset = project_log_path.stat().st_size
        except OSError:
            self._project_log_offset = 0
        self.ready_path.unlink(missing_ok=True)
        creation_flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
            else 0
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_stream = self.backend_log_path.open("w", encoding="utf-8")
        backend_env = os.environ.copy()
        backend_env["PYTHONIOENCODING"] = "utf-8:replace"
        backend_env["PYTHONUTF8"] = "1"
        backend_env["PYTHONLEGACYWINDOWSSTDIO"] = "0"
        self.process = subprocess.Popen(
            [
                str(self.backend_path),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--ready-file",
                str(self.ready_path),
            ],
            cwd=str(self.backend_path.parent),
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            env=backend_env,
            creationflags=creation_flags,
        )
        ready_deadline = time.monotonic() + 15
        ready: dict[str, Any] = {}
        while time.monotonic() < ready_deadline:
            if self.process.poll() is not None:
                detail = self._backend_log_tail()
                self._cleanup_backend()
                raise RuntimeError(f"GalTransl backend exited during startup.\n{detail}")
            if self.ready_path.exists():
                try:
                    ready = json.loads(self.ready_path.read_text(encoding="utf-8"))
                    if isinstance(ready, dict) and ready.get("port"):
                        break
                except (OSError, json.JSONDecodeError):
                    pass
            time.sleep(0.1)
        if not ready.get("port"):
            detail = self._backend_log_tail()
            self._cleanup_backend()
            raise RuntimeError(f"GalTransl backend did not become ready.\n{detail}")

        self.server_url = f"http://{ready.get('host', '127.0.0.1')}:{ready['port']}"
        translator = os.environ.get("FFBE_GALTRANSL_TRANSLATOR", "ForGal-markdown")
        job = self._request_json(
            "/api/jobs",
            {
                "project_dir": str(self.project_dir),
                "config_file_name": "config.yaml",
                "translator": translator,
            },
            method="POST",
        )
        self.job_id = str(job.get("job_id") or "")
        if not self.job_id:
            self._cleanup_backend()
            raise RuntimeError(f"GalTransl did not return a job id: {job}")
        state = {
            "status": str(job.get("status") or "pending"),
            "pid": self.process.pid,
            "job_id": self.job_id,
            "server_url": self.server_url,
            "started_at": started_at,
            "finished_at": None,
            "success": None,
            "error": "",
            "baseline_rows_completed": baseline["summary"]["rows_completed"],
            "rows_total": baseline["summary"]["rows_total"],
            "model": baseline["profile"].get("model", ""),
            "endpoint": baseline["profile"].get("endpoint", ""),
            "translator": translator,
            "log_path": str(self.log_path),
            "backend_log_path": str(self.backend_log_path),
        }
        self._write_state(state)
        self._monitor_thread = threading.Thread(target=self._monitor_job, daemon=True)
        self._monitor_thread.start()
        return state

    def _request_json(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        method: str = "GET",
    ) -> dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.server_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                result = json.loads(body) if body else {}
                return result if isinstance(result, dict) else {"data": result}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GalTransl API {method} {path} failed: {exc.code} {body}") from exc

    def _emit_new_project_log(self) -> None:
        path = self.project_dir / "GalTransl.log"
        try:
            size = path.stat().st_size
            if size < self._project_log_offset:
                self._project_log_offset = 0
            if size == self._project_log_offset:
                return
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                stream.seek(self._project_log_offset)
                lines = stream.readlines()
                self._project_log_offset = stream.tell()
            for line in lines:
                if callable(self.on_line):
                    self.on_line(line.rstrip("\r\n"))
        except OSError:
            return

    def _monitor_job(self) -> None:
        terminal = {"completed", "failed", "cancelled"}
        consecutive_errors = 0
        while True:
            self._emit_new_project_log()
            try:
                response = self._request_json("/api/jobs")
                jobs = response.get("jobs", [])
                job = next(
                    (item for item in jobs if str(item.get("job_id")) == self.job_id),
                    None,
                )
                if job is None:
                    raise RuntimeError(f"GalTransl job disappeared: {self.job_id}")
                state = self.read_state()
                state.update(
                    {
                        "status": str(job.get("status") or state.get("status") or ""),
                        "success": job.get("success"),
                        "error": str(job.get("error") or ""),
                    }
                )
                if state["status"] in terminal:
                    state["finished_at"] = job.get("finished_at") or utc_now()
                    self._emit_new_project_log()
                    self._write_state(state)
                    if callable(self.on_line):
                        message = f"[runner] GalTransl job {state['status']}"
                        if state.get("error"):
                            message += f": {state['error']}"
                        self.on_line(message)
                    self._cleanup_backend()
                    return
                self._write_state(state)
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                if self.process is not None and self.process.poll() is None and consecutive_errors < 10:
                    time.sleep(1)
                    continue
                state = self.read_state()
                state.update(
                    {
                        "status": "failed",
                        "success": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "finished_at": utc_now(),
                    }
                )
                self._write_state(state)
                if callable(self.on_line):
                    self.on_line(f"[runner] {state['error']}")
                self._cleanup_backend()
                return
            time.sleep(1)

    def _backend_log_tail(self, limit: int = 3000) -> str:
        try:
            return self.backend_log_path.read_text(encoding="utf-8", errors="replace")[-limit:]
        except OSError:
            return ""

    def _cleanup_backend(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self._log_stream is not None:
            self._log_stream.close()
            self._log_stream = None

    def is_running(self) -> bool:
        if self.process is None or self.process.poll() is not None:
            return False
        return self.read_state().get("status") in {"pending", "running"}

    def stop(self) -> None:
        state = self.read_state()
        if state.get("status") in {"pending", "running"}:
            state.update(
                {
                    "status": "cancelled",
                    "success": False,
                    "finished_at": utc_now(),
                }
            )
            self._write_state(state)
        self._cleanup_backend()

    def read_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}


def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json_list(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if not isinstance(data, list):
        return [], "Root JSON value is not a list."
    records = [item for item in data if isinstance(item, dict)]
    if len(records) != len(data):
        return records, f"{len(data) - len(records)} non-object entries were ignored."
    return records, ""


def file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def has_kana(text: str) -> bool:
    return bool(HIRAGANA_RE.search(text) or KATAKANA_RE.search(text))


def has_japanese_text(text: str) -> bool:
    return bool(has_kana(text) or CJK_RE.search(text))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", BR_RE.sub("\n", text or "")).strip()


def tag_counts(text: str) -> Counter[str]:
    return Counter(tag.group(0).upper() for tag in CONTROL_TAG_RE.finditer(text or ""))


def _safe_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_galtransl_profile(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "endpoint": "",
        "model": "",
        "timeout_seconds": None,
        "max_retries": None,
        "workers": None,
        "batch_size": None,
        "context_size": None,
        "error_wait": "",
        "auto_adjust_workers": None,
        "language": "",
    }
    if not config_path.exists():
        return profile
    text = config_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = _safe_yaml_scalar(value)
        mapping = {
            "endpoint": ("endpoint", str),
            "modelName": ("model", str),
            "apiTimeout": ("timeout_seconds", int),
            "maxApiRetries": ("max_retries", int),
            "workersPerProject": ("workers", int),
            "gpt.numPerRequestTranslate": ("batch_size", int),
            "gpt.contextNum": ("context_size", int),
            "apiErrorWait": ("error_wait", str),
            "language": ("language", str),
        }
        if key in mapping:
            target, converter = mapping[key]
            try:
                profile[target] = converter(value) if converter is int else value
            except ValueError:
                pass
        elif key == "autoAdjustWorkers":
            profile["auto_adjust_workers"] = value.lower() == "true"
    return profile


def discover_galtransl_backend(root_dir: Path = ROOT_DIR) -> Path | None:
    candidates = list(
        (root_dir / "artifacts" / "tool-evaluation").glob(
            "GalTransl*/**/backend/galtransl_backend.exe"
        )
    )
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def replace_config_endpoint(config_path: Path, endpoint: str) -> str:
    """Replace only the first endpoint scalar and return the previous value."""
    if not config_path.exists():
        raise FileNotFoundError(config_path)
    text = config_path.read_text(encoding="utf-8")
    pattern = re.compile(r"(?m)^(\s*endpoint:\s*)([^\r\n#]*)(.*)$")
    match = pattern.search(text)
    if not match:
        raise ValueError(f"No endpoint setting found in {config_path}")
    previous = _safe_yaml_scalar(match.group(2))
    updated = text[: match.start(2)] + endpoint + text[match.end(2) :]
    temp_path = config_path.with_suffix(".yaml.tmp")
    temp_path.write_text(updated, encoding="utf-8")
    temp_path.replace(config_path)
    return previous


def select_translation_provider(config_path: Path, provider: str) -> None:
    """Apply a complete provider profile while preserving the DeepSeek values."""
    provider_profile = TRANSLATION_PROVIDER_PROFILES.get(provider)
    if provider_profile is None:
        raise ValueError("지원하지 않는 모델입니다.")
    text = config_path.read_text(encoding="utf-8")
    matches = {
        key: list(pattern.finditer(text))
        for key, pattern in _PROFILE_FIELD_PATTERNS.items()
    }
    if any(len(matches[key]) != 1 for key in _REQUIRED_PROFILE_FIELDS):
        raise ValueError("단일 API 설정만 전환할 수 있습니다. 설정 파일을 확인하세요.")
    if any(len(found) > 1 for found in matches.values()):
        raise ValueError("번역 옵션이 여러 번 정의되어 있습니다. 설정 파일을 확인하세요.")
    values = {
        key: found[0].group(2)
        for key, found in matches.items()
        if len(found) == 1
    }
    current_model = _safe_yaml_scalar(values["model"])
    marker = re.compile(r"(?m)^# dashboard_saved_deepseek: ([A-Za-z0-9+/=]+)\r?\n")
    saved = marker.search(text)
    if "values" in provider_profile:
        if saved is None:
            if current_model.startswith("deepseek"):
                payload = base64.b64encode(json.dumps(values, ensure_ascii=False).encode("utf-8")).decode("ascii")
                text = "# dashboard_saved_deepseek: " + payload + "\n" + text
        new_values = dict(provider_profile["values"])
    else:
        if saved is None:
            if current_model.startswith("deepseek"):
                return
            raise ValueError("보관된 DeepSeek 설정이 없습니다.")
        try:
            new_values = json.loads(base64.b64decode(saved.group(1), validate=True).decode("utf-8"))
            if (
                not isinstance(new_values, dict)
                or not _REQUIRED_PROFILE_FIELDS.issubset(new_values)
                or not set(new_values).issubset(_PROFILE_FIELD_PATTERNS)
                or not all(
                    isinstance(value, str)
                    and "\n" not in value
                    and "\r" not in value
                    for value in new_values.values()
                )
            ):
                raise ValueError("invalid saved profile")
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("보관된 DeepSeek 설정을 읽을 수 없습니다.") from exc
        text = marker.sub("", text, count=1)
    for key, value in new_values.items():
        pattern = _PROFILE_FIELD_PATTERNS[key]
        if not pattern.search(text):
            raise ValueError(f"GalTransl 설정 항목을 찾을 수 없습니다: {key}")
        text = pattern.sub(
            lambda match, replacement=value: match.group(1) + replacement + match.group(3),
            text,
            count=1,
        )
    import tempfile
    import os
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=config_path.parent, delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(text)
        os.replace(temp_path, config_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def discover_csv_files(csv_dir: Path = CSV_DIR) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not csv_dir.exists():
        return result
    for path in sorted(csv_dir.glob("*.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream)
                headers = next(reader, [])
                rows = sum(1 for _ in reader)
            result.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "rows": rows,
                    "columns": headers,
                }
            )
        except (OSError, csv.Error, UnicodeError) as exc:
            result.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "rows": 0,
                    "columns": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return result


def _source_entries(
    file_name: str,
    records: Iterable[dict[str, Any]],
    audit: FileAudit,
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(records):
        ffbe_id = str(record.get("ffbe_id") or "").strip()
        message = str(record.get("message") or "")
        name = str(record.get("name") or "")
        if not ffbe_id:
            audit.issues.append(Issue("source", "missing_ffbe_id", file_name, detail=f"index={index}"))
        elif ffbe_id in seen_ids:
            audit.issues.append(Issue("source", "duplicate_ffbe_id", file_name, ffbe_id))
        seen_ids.add(ffbe_id)
        if not message.strip():
            audit.issues.append(Issue("source", "blank_message", file_name, ffbe_id))
        elif not has_japanese_text(message):
            if re.search(r"[A-Za-z]", message):
                audit.issues.append(
                    Issue("source", "non_japanese_latin_source", file_name, ffbe_id, message[:120])
                )
            else:
                audit.issues.append(
                    Issue("source", "neutral_source_text", file_name, ffbe_id, message[:120])
                )
        if not name.strip():
            audit.name_missing += 1
        audit.row_count += 1
        audit.source_chars += len(message)
        audit.japanese_rows += int(has_japanese_text(message))
        prepared.append(record)
    return prepared


def _audit_output(
    file_name: str,
    source: list[dict[str, Any]],
    audit: FileAudit,
    output_dir: Path,
) -> None:
    output_path = output_dir / file_name
    if not output_path.exists():
        fatal = any(issue.type == "invalid_input_json" for issue in audit.issues)
        audit.status = "blocked" if fatal else ("source_warning" if audit.issues else "pending")
        return
    audit.output_exists = True
    audit.output_hash = file_hash(output_path)
    output, parse_error = read_json_list(output_path)
    if parse_error:
        audit.issues.append(Issue("output", "invalid_output_json", file_name, detail=parse_error))
        audit.status = "blocked"
        return

    output_by_id: dict[str, dict[str, Any]] = {}
    output_seen: set[str] = set()
    for index, record in enumerate(output):
        ffbe_id = str(record.get("ffbe_id") or "").strip()
        message = str(record.get("message") or "")
        audit.output_chars += len(message)
        if not ffbe_id:
            audit.issues.append(Issue("output", "missing_ffbe_id", file_name, detail=f"index={index}"))
            continue
        if ffbe_id in output_seen:
            audit.issues.append(Issue("output", "duplicate_output_id", file_name, ffbe_id))
        output_seen.add(ffbe_id)
        output_by_id[ffbe_id] = record

    source_ids = {str(row.get("ffbe_id") or "").strip() for row in source}
    seen_source_ids: set[str] = set()
    for row in source:
        ffbe_id = str(row.get("ffbe_id") or "").strip()
        if ffbe_id in seen_source_ids:
            continue
        seen_source_ids.add(ffbe_id)
        source_text = str(row.get("message") or "")
        target = output_by_id.get(ffbe_id)
        if target is None:
            audit.issues.append(Issue("output", "missing_translation", file_name, ffbe_id))
            continue
        target_text = str(target.get("message") or "")
        if not target_text.strip():
            audit.issues.append(Issue("output", "blank_translation", file_name, ffbe_id))
            continue
        audit.completed_rows += 1
        if has_kana(target_text):
            audit.issues.append(
                Issue("output", "japanese_remaining", file_name, ffbe_id, target_text[:120])
            )
        source_tags = tag_counts(source_text)
        target_tags = tag_counts(target_text)
        if source_tags != target_tags:
            audit.issues.append(
                Issue(
                    "output",
                    "control_tag_mismatch",
                    file_name,
                    ffbe_id,
                    f"source={dict(source_tags)}, output={dict(target_tags)}",
                )
            )

    for ffbe_id in sorted(output_seen - source_ids):
        audit.issues.append(Issue("output", "extra_output_id", file_name, ffbe_id))

    if (
        audit.completed_rows == audit.row_count
        and not any(issue.type == "missing_translation" for issue in audit.issues)
    ):
        audit.status = "translated"
    if audit.issues:
        audit.status = "qa_warning" if audit.completed_rows else "blocked"


def _audit_meta(
    input_records: dict[str, list[dict[str, Any]]],
    issues: list[Issue],
    meta_path: Path,
) -> dict[str, Any]:
    result = {
        "exists": meta_path.exists(),
        "rows": 0,
        "unique_keys": 0,
        "duplicate_keys": 0,
        "missing_source_entries": 0,
        "unreferenced_input_entries": 0,
        "japanese_mismatches": 0,
    }
    if not meta_path.exists():
        return result
    meta_rows, parse_error = read_json_list(meta_path)
    if parse_error:
        issues.append(Issue("meta", "invalid_meta_json", meta_path.name, detail=parse_error))
        return result
    result["rows"] = len(meta_rows)
    meta_map: dict[tuple[str, str], str] = {}
    duplicates: set[tuple[str, str]] = set()
    for row in meta_rows:
        cpk_name = str(row.get("cpk_name") or "").strip()
        ffbe_id = str(row.get("ffbe_id") or "").strip()
        input_file = str(row.get("input_file") or "")
        key = (Path(input_file).stem if input_file else Path(cpk_name).stem, ffbe_id)
        if key in meta_map:
            duplicates.add(key)
        meta_map[key] = str(row.get("clean_jp") or "")
    result["unique_keys"] = len(meta_map)
    result["duplicate_keys"] = len(duplicates)
    for key in sorted(duplicates):
        issues.append(Issue("meta", "duplicate_meta_key", meta_path.name, key[1], key[0]))

    input_keys: set[tuple[str, str]] = set()
    for file_name, records in sorted(input_records.items()):
        stem = Path(file_name).stem
        for row in records:
            ffbe_id = str(row.get("ffbe_id") or "").strip()
            key = (stem, ffbe_id)
            input_keys.add(key)
            if key not in meta_map:
                result["missing_source_entries"] += 1
                issues.append(Issue("meta", "input_without_meta", file_name, ffbe_id))
                continue
            if normalize_text(meta_map[key]) != normalize_text(str(row.get("message") or "")):
                result["japanese_mismatches"] += 1
                issues.append(Issue("meta", "japanese_mismatch", file_name, ffbe_id))
    result["unreferenced_input_entries"] = len(set(meta_map) - input_keys)
    for key in sorted(set(meta_map) - input_keys):
        issues.append(Issue("meta", "meta_without_input", meta_path.name, key[1], key[0]))
    return result


def review_key(issue: Issue | dict[str, Any]) -> str:
    if isinstance(issue, Issue):
        scope, issue_type, file_name, ffbe_id = (
            issue.scope,
            issue.type,
            issue.file,
            issue.ffbe_id,
        )
    else:
        scope, issue_type, file_name, ffbe_id = (
            issue.get("scope", ""),
            issue.get("type", ""),
            issue.get("file", ""),
            issue.get("ffbe_id", ""),
        )
    return f"{scope}|{issue_type}|{file_name}|{ffbe_id}"


def load_qa_reviews(project_dir: Path = PROJECT_DIR) -> dict[str, dict[str, Any]]:
    path = project_dir / "runtime" / "qa_reviews.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_qa_reviews(
    reviews: dict[str, dict[str, Any]],
    project_dir: Path = PROJECT_DIR,
) -> None:
    path = project_dir / "runtime" / "qa_reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(reviews, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def accept_qa_issue(
    issue: dict[str, Any],
    note: str = "",
    project_dir: Path = PROJECT_DIR,
) -> dict[str, Any]:
    reviews = load_qa_reviews(project_dir)
    record = {
        "status": "accepted",
        "reviewed_at": utc_now(),
        "note": note,
        "scope": issue.get("scope", ""),
        "type": issue.get("type", ""),
        "file": issue.get("file", ""),
        "ffbe_id": issue.get("ffbe_id", ""),
    }
    reviews[review_key(issue)] = record
    write_qa_reviews(reviews, project_dir)
    return record


def explain_issue(
    issue: Issue | dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return a plain-language reason and suggested action for a QA issue."""
    if isinstance(issue, Issue):
        issue_type = issue.type
        detail = issue.detail
    else:
        issue_type = str(issue.get("type") or "")
        detail = str(issue.get("detail") or "")
    context = context or {}
    source = str(context.get("source") or "")
    translation = str(context.get("translation") or "")

    if issue_type == "japanese_remaining":
        remaining = "".join(
            sorted(
                {
                    char
                    for char in translation
                    if "\u3040" <= char <= "\u30ff"
                }
            )
        )
        reason = "번역문에 히라가나 또는 가타카나가 남아 있습니다."
        if remaining:
            reason += f" 남은 문자: {remaining}"
        action = "남은 일본어를 자연스러운 한국어로 바꾼 뒤 저장하세요."
    elif issue_type == "control_tag_mismatch":
        source_tags = tag_counts(source)
        target_tags = tag_counts(translation)
        missing = source_tags - target_tags
        extra = target_tags - source_tags
        changes = []
        if missing:
            changes.append("누락 " + ", ".join(f"{tag}×{count}" for tag, count in missing.items()))
        if extra:
            changes.append("초과 " + ", ".join(f"{tag}×{count}" for tag, count in extra.items()))
        reason = "게임 제어 태그가 원문과 번역문에서 다릅니다."
        if changes:
            reason += " (" + " / ".join(changes) + ")"
        action = "원문과 같은 수·위치의 [PAGE] 같은 태그를 복원하세요."
    elif issue_type == "non_japanese_latin_source":
        reason = "원문에 일본어 대신 라틴 문자와 숫자만 있습니다."
        action = "고유명사·UI 문자열이면 승인하고, 원문 누락이면 원본 소스를 보완하세요."
    elif issue_type == "neutral_source_text":
        reason = "원문이 숫자·기호·구분선처럼 언어 문자가 없는 값입니다."
        action = "의도된 표시값이면 승인하세요. 번역할 문장이면 원문 추출을 다시 확인하세요."
    elif issue_type == "blank_message":
        reason = "원문 또는 번역문의 메시지가 비어 있습니다."
        action = "원문과 번역 결과를 확인하고 빈 값을 채우세요."
    elif issue_type == "missing_translation":
        reason = "원문 ID에 대응하는 번역 결과가 없습니다."
        action = "해당 파일을 번역 작업에 포함해 다시 실행하세요."
    elif issue_type == "blank_translation":
        reason = "번역 결과의 메시지가 비어 있습니다."
        action = "해당 ID의 번역문을 입력하세요."
    elif issue_type in {"duplicate_ffbe_id", "duplicate_output_id"}:
        reason = "같은 파일 안에서 FFBE ID가 중복됩니다."
        action = "중복 행의 원본 순서와 번역 대상을 확인하세요."
    elif issue_type.startswith("invalid_"):
        reason = "JSON 구조를 읽지 못했습니다."
        action = "해당 파일의 JSON 형식과 인코딩을 복구하세요."
    elif issue_type in {"input_without_meta", "meta_without_input", "japanese_mismatch"}:
        reason = "입력 JSON과 스크립트 메타데이터 연결이 일치하지 않습니다."
        action = "스크립트 범위와 추출 결과를 다시 생성해 대조하세요."
    else:
        reason = "자동 검사에서 추가 확인이 필요한 항목으로 분류됐습니다."
        action = "원문과 번역문을 비교하고 필요하면 직접 수정하거나 승인하세요."
    if detail and detail not in reason:
        reason += f" 감지 내용: {detail}"
    return {
        "summary": reason.split(" 감지 내용:", 1)[0],
        "reason": reason,
        "action": action,
    }


def _find_record(records: list[dict[str, Any]], ffbe_id: str) -> dict[str, Any]:
    return next(
        (row for row in records if str(row.get("ffbe_id") or "") == str(ffbe_id)),
        {},
    )


def get_issue_context(
    file_name: str,
    ffbe_id: str,
    project_dir: Path = PROJECT_DIR,
) -> dict[str, Any]:
    input_path = project_dir / "gt_input" / file_name
    output_path = project_dir / "gt_output" / file_name
    input_rows, input_error = read_json_list(input_path)
    output_rows, output_error = read_json_list(output_path) if output_path.exists() else ([], "")
    source = _find_record(input_rows, ffbe_id)
    output = _find_record(output_rows, ffbe_id)
    stem = Path(file_name).stem
    meta: dict[str, Any] = {}
    meta_db_path = project_dir / "script_meta.sqlite"
    if meta_db_path.exists():
        try:
            with sqlite3.connect(meta_db_path) as connection:
                cursor = connection.execute(
                    """
                    SELECT speaker_jp, speaker_ko, clean_jp, english_clean, cpk_name
                    FROM script_meta
                    WHERE scene_id = ? AND ffbe_id = ?
                    ORDER BY CASE WHEN cpk_name = ? THEN 0 ELSE 1 END
                    LIMIT 1
                    """,
                    (stem.split("__", 1)[0], str(ffbe_id), f"{stem}.cpk"),
                )
                row = cursor.fetchone()
                if row:
                    meta = {
                        "speaker_jp": row[0] or "",
                        "speaker_ko": row[1] or "",
                        "clean_jp": row[2] or "",
                        "english_clean": row[3] or "",
                        "cpk_name": row[4] or "",
                    }
        except sqlite3.Error:
            meta = {}
    if not meta:
        meta_path = project_dir / "script_meta.json"
        if not meta_path.exists():
            meta_path = project_dir / "chapter1_meta.json"
        meta_rows, _meta_error = read_json_list(meta_path)
        meta = next(
            (
                row
                for row in meta_rows
                if str(row.get("ffbe_id") or "") == str(ffbe_id)
                and (
                    str(row.get("input_file") or "") == file_name
                    or Path(str(row.get("cpk_name") or "")).stem == stem
                    or str(row.get("scene_id") or "") == stem.split("__", 1)[0]
                )
            ),
            {},
        )
    return {
        "file": file_name,
        "ffbe_id": ffbe_id,
        "name": str(source.get("name") or meta.get("speaker_jp") or ""),
        "speaker_ko": str(meta.get("speaker_ko") or ""),
        "source": str(source.get("message") or meta.get("clean_jp") or ""),
        "english": str(meta.get("english_clean") or ""),
        "translation": str(output.get("message") or ""),
        "input_error": input_error,
        "output_error": output_error,
    }


def update_translation_message(
    file_name: str,
    ffbe_id: str,
    message: str,
    project_dir: Path = PROJECT_DIR,
) -> None:
    output_path = project_dir / "gt_output" / file_name
    rows, parse_error = read_json_list(output_path)
    if parse_error:
        raise ValueError(parse_error)
    found = False
    for row in rows:
        if str(row.get("ffbe_id") or "") == str(ffbe_id):
            row["message"] = message
            found = True
            break
    if not found:
        raise KeyError(f"ffbe_id {ffbe_id} does not exist in {output_path}")
    temp_path = output_path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(output_path)


def audit_project(
    project_dir: Path = PROJECT_DIR,
    runtime_dir: Path = RUNTIME_DIR,
    write_snapshot: bool = True,
) -> dict[str, Any]:
    input_dir = project_dir / "gt_input"
    output_dir = project_dir / "gt_output"
    cache_dir = project_dir / "transl_cache"
    csv_dir = project_dir / "csv_exports"
    meta_path = project_dir / "script_meta.json"
    if not meta_path.exists():
        meta_path = project_dir / "chapter1_meta.json"
    config_path = project_dir / "config.yaml"

    runtime_dir.mkdir(parents=True, exist_ok=True)
    ensure_runtime_files(
        runtime_dir / "usage_ledger.jsonl",
        runtime_dir / "pricing.json",
    )
    files: list[FileAudit] = []
    issues: list[Issue] = []
    input_records: dict[str, list[dict[str, Any]]] = {}
    message_counts: Counter[str] = Counter()

    input_files = sorted(input_dir.glob("*.json")) if input_dir.exists() else []
    for input_path in input_files:
        audit = FileAudit(input_path.name, source_hash=file_hash(input_path))
        audit.cache_exists = (cache_dir / input_path.name).exists()
        rows, parse_error = read_json_list(input_path)
        if parse_error:
            issue = Issue("source", "invalid_input_json", input_path.name, detail=parse_error)
            audit.issues.append(issue)
            audit.status = "blocked"
        else:
            input_records[input_path.name] = rows
            _source_entries(input_path.name, rows, audit)
            for row in rows:
                normalized = normalize_text(str(row.get("message") or ""))
                if normalized:
                    message_counts[normalized] += 1
            _audit_output(input_path.name, rows, audit, output_dir)
        files.append(audit)

    meta = _audit_meta(input_records, issues, meta_path)
    for audit in files:
        issues.extend(audit.issues)

    reviews = load_qa_reviews(project_dir)
    accepted_issues = [
        issue for issue in issues if review_key(issue) in reviews
        and reviews[review_key(issue)].get("status") == "accepted"
    ]
    unresolved_issues = [
        issue for issue in issues if review_key(issue) not in reviews
        or reviews[review_key(issue)].get("status") != "accepted"
    ]
    unresolved_types = Counter(issue.type for issue in unresolved_issues)

    for audit in files:
        file_unresolved = [
            issue for issue in audit.issues
            if review_key(issue) not in reviews or reviews[review_key(issue)].get("status") != "accepted"
        ]
        if not file_unresolved and audit.output_exists and not any(issue.type == "missing_translation" for issue in audit.issues):
            audit.status = "translated"

    file_dicts = [audit.as_dict() for audit in files]
    rows_total = sum(item["row_count"] for item in file_dicts)
    rows_completed = sum(item["completed_rows"] for item in file_dicts)
    source_chars = sum(item["source_chars"] for item in file_dicts)
    output_chars = sum(item["output_chars"] for item in file_dicts)
    issue_types = Counter(issue.type for issue in issues)
    source_issue_count = sum(1 for issue in unresolved_issues if issue.scope in {"source", "meta"})
    output_issue_count = sum(1 for issue in unresolved_issues if issue.scope == "output")
    duplicate_message_rows = sum(count - 1 for count in message_counts.values() if count > 1)
    backend = discover_galtransl_backend(ROOT_DIR)
    profile = read_galtransl_profile(config_path)
    usage = summarize_usage(
        runtime_dir / "usage_ledger.jsonl",
        runtime_dir / "pricing.json",
    )

    result = {
        "generated_at": utc_now(),
        "project_dir": str(project_dir.resolve()),
        "summary": {
            "files_total": len(files),
            "files_with_output": sum(1 for item in file_dicts if item["output_exists"]),
            "files_translated": sum(1 for item in file_dicts if item["status"] == "translated"),
            "files_with_warnings": sum(
                1 for item in file_dicts if item["status"] == "qa_warning"
            ),
            "files_blocked": sum(1 for item in file_dicts if item["status"] == "blocked"),
            "files_source_warning": sum(
                1 for item in file_dicts if item["status"] == "source_warning"
            ),
            "files_pending": sum(1 for item in file_dicts if item["status"] == "pending"),
            "rows_total": rows_total,
            "rows_completed": rows_completed,
            "completion_percent": round(rows_completed / rows_total * 100, 2)
            if rows_total
            else 0.0,
            "source_chars": source_chars,
            "output_chars": output_chars,
            "source_issue_count": sum(
                1 for issue in unresolved_issues if issue.scope in {"source", "meta"}
            ),
            "output_issue_count": sum(
                1 for issue in unresolved_issues if issue.scope == "output"
            ),
            "total_issue_count": len(unresolved_issues),
            "accepted_issue_count": len(accepted_issues),
            "unique_source_messages": len(message_counts),
            "duplicate_message_rows": duplicate_message_rows,
            "name_missing": sum(item["name_missing"] for item in file_dicts),
        },
        "input_audit": {
            "files": len(files),
            "rows": rows_total,
            "japanese_rows": sum(item["japanese_rows"] for item in file_dicts),
            "rows_without_japanese": rows_total
            - sum(item["japanese_rows"] for item in file_dicts),
                "parse_errors": unresolved_types.get("invalid_input_json", 0),
                "duplicate_ids": unresolved_types.get("duplicate_ffbe_id", 0),
                "blank_messages": unresolved_types.get("blank_message", 0),
            "missing_names": sum(item["name_missing"] for item in file_dicts),
                "non_japanese_latin": unresolved_types.get("non_japanese_latin_source", 0),
                "neutral_text": unresolved_types.get("neutral_source_text", 0),
            "unique_messages": len(message_counts),
            "duplicate_message_rows": duplicate_message_rows,
        },
        "meta": meta,
        "profile": profile,
        "backend": {"path": str(backend) if backend else "", "exists": bool(backend)},
        "usage": usage,
        "issue_types": dict(sorted(unresolved_types.items())),
        "categories": discover_csv_files(csv_dir),
        "files": file_dicts,
        "issues": [issue.as_dict() for issue in unresolved_issues],
        "accepted_issues": [issue.as_dict() for issue in accepted_issues],
    }
    if write_snapshot:
        state_path = runtime_dir / "project_audit.json"
        temp_path = state_path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(state_path)
        files_csv = runtime_dir / "file_status.csv"
        with files_csv.open("w", encoding="utf-8-sig", newline="") as stream:
            fieldnames = list(file_dicts[0]) if file_dicts else ["file"]
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(file_dicts)
        issues_csv = runtime_dir / "issues.csv"
        with issues_csv.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["scope", "type", "file", "ffbe_id", "detail"],
            )
            writer.writeheader()
            writer.writerows(issue.as_dict() for issue in unresolved_issues)
    return result


def format_summary(result: dict[str, Any]) -> str:
    summary = result["summary"]
    input_audit = result["input_audit"]
    return (
        f"files={summary['files_total']} rows={summary['rows_total']} "
        f"completed={summary['rows_completed']} ({summary['completion_percent']}%) "
        f"input_issues={summary['source_issue_count']} "
        f"output_issues={summary['output_issue_count']} "
        f"japanese_rows={input_audit['japanese_rows']} "
        f"unique_messages={input_audit['unique_messages']}"
    )


def calculate_eta(
    result: dict[str, Any],
    run_state: dict[str, Any],
    now: datetime | None = None,
) -> float | None:
    if run_state.get("status") != "running":
        return None
    started_raw = str(run_state.get("started_at") or "")
    if not started_raw:
        return None
    try:
        started_at = datetime.fromisoformat(started_raw)
    except ValueError:
        return None
    now = now or datetime.now().astimezone()
    elapsed = max(0.0, (now - started_at).total_seconds())
    baseline = int(run_state.get("baseline_rows_completed") or 0)
    completed = int(result["summary"]["rows_completed"])
    total = int(result["summary"]["rows_total"])
    delta = completed - baseline
    if elapsed < 1 or delta <= 0 or completed >= total:
        return None
    seconds_per_row = elapsed / delta
    return seconds_per_row * (total - completed)


def main() -> None:
    result = audit_project()
    print(format_summary(result))
    print(json.dumps(result["input_audit"], ensure_ascii=False, indent=2))
    print(json.dumps(result["usage"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
