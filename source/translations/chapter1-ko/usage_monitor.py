"""Token, cost, and OpenAI-compatible proxy accounting for translation runs.

The proxy intentionally stores usage metadata only. Prompt and response bodies
are never written to the ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import time_policy


PROJECT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_DIR / "runtime"
DEFAULT_LEDGER_PATH = RUNTIME_DIR / "usage_ledger.jsonl"
DEFAULT_PRICING_PATH = RUNTIME_DIR / "pricing.json"

_LEDGER_LOCK = threading.Lock()
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

DEFAULT_PRICING_MODELS = {
    "deepseek-flash": {
        "peak": {
            "input_per_million": 0.3,
            "cached_input_per_million": 0.006,
            "output_per_million": 1.2,
        },
        "off_peak": {
            "input_per_million": 0.15,
            "cached_input_per_million": 0.003,
            "output_per_million": 0.6,
        },
    },
    "deepseek-v4-pro": {
        "peak": {
            "input_per_million": 1.32,
            "cached_input_per_million": 0.044,
            "output_per_million": 3.96,
        },
        "off_peak": {
            "input_per_million": 0.66,
            "cached_input_per_million": 0.022,
            "output_per_million": 1.98,
        },
    },
}


class UsageProxyProcess:
    """Manage the local accounting proxy as a child of the desktop GUI."""

    def __init__(
        self,
        port: int = 41990,
        upstream: str = "https://api.deepseek.com",
        ledger_path: Path = DEFAULT_LEDGER_PATH,
        pricing_path: Path = DEFAULT_PRICING_PATH,
        router_client: str = "",
    ) -> None:
        self.port = port
        self.upstream = upstream
        self.ledger_path = ledger_path
        self.pricing_path = pricing_path
        self.router_client = router_client
        self.log_path = ledger_path.parent / "usage_proxy.log"
        self.process: subprocess.Popen[str] | None = None
        self._log_stream: Any = None

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self) -> None:
        if self.is_running():
            return
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", self.port)) == 0:
                raise RuntimeError(
                    f"Usage proxy port {self.port} is already in use. "
                    "Stop the previous proxy before starting another."
                )
        ensure_runtime_files(self.ledger_path, self.pricing_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_stream = self.log_path.open("a", encoding="utf-8")
        creation_flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP")
            else 0
        )
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--port",
                str(self.port),
                "--upstream",
                self.upstream,
                "--ledger",
                str(self.ledger_path),
                "--pricing",
                str(self.pricing_path),
                "--router-client",
                self.router_client,
            ],
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creation_flags,
        )
        time.sleep(0.4)
        if self.process.poll() is not None:
            message = self.log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
            raise RuntimeError(f"Usage proxy exited during startup.\n{message}")

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
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


def ensure_runtime_files(
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.touch(exist_ok=True)
    if not pricing_path.exists():
        data: dict[str, Any] = {
            "currency": "USD",
            "source": time_policy.POLICY_SOURCE,
            "checked_at": time_policy.POLICY_CHECKED_AT,
            "models": {},
        }
    else:
        try:
            data = json.loads(pricing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"currency": "USD", "models": {}}
    if not isinstance(data, dict):
        data = {"currency": "USD", "models": {}}
    models = data.setdefault("models", {})
    if not isinstance(models, dict):
        models = {}
        data["models"] = models
    changed = False
    if not data.get("source"):
        data["source"] = time_policy.POLICY_SOURCE
        changed = True
    if not data.get("checked_at"):
        data["checked_at"] = time_policy.POLICY_CHECKED_AT
        changed = True
    for model, rates in DEFAULT_PRICING_MODELS.items():
        if model not in models:
            models[model] = rates
            changed = True
    if changed or not pricing_path.exists():
        pricing_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def load_pricing(path: Path = DEFAULT_PRICING_PATH) -> dict[str, Any]:
    ensure_runtime_files(pricing_path=path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"currency": "USD", "models": {}}
    if not isinstance(data, dict):
        return {"currency": "USD", "models": {}}
    if not isinstance(data.get("models"), dict):
        data["models"] = {}
    return data


def save_model_pricing(
    model: str,
    input_per_million: float | None,
    output_per_million: float | None,
    cached_input_per_million: float | None,
    path: Path = DEFAULT_PRICING_PATH,
) -> dict[str, Any]:
    pricing = load_pricing(path)
    pricing["models"][model] = {
        "input_per_million": input_per_million,
        "output_per_million": output_per_million,
        "cached_input_per_million": cached_input_per_million,
    }
    path.write_text(
        json.dumps(pricing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return pricing


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_rate(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_usage(payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }
    details = payload.get("prompt_tokens_details")
    cached = payload.get("cached_tokens")
    if cached is None and isinstance(details, dict):
        cached = details.get("cached_tokens")
    if cached is None:
        cached = payload.get("prompt_cache_hit_tokens")
    return {
        "prompt_tokens": _as_int(payload.get("prompt_tokens")),
        "completion_tokens": _as_int(payload.get("completion_tokens")),
        "total_tokens": _as_int(payload.get("total_tokens")),
        "cached_tokens": _as_int(cached),
    }


def calculate_cost(
    usage: dict[str, Any],
    model_rates: dict[str, Any],
    period: str | None = None,
) -> float | None:
    if isinstance(model_rates.get("peak"), dict):
        selected_period = period or time_policy.market_clock()["period"]
        selected = model_rates.get(selected_period)
        if isinstance(selected, dict):
            model_rates = selected
    input_rate = _as_rate(model_rates.get("input_per_million"))
    output_rate = _as_rate(model_rates.get("output_per_million"))
    cached_rate = _as_rate(model_rates.get("cached_input_per_million"))
    if input_rate is None or output_rate is None:
        return None

    prompt_tokens = _as_int(usage.get("prompt_tokens"))
    completion_tokens = _as_int(usage.get("completion_tokens"))
    cached_tokens = min(prompt_tokens, _as_int(usage.get("cached_tokens")))
    uncached_tokens = prompt_tokens - cached_tokens
    if cached_rate is None:
        cached_rate = input_rate
    return (
        uncached_tokens * input_rate
        + cached_tokens * cached_rate
        + completion_tokens * output_rate
    ) / 1_000_000


def append_ledger_record(record: dict[str, Any], path: Path = DEFAULT_LEDGER_PATH) -> None:
    ensure_runtime_files(ledger_path=path)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with _LEDGER_LOCK:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())


def summarize_usage(
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
) -> dict[str, Any]:
    pricing = load_pricing(pricing_path)
    rates_by_model = pricing.get("models", {})
    total = {
        "requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "known_cost": 0.0,
        "peak_cost": 0.0,
        "off_peak_cost": 0.0,
        "peak_requests": 0,
        "off_peak_requests": 0,
        "unknown_cost_requests": 0,
    }
    models: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "cost": 0.0,
            "peak_requests": 0,
            "off_peak_requests": 0,
            "unknown_cost_requests": 0,
        }
    )
    malformed_lines = 0

    if not ledger_path.exists():
        records: list[dict[str, Any]] = []
    else:
        records = []
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                malformed_lines += 1
                continue
            if isinstance(item, dict):
                records.append(item)

    for record in records:
        model = str(record.get("model") or "unknown")
        usage = normalize_usage(record.get("usage") if isinstance(record.get("usage"), dict) else record)
        period = str(
            record.get("billing_period")
            or time_policy.period_for_timestamp(record.get("timestamp"))
        )
        model_rates = rates_by_model.get(model)
        if not isinstance(model_rates, dict):
            model_rates = {}
        cost = calculate_cost(usage, model_rates, period)
        status = _as_int(record.get("status", 200))
        success = bool(record.get("success", 200 <= status < 300))

        total["requests"] += 1
        total["successful_requests"] += int(success)
        total["failed_requests"] += int(not success)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens"):
            total[key] += usage[key]
            models[model][key] += usage[key]
        models[model]["requests"] += 1
        if period == "peak":
            total["peak_requests"] += 1
            models[model]["peak_requests"] += 1
        else:
            total["off_peak_requests"] += 1
            models[model]["off_peak_requests"] += 1
        if cost is None:
            total["unknown_cost_requests"] += 1
            models[model]["unknown_cost_requests"] += 1
        else:
            total["known_cost"] += cost
            models[model]["cost"] += cost
            if period == "peak":
                total["peak_cost"] += cost
            else:
                total["off_peak_cost"] += cost

    return {
        "currency": pricing.get("currency", "USD"),
        "requests": total["requests"],
        "successful_requests": total["successful_requests"],
        "failed_requests": total["failed_requests"],
        "prompt_tokens": total["prompt_tokens"],
        "completion_tokens": total["completion_tokens"],
        "total_tokens": total["total_tokens"],
        "cached_tokens": total["cached_tokens"],
        "known_cost": round(total["known_cost"], 8),
        "peak_cost": round(total["peak_cost"], 8),
        "off_peak_cost": round(total["off_peak_cost"], 8),
        "peak_requests": total["peak_requests"],
        "off_peak_requests": total["off_peak_requests"],
        "unknown_cost_requests": total["unknown_cost_requests"],
        "malformed_lines": malformed_lines,
        "models": {name: values for name, values in sorted(models.items())},
        "ledger_path": str(ledger_path),
        "pricing_path": str(pricing_path),
    }


def _filtered_request_headers(
    original_headers: list[tuple[str, str]],
    api_key: str | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in original_headers:
        lower = key.lower()
        if (
            lower in _HOP_BY_HOP_HEADERS
            or lower in {"authorization", "accept-encoding"}
        ):
            continue
        headers[key] = value
    headers["Accept-Encoding"] = "identity"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif original_headers:
        # urllib stores duplicate headers as separate entries. The final value is
        # sufficient for the provider APIs used by GalTransl.
        for key, value in original_headers:
            if key.lower() == "authorization":
                headers["Authorization"] = value
    return headers


def make_proxy_handler(
    upstream: str,
    ledger_path: Path,
    pricing_path: Path,
    api_key: str | None,
    router_client: str = "",
) -> type[BaseHTTPRequestHandler]:
    upstream_root = upstream.rstrip("/")

    class UsageProxyHandler(BaseHTTPRequestHandler):
        server_version = "FFBEUsageProxy/1.0"

        def do_GET(self) -> None:  # noqa: N802
            self._proxy()

        def do_POST(self) -> None:  # noqa: N802
            self._proxy()

        def _proxy(self) -> None:
            started = time.perf_counter()
            length = _as_int(self.headers.get("Content-Length"))
            request_body = self.rfile.read(length) if length else None
            headers = _filtered_request_headers(list(self.headers.items()), api_key)
            if router_client:
                headers = {key: value for key, value in headers.items() if key.lower() != "x-router-client"}
                headers["X-Router-Client"] = router_client
            request = urllib.request.Request(
                upstream_root + self.path,
                data=request_body,
                headers=headers,
                method=self.command,
            )
            status = 502
            response_body = b""
            response_headers: list[tuple[str, str]] = []
            error_text = ""
            model = ""
            request_model = ""
            usage_payload: dict[str, Any] | None = None
            if request_body:
                try:
                    request_json = json.loads(request_body.decode("utf-8"))
                    if isinstance(request_json, dict):
                        request_model = str(request_json.get("model") or "")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass

            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    status = response.status
                    response_body = response.read()
                    response_headers = list(response.headers.items())
            except urllib.error.HTTPError as exc:
                status = exc.code
                response_body = exc.read()
                response_headers = list(exc.headers.items()) if exc.headers else []
                error_text = response_body[:500].decode("utf-8", errors="replace")
            except Exception as exc:  # Network failures should remain visible to GalTransl.
                status = 502
                error_text = f"{type(exc).__name__}: {exc}"
                response_body = error_text.encode("utf-8")

            content_type = ""
            for key, value in response_headers:
                if key.lower() == "content-type":
                    content_type = value
                    break
            if "json" in content_type.lower() and response_body:
                try:
                    decoded = json.loads(response_body.decode("utf-8"))
                    if isinstance(decoded, dict):
                        model = str(decoded.get("model") or request_model)
                        if isinstance(decoded.get("usage"), dict):
                            usage_payload = decoded["usage"]
                        if not error_text and decoded.get("error"):
                            error_text = str(decoded["error"])[:500]
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass

            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            usage = normalize_usage(usage_payload)
            record = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "path": self.path,
                "model": model or request_model or "unknown",
                "status": status,
                "success": 200 <= status < 300,
                "latency_ms": latency_ms,
                "usage": usage,
                "billing_period": time_policy.market_clock()["period"],
                "error": error_text[:500],
            }
            append_ledger_record(record, ledger_path)

            self.send_response(status)
            for key, value in response_headers:
                if key.lower() not in _HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            if not any(key.lower() == "content-type" for key, _ in response_headers):
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[usage-proxy] {self.address_string()} {fmt % args}")

    return UsageProxyHandler


def run_proxy(
    host: str,
    port: int,
    upstream: str,
    ledger_path: Path,
    pricing_path: Path,
    api_key_env: str,
    router_client: str = "",
) -> None:
    ensure_runtime_files(ledger_path, pricing_path)
    api_key = None if router_client else os.environ.get(api_key_env, "").strip() or None
    handler = make_proxy_handler(upstream, ledger_path, pricing_path, api_key, router_client)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Usage proxy listening on http://{host}:{port}/v1")
    print(f"Upstream: {upstream.rstrip('/')}")
    print(f"Ledger: {ledger_path}")
    print(f"API key source: {'environment' if api_key else 'incoming request'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=41990)
    parser.add_argument(
        "--upstream",
        default=os.environ.get("FFBE_UPSTREAM_API", "https://api.deepseek.com"),
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--pricing", type=Path, default=DEFAULT_PRICING_PATH)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--router-client", default="")
    args = parser.parse_args()
    run_proxy(args.host, args.port, args.upstream, args.ledger, args.pricing, args.api_key_env, args.router_client)


if __name__ == "__main__":
    main()
