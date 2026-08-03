# -*- coding: utf-8 -*-
"""解析器工具：SSRF 防护 + 限流下载 + 编码检测。

借鉴 ekbs-ai-service，关键安全：
- is_safe_url 防止 SSRF（不允许 localhost、私有 IP、危险协议）
- download_file 流式 + 限流 防 OOM
- find_codec 自动检测文件编码
"""
from __future__ import annotations

import ipaddress
import logging
import re
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)


def is_safe_url(url: str) -> bool:
    """检查 URL 是否安全，防止 SSRF 攻击。

    拦截：
    - 非 http/https 协议
    - localhost / 127.0.0.1 / ::1
    - 私有 IP（10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16）
    - loopback / link-local
    """
    try:
        parsed = urlsplit(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.scheme in ("file", "gopher", "ftp"):
        return False
    hostname = (parsed.hostname or "").lower()
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except ValueError:
        pass
    return True


def download_file(url: str, max_size: int = 200 * 1024 * 1024, timeout: int = 60) -> bytes:
    """流式下载文件，限制最大大小防止 OOM。

    Args:
        url: 文件 URL（必须先过 is_safe_url）
        max_size: 最大下载字节（默认 200MB）
        timeout: 超时秒数
    Returns:
        文件二进制内容
    Raises:
        ValueError: 文件超出大小限制
    """
    response = requests.get(url, stream=True, timeout=timeout)
    response.raise_for_status()
    chunks = []
    downloaded = 0
    for chunk in response.iter_content(chunk_size=4096):
        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)
            if downloaded > max_size:
                raise ValueError(f"文件超出大小限制 {max_size} bytes: {url}")
    return b"".join(chunks)


def detect_encoding(file_bytes: bytes) -> str:
    """自动检测文件编码。"""
    try:
        import chardet
        result = chardet.detect(file_bytes[:8192])
        encoding = result.get("encoding") or "utf-8"
        return encoding
    except ImportError:
        # 简单启发式
        if file_bytes.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if file_bytes.startswith(b"\xff\xfe") or file_bytes.startswith(b"\xfe\xff"):
            return "utf-16"
        try:
            file_bytes.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            return "gbk"
