"""Local API gateway for Xiaomi-OCR-0 Studio.

Design notes
------------
* No third-party Python packages: the gateway runs on the Python standard
  library so it works inside the existing Xiaomi-OCR-0 MCP virtualenv.
* All model work is delegated to the official MCP engine module
  (``skills/xiaomi-ocr/mcp_ocr_server.py``) which owns image normalization,
  prompts, layout detection, cropping and post-processing. This keeps the web
  app honest: identical prompts and identical output formatting as the CLI.
* Only a loopback inference server is contacted (Ollama / SGLang / vLLM).
* Inference is serialized behind a lock because the default target is a CPU
  Ollama instance, where parallel requests only inflate memory use.

Endpoints
---------
GET  /api/health              service + model + capability probe
GET  /api/samples             bundled example images
GET  /api/samples/{name}      one example image
POST /api/ocr                 {image, mode, max_tokens}
POST /api/kie                 {image, fields[], max_tokens}
POST /api/vqa                 {image, question}
POST /api/pdf                 {pdf, mode, max_pages, dpi, max_tokens}
GET  /*                       built SPA (dist/) with history fallback
"""

from __future__ import annotations

import base64
import importlib.util
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DEFAULT_REPO = PROJECT_DIR.parent / "Xiaomi-OCR-0"
DIST_DIR = PROJECT_DIR / "dist"

REPO = Path(os.environ.get("XIAOMI_OCR_REPO", DEFAULT_REPO)).expanduser().resolve()
ENDPOINT = os.environ.get("XIAOMI_OCR_LOCAL_URL", "http://127.0.0.1:11434/v1").rstrip("/")
MODEL = os.environ.get("XIAOMI_OCR_MODEL", "longwayxu/xiaomi-ocr-0:bf16")
BACKEND = os.environ.get("XIAOMI_OCR_BACKEND", "ollama")
MCP_ENTRY = REPO / "skills" / "xiaomi-ocr" / "mcp_ocr_server.py"
MAX_BYTES = int(os.environ.get("XIAOMI_OCR_MAX_UPLOAD_MB", "30")) * 1024 * 1024
MAX_BODY = MAX_BYTES * 2 + 2 * 1024 * 1024
HOST = os.environ.get("XIAOMI_OCR_HOST", "0.0.0.0")
PORT = int(os.environ.get("XIAOMI_OCR_PORT", "8787"))
SAMPLE_DIRS = [REPO / "example_pics", REPO / "demo" / "samples"]
SAMPLE_LABELS = {
    "receipt.jpg": "AA 收据小票",
    "dense-equations.jpg": "密集公式论文",
    "handwrite-formula.jpg": "手写公式",
    "qianziwen.jpeg": "千字文书法",
    "sample_document.png": "示例文档",
    "sample_kie.png": "示例证件",
    "sample_vqa.png": "示例问答图",
}

# The engine module reads its configuration at import time.
os.environ.setdefault("XIAOMI_OCR_REPO", str(REPO))
os.environ.setdefault("XIAOMI_OCR_LOCAL_URL", ENDPOINT)
os.environ.setdefault("XIAOMI_OCR_MODEL", MODEL)

_engine = None
_engine_error: str | None = None
_engine_lock = threading.Lock()
_infer_lock = threading.Lock()


