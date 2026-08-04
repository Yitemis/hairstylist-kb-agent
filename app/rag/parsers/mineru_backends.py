# -*- coding: utf-8 -*-
"""MinerU multi-backend client. Default: local pipeline (CPU)."""
from __future__ import annotations
import logging, os, time, base64
from abc import ABC, abstractmethod
from typing import List, Optional
logger = logging.getLogger(__name__)


class MinerUBackend(ABC):
    @abstractmethod
    def parse(self, binary, filename):
        pass
    @property
    @abstractmethod
    def name(self):
        pass


class MinerUCloudBackend(MinerUBackend):
    API_BASE = "https://mineru.net/api/v4"
    DAILY_FREE_QUOTA = 1000

    def __init__(self, token):
        if not token:
            raise ValueError("MINERU_API_TOKEN not set")
        self.token = token
        self.h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @property
    def name(self):
        return f"mineru-cloud (mineru.net, {self.DAILY_FREE_QUOTA} pages/day free)"

    def parse(self, binary, filename):
        import requests
        try:
            t0 = time.time()
            r = requests.post(f"{self.API_BASE}/file-urls/batch", headers=self.h, json={"enable_formula": True, "enable_table": True, "language": "ch", "is_ocr": True, "files": [{"name": filename, "is_ocr": True, "data_id": f"{filename}-{int(time.time())}"}]}, timeout=30)
            p = r.json()
            if r.status_code != 200 or not p.get("success"):
                return []
            data = p.get("data") or {}
            batch_id = data.get("batch_id")
            urls = data.get("file_urls", [])
            if not batch_id or not urls:
                return []
            upload_url = urls[0]
            logger.info(f"MinerU cloud: applied URL batch_id={batch_id} {time.time()-t0:.2f}s")
            t1 = time.time()
            put = requests.put(upload_url, headers={"Content-Type": "application/pdf"}, data=binary, timeout=180)
            if put.status_code not in (200, 204):
                return []
            logger.info(f"MinerU cloud: uploaded {time.time()-t1:.2f}s")
            return self._poll(batch_id, 300)
        except Exception as e:
            logger.warning(f"MinerU cloud failed: {e}")
            return []

    def _poll(self, batch_id, timeout):
        import requests
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = requests.get(f"{self.API_BASE}/extract-results/batch/{batch_id}", headers=self.h, timeout=30)
                p = r.json()
                if r.status_code == 200 and p.get("success"):
                    results = (p.get("data") or {}).get("extract_result", [])
                    if results:
                        first = results[0]
                        state = first.get("state")
                        if state == "done":
                            md = first.get("markdown_content") or first.get("content", "")
                            if md:
                                logger.info(f"MinerU cloud: parsed {time.time()-start:.2f}s {len(md)} chars")
                                return [md]
                        elif state == "failed":
                            return []
            except Exception:
                pass
            time.sleep(5)
        return []


class MinerUHttpBackend(MinerUBackend):
    def __init__(self, base_url, api_key=""):
        if not base_url:
            raise ValueError("MINERU_HTTP_URL not set")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    @property
    def name(self):
        return f"mineru-http ({self.base_url})"

    def parse(self, binary, filename):
        import requests
        try:
            b64 = base64.b64encode(binary).decode("utf-8")
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            payload = {"model": "mineru", "messages": [{"role": "user", "content": [{"type": "text", "text": "Parse PDF to Markdown"}, {"type": "file", "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{b64}"}}]}], "temperature": 0}
            r = requests.post(f"{self.base_url}/v1/chat/completions", headers=headers, json=payload, timeout=300)
            if r.status_code != 200:
                return []
            content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return [content]
            return []
        except Exception as e:
            logger.warning(f"MinerU http failed: {e}")
            return []


class MinerULocalBackend(MinerUBackend):
    """Default local pipeline (CPU, 86.47 accuracy). Install: pip install -U mineru[all]"""
    def __init__(self):
        try:
            from mineru.cli.client import parse_pdf
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("mineru[all] not installed, local pipeline unavailable, will fallback to PyMuPDF")

    @property
    def name(self):
        return "mineru-local-pipeline (CPU, 86.47 accuracy, default)"

    def parse(self, binary, filename):
        if not self._available:
            return []
        try:
            from mineru.cli.client import parse_pdf
            import tempfile
            from pathlib import Path
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="mineru_") as tmp:
                tmp.write(binary)
                tmp_path = tmp.name
            try:
                with tempfile.TemporaryDirectory() as out_dir:
                    t0 = time.time()
                    parse_pdf(input_path=tmp_path, output_dir=out_dir, backend="pipeline", parse_method="auto")
                    md_files = list(Path(out_dir).rglob("*.md"))
                    if md_files:
                        md = md_files[0].read_text(encoding="utf-8")
                        if md:
                            logger.info(f"MinerU local pipeline: parsed {time.time()-t0:.2f}s {len(md)} chars")
                            return [md]
                return []
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"MinerU local pipeline failed: {e}")
            return []


_cache = None


def get_mineru_backend():
    global _cache
    if _cache is not None:
        return _cache
    btype = os.environ.get("MINERU_BACKEND", "local").lower()
    if btype == "cloud":
        _cache = MinerUCloudBackend(os.environ.get("MINERU_API_TOKEN", ""))
    elif btype == "http":
        _cache = MinerUHttpBackend(os.environ.get("MINERU_HTTP_URL", ""), os.environ.get("MINERU_HTTP_KEY", ""))
    elif btype == "local":
        _cache = MinerULocalBackend()
    else:
        logger.warning(f"Unknown MINERU_BACKEND={btype}, fallback to local")
        _cache = MinerULocalBackend()
    logger.info(f"MinerU backend: {_cache.name}")
    return _cache


def reset_mineru_backend():
    global _cache
    _cache = None
