# -*- coding: utf-8 -*-
"""解析器公共工具：token 计数、文本读取、URL 安全校验、文件下载。"""
from __future__ import annotations

import ipaddress
import logging
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Token 计数：优先 tiktoken，缺省降级为近似（utf-8 字节数 // 4）
# 降级算法与 rag/chunkers/parent_child_chunker.py 保持一致。
# ------------------------------------------------------------------

_encoder = None
try:  # pragma: no cover - 依赖是否安装决定分支
    import tiktoken

    _encoder = tiktoken.get_encoding("cl100k_base")
except Exception:  # noqa: BLE001
    _encoder = None


def num_tokens_from_string(string: str) -> int:
    """返回文本的 token 数。"""
    if not string:
        return 0
    if _encoder is not None:
        try:
            return len(_encoder.encode(string))
        except Exception:  # noqa: BLE001
            pass
    return len(string.encode("utf-8")) // 4


# ------------------------------------------------------------------
# 文本读取
# ------------------------------------------------------------------


def get_text(file_path: str | Path, binary: bytes | None = None) -> str:
    """读取文本内容（支持文件路径或二进制）。"""
    try:
        if binary is not None:
            encoding = _detect_encoding(binary)
            return binary.decode(encoding, errors="ignore")
        return Path(file_path).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        logger.error("读取文本失败: %s", e)
        return ""


def _detect_encoding(binary: bytes) -> str:
    """探测二进制内容的字符编码。"""
    try:
        import chardet

        result = chardet.detect(binary)
        return result.get("encoding") or "utf-8"
    except Exception:  # noqa: BLE001
        return "utf-8"


# ------------------------------------------------------------------
# URL 安全校验（防 SSRF）与下载
# ------------------------------------------------------------------


def is_safe_url(url: str) -> bool:
    """判断是否为安全的可下载 URL（http/https 且非内网地址）。"""
    try:
        parsed = urlsplit(url)
    except Exception:  # noqa: BLE001
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = (parsed.hostname or "").lower()
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except ValueError:
        pass  # 是域名，放行

    return True


def download_file(url: str, max_size: int = 20 * 1024 * 1024) -> bytes:
    """下载文件并限制最大大小。"""
    import requests

    response = requests.get(url, stream=True, timeout=15)
    response.raise_for_status()

    content = b""
    downloaded = 0
    for chunk in response.iter_content(chunk_size=8192):
        content += chunk
        downloaded += len(chunk)
        if downloaded > max_size:
            raise ValueError(f"文件超出大小限制: {url}")
    return content