class ApiError(Exception):
    def __init__(self, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


# --------------------------------------------------------------------------- engine
def get_engine():
    """Import the official MCP engine exactly once."""
    global _engine, _engine_error
    with _engine_lock:
        if _engine is not None:
            return _engine
        if _engine_error is not None:
            raise ApiError(_engine_error, 503)
        try:
            if not MCP_ENTRY.is_file():
                raise RuntimeError(f"找不到 Xiaomi-OCR-0 MCP 引擎: {MCP_ENTRY}")
            if str(REPO) not in sys.path:
                sys.path.insert(0, str(REPO))
            spec = importlib.util.spec_from_file_location("xiaomi_ocr_mcp_engine", MCP_ENTRY)
            if spec is None or spec.loader is None:
                raise RuntimeError("无法加载 MCP 引擎模块")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _engine = module
            return module
        except Exception as exc:  # pragma: no cover - environment surface
            _engine_error = f"{type(exc).__name__}: {exc}"
            raise ApiError(f"引擎加载失败：{_engine_error}", 503)


def model_online(timeout: float = 2.5) -> bool:
    try:
        request = urllib.request.Request(f"{ENDPOINT}/models", headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            json.loads(response.read())
        return True
    except Exception:
        return False


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def layout_model_ready() -> bool:
    """Region mode needs both PaddleX and the PP-DocLayoutV3 weights on disk.

    PaddleX can fetch the weights on first use, but that download is hundreds of
    megabytes and often unavailable offline, so we only advertise region mode
    when the weights are already cached (or explicitly configured).
    """
    explicit = os.environ.get("XIAOMI_OCR_LAYOUT_MODEL_DIR")
    if explicit:
        return Path(explicit).expanduser().is_dir()
    if not has_module("paddlex"):
        return False
    cache = Path(os.environ.get("PADDLE_PDX_CACHE_HOME", Path.home() / ".paddlex"))
    models = cache / "official_models"
    if not models.is_dir():
        return False
    try:
        entries = list(models.iterdir())
    except OSError:
        return False
    for entry in entries:
        if entry.is_dir() and "doclayout" in entry.name.lower():
            try:
                return any(entry.iterdir())
            except OSError:
                continue
    return False


# --------------------------------------------------------------------------- helpers
def decode_payload(payload: str, kind: str) -> str:
    if not isinstance(payload, str) or not payload.strip():
        raise ApiError(f"请提供{kind}数据", 400)
    raw = payload.split(",", 1)[1] if payload.startswith("data:") else payload
    compact = "".join(raw.split())
    if not compact:
        raise ApiError(f"请提供{kind}数据", 400)
    if len(compact) * 3 // 4 > MAX_BYTES:
        raise ApiError(f"{kind}超过 {MAX_BYTES // (1024 * 1024)}MB 限制", 413)
    try:
        base64.b64decode(compact)
    except Exception as exc:
        raise ApiError(f"{kind}数据不是有效的 base64", 400) from exc
    return compact


def as_int(data: dict, key: str, default: int, low: int, high: int) -> int:
    value = data.get(key, default)
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(f"参数 {key} 必须是整数", 400) from exc
    if number < low or number > high:
        raise ApiError(f"参数 {key} 需要在 {low}..{high} 之间", 400)
    return number


def as_mode(data: dict) -> str:
    mode = str(data.get("mode", "page") or "page")
    if mode not in {"page", "region"}:
        raise ApiError("mode 只能是 page 或 region", 400)
    return mode


def run_engine(fn, **kwargs) -> dict:
    started = time.perf_counter()
    with _infer_lock:
        try:
            result = fn(**kwargs)
        except ApiError:
            raise
        except RuntimeError as exc:
            raise ApiError(str(exc), 502) from exc
        except Exception as exc:  # pragma: no cover - defensive
            traceback.print_exc()
            raise ApiError(f"{type(exc).__name__}: {exc}", 500) from exc
    if not isinstance(result, dict):
        result = {"markdown": str(result)}
    result["elapsedMs"] = round((time.perf_counter() - started) * 1000)
    return result


def sample_index() -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for directory in SAMPLE_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            if path.name in seen:
                continue
            seen.add(path.name)
            items.append(
                {
                    "name": path.name,
                    "label": SAMPLE_LABELS.get(path.name, path.stem),
                    "url": f"/api/samples/{path.name}",
                }
            )
    return items


def find_sample(name: str) -> Path | None:
    safe = Path(name).name
    for directory in SAMPLE_DIRS:
        candidate = (directory / safe).resolve()
        if candidate.is_file() and candidate.parent == directory.resolve():
            return candidate
    return None


# --------------------------------------------------------------------------- handlers
class Handler(BaseHTTPRequestHandler):
    server_version = "XiaomiOCRStudio/0.1"
    protocol_version = "HTTP/1.1"

    # -- output ------------------------------------------------------------
    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, cache: bool = True) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self.send_json(404, {"detail": "文件不存在"})
            return
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() in {".js", ".mjs"}:
            mime = "text/javascript; charset=utf-8"
        elif path.suffix.lower() == ".css":
            mime = "text/css; charset=utf-8"
        elif path.suffix.lower() == ".svg":
            mime = "image/svg+xml"
        elif path.suffix.lower() == ".html":
            mime = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if cache else "no-cache")
        self.cors()
        self.end_headers()
        self.wfile.write(data)

    def cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- reading -----------------------------------------------------------
    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            raise ApiError("请求体为空", 400)
        if length > MAX_BODY:
            raise ApiError(f"请求体超过 {MAX_BODY // (1024 * 1024)}MB 限制", 413)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ApiError("请求体不是合法的 JSON", 400) from exc
        if not isinstance(data, dict):
            raise ApiError("请求体必须是 JSON 对象", 400)
        return data

    # -- routing -----------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/health":
                self.handle_health()
                return
            if path == "/api/samples":
                self.send_json(200, {"items": sample_index()})
                return
            if path.startswith("/api/samples/"):
                found = find_sample(path[len("/api/samples/") :])
                if found is None:
                    self.send_json(404, {"detail": "示例不存在"})
                    return
                self.send_file(found)
                return
            if path.startswith("/api/"):
                self.send_json(404, {"detail": f"未知接口 {path}"})
                return
            self.serve_spa(path)
        except ApiError as exc:
            self.send_json(exc.status, {"detail": exc.detail})
        except BrokenPipeError:
            return
        except Exception:  # pragma: no cover - defensive
            traceback.print_exc()
            self.send_json(500, {"detail": "服务内部错误"})

    def do_POST(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        try:
            data = self.read_json()
            if path == "/api/ocr":
                self.handle_ocr(data)
            elif path == "/api/kie":
                self.handle_kie(data)
            elif path == "/api/vqa":
                self.handle_vqa(data)
            elif path == "/api/pdf":
                self.handle_pdf(data)
            else:
                self.send_json(404, {"detail": f"未知接口 {path}"})
        except ApiError as exc:
            self.send_json(exc.status, {"detail": exc.detail})
        except BrokenPipeError:
            return
        except Exception:  # pragma: no cover - defensive
            traceback.print_exc()
            self.send_json(500, {"detail": "服务内部错误"})

    # -- API ---------------------------------------------------------------
    def handle_health(self) -> None:
        region_ready = layout_model_ready()
        pdf_ready = has_module("pypdfium2")
        engine_ok = True
        engine_error = None
        try:
            get_engine()
        except ApiError as exc:
            engine_ok = False
            engine_error = exc.detail
        self.send_json(
            200,
            {
                "ok": engine_ok,
                "backend": BACKEND,
                "endpoint": ENDPOINT,
                "model": MODEL,
                "repo": str(REPO),
                "engineReady": engine_ok,
                "engineError": engine_error,
                "modelOnline": model_online(),
                "capabilities": {
                    "page": engine_ok,
                    "region": engine_ok and region_ready,
                    "kie": engine_ok,
                    "vqa": engine_ok,
                    "pdf": engine_ok and pdf_ready,
                },
                "regionHint": None
                if region_ready
                else "区域模式需要本地 PP-DocLayoutV3 版面权重：首次使用由 PaddleX 自动下载（约 100MB），离线环境可用 XIAOMI_OCR_LAYOUT_MODEL_DIR 指定权重目录。其余能力不受影响。",
            },
        )

    def handle_ocr(self, data: dict) -> None:
        image = decode_payload(data.get("image", ""), "图片")
        mode = as_mode(data)
        max_tokens = as_int(data, "max_tokens", 2048, 256, 8192)
        engine = get_engine()
        result = run_engine(engine.ocr_image, image_base64=image, mode=mode, max_tokens=max_tokens)
        self.send_json(
            200,
            {
                "ok": True,
                "kind": "document",
                "mode": result.get("mode", mode),
                "markdown": result.get("markdown", ""),
                "usage": result.get("usage"),
                "regions": result.get("regions"),
                "reason": result.get("reason"),
                "elapsedMs": result.get("elapsedMs"),
            },
        )

    def handle_kie(self, data: dict) -> None:
        image = decode_payload(data.get("image", ""), "图片")
        fields = data.get("fields") or []
        if not isinstance(fields, list):
            raise ApiError("fields 必须是字符串数组", 400)
        fields = [str(field).strip() for field in fields if str(field).strip()][:20]
        max_tokens = as_int(data, "max_tokens", 2048, 256, 8192)
        engine = get_engine()
        result = run_engine(engine.kie_image, image_base64=image, fields=fields or None, max_tokens=max_tokens)
        self.send_json(
            200,
            {
                "ok": True,
                "kind": "kie",
                "json": result.get("json"),
                "raw": result.get("raw"),
                "warning": result.get("warning"),
                "elapsedMs": result.get("elapsedMs"),
            },
        )

    def handle_vqa(self, data: dict) -> None:
        image = decode_payload(data.get("image", ""), "图片")
        question = str(data.get("question", "")).strip()
        if not question:
            raise ApiError("请先输入问题", 400)
        if len(question) > 2000:
            raise ApiError("问题过长，请控制在 2000 字符以内", 400)
        engine = get_engine()
        result = run_engine(engine.vqa_image, image_base64=image, question=question)
        self.send_json(
            200,
            {
                "ok": True,
                "kind": "vqa",
                "answer": result.get("answer", ""),
                "question": question,
                "elapsedMs": result.get("elapsedMs"),
            },
        )

    def handle_pdf(self, data: dict) -> None:
        payload = decode_payload(data.get("pdf", ""), "PDF")
        mode = as_mode(data)
        max_pages = as_int(data, "max_pages", 3, 1, 50)
        dpi = as_int(data, "dpi", 150, 72, 300)
        max_tokens = as_int(data, "max_tokens", 2048, 256, 8192)
        engine = get_engine()
        result = run_engine(
            engine.ocr_pdf,
            pdf_base64=payload,
            mode=mode,
            max_pages=max_pages,
            dpi=dpi,
            max_tokens=max_tokens,
        )
        self.send_json(
            200,
            {
                "ok": True,
                "kind": "document",
                "mode": result.get("mode", mode),
                "pages": result.get("pages"),
                "markdown": result.get("markdown", ""),
                "elapsedMs": result.get("elapsedMs"),
            },
        )

    # -- static SPA --------------------------------------------------------
    def serve_spa(self, path: str) -> None:
        index = DIST_DIR / "index.html"
        if not index.is_file():
            self.send_json(503, {"detail": "前端尚未构建，请先运行 npm run build，或用 npm run dev 启动开发服务器"})
            return
        relative = path.lstrip("/")
        if relative:
            candidate = (DIST_DIR / relative).resolve()
            try:
                inside = candidate.is_relative_to(DIST_DIR)
            except AttributeError:  # Python < 3.9
                inside = str(candidate).startswith(str(DIST_DIR))
            if inside and candidate.is_file():
                self.send_file(candidate)
                return
        self.send_file(index, cache=False)


def main() -> None:
    print("[xiaomi-ocr] Xiaomi-OCR Studio API")
    print(f"[xiaomi-ocr] repo     = {REPO}")
    print(f"[xiaomi-ocr] engine   = {MCP_ENTRY}")
    print(f"[xiaomi-ocr] backend  = {BACKEND}  model = {MODEL}")
    print(f"[xiaomi-ocr] endpoint = {ENDPOINT}")
    print(f"[xiaomi-ocr] dist     = {DIST_DIR} ({'found' if (DIST_DIR / 'index.html').is_file() else 'not built'})")
    print(f"[xiaomi-ocr] listen   = http://{HOST}:{PORT}")
    try:
        get_engine()
        print("[xiaomi-ocr] engine   = loaded")
    except ApiError as exc:
        print(f"[xiaomi-ocr] engine   = FAILED: {exc.detail}")
    print(f"[xiaomi-ocr] model    = {'online' if model_online() else 'offline'}")
    ThreadingHTTPServer.daemon_threads = True
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[xiaomi-ocr] stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
