#!/usr/bin/env python3
"""End-to-end smoke test for the Xiaomi-OCR Studio gateway.

Usage (from the project root, with any Python 3.10+ interpreter):

    python scripts/smoke_test.py --sample receipt.jpg
    python scripts/smoke_test.py --file .\\invoice.png --task kie --fields 商户名称 总金额
    python scripts/smoke_test.py --task vqa --sample receipt.jpg --question "总金额是多少？"

The script only talks to the gateway on 127.0.0.1:8787, so start it first:
    python server/app.py
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_CANDIDATES = [ROOT.parent / "Xiaomi-OCR-0", ROOT / "Xiaomi-OCR-0"]


def split_fields(raw: list[str] | None) -> list[str]:
    """Accept "a b", "a,b" or "a、b" and always send a list of field names."""
    fields: list[str] = []
    for chunk in raw or []:
        for part in re.split(r"[,，、;；\n]+", chunk):
            name = part.strip()
            if name:
                fields.append(name)
    return fields


def call(url: str, payload: dict | None = None, timeout: int = 600) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"无法连接网关 {url}：{exc.reason}\n请先运行 python server/app.py") from exc


def sample_path(name: str) -> Path:
    for repo in REPO_CANDIDATES:
        for folder in (repo / "example_pics", repo / "demo" / "samples"):
            candidate = folder / name
            if candidate.is_file():
                return candidate
    raise SystemExit(f"找不到示例图片 {name}，请用 --file 指定路径")


def main() -> None:
    parser = argparse.ArgumentParser(description="Xiaomi-OCR Studio smoke test")
    parser.add_argument("--base", default="http://127.0.0.1:8787")
    parser.add_argument("--task", choices=["ocr", "kie", "vqa", "pdf"], default="ocr")
    parser.add_argument("--mode", choices=["page", "region"], default="page")
    parser.add_argument("--sample", help="bundled example name, e.g. receipt.jpg")
    parser.add_argument("--file", help="local image or pdf path")
    parser.add_argument("--fields", nargs="*", default=None, help="KIE field names")
    parser.add_argument("--question", default="文档的主标题是什么？")
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--save", help="write the raw JSON response here")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    health = call(f"{args.base}/api/health")
    print("health:", json.dumps({k: health[k] for k in ("backend", "model", "modelOnline")}, ensure_ascii=False))
    if not health.get("modelOnline"):
        raise SystemExit("本地模型不在线，请先启动 Ollama / SGLang / vLLM")

    if args.file:
        path = Path(args.file).expanduser().resolve()
    elif args.sample:
        path = sample_path(args.sample)
    else:
        path = sample_path("receipt.jpg")
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode()
    print(f"input: {path.name} ({len(raw) / 1024:.0f} KB) -> {args.task}")

    started = time.perf_counter()
    if args.task == "pdf":
        response = call(
            f"{args.base}/api/pdf",
            {
                "pdf": encoded,
                "mode": args.mode,
                "max_pages": 2,
                "dpi": 150,
                "max_tokens": args.max_tokens,
            },
        )
    elif args.task == "kie":
        response = call(
            f"{args.base}/api/kie",
            {"image": encoded, "fields": split_fields(args.fields), "max_tokens": args.max_tokens},
        )
    elif args.task == "vqa":
        response = call(f"{args.base}/api/vqa", {"image": encoded, "question": args.question})
    else:
        response = call(
            f"{args.base}/api/ocr",
            {"image": encoded, "mode": args.mode, "max_tokens": args.max_tokens},
        )

    wall = time.perf_counter() - started
    print(f"elapsed: {response.get('elapsedMs', 0)} ms (wall {wall:.1f}s)")
    print(f"mode: {response.get('mode')}  regions: {response.get('regions')}  pages: {response.get('pages')}")

    if args.task == "kie":
        print(json.dumps(response.get("json"), ensure_ascii=False, indent=2))
    elif args.task == "vqa":
        print("answer:", response.get("answer"))
    else:
        markdown = response.get("markdown", "")
        print(f"markdown: {len(markdown)} chars")
        print("-" * 60)
        print(markdown[:1200])
        print("-" * 60)

    if args.save:
        Path(args.save).write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved -> {args.save}")

    if not response.get("elapsedMs"):
        raise SystemExit("响应缺少 elapsedMs，网关可能不是本项目版本")
    sys.exit(0)


if __name__ == "__main__":
    main()
