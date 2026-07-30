# -*- coding: utf-8 -*-
"""表格处理工具：合并单元格展开、大表分窗口、HTML 渲染。

结构化文档中的表格常因两类问题在检索时丢失语义：

1. 合并单元格：解析后边界丢失，行/列的归属关系断裂（例如"连带责任人"
   跨多行合并，展开后子行不再携带该标签）；
2. 大表切分：行数过多时按窗口切块，非首窗口丢失表头，数值失去列含义。

本模块把表格统一表示为二维字符串矩阵 ``rows[r][c]``，提供：

* :func:`expand_merged` —— 把合并区域的值回填到其覆盖的每个单元格；
* :func:`window_rows`   —— 大表按行分窗口，每个窗口强制携带表头；
* :func:`matrix_to_html` —— 矩阵渲染为 HTML 表格。
"""
from __future__ import annotations

from typing import Iterable

# 触发分窗口的行数阈值与每窗口数据行数
LARGE_TABLE_ROW_THRESHOLD = 50
WINDOW_DATA_ROWS = 30


def expand_merged(
    rows: list[list[str]],
    merged_ranges: Iterable[tuple[int, int, int, int]],
) -> list[list[str]]:
    """把合并区域左上角的值回填到区域内所有单元格。

    Args:
        rows: 二维矩阵（行优先），元素为字符串。
        merged_ranges: 合并区域列表，每项 ``(r0, c0, r1, c1)`` 为闭区间的
            起止行列（0 基）。

    Returns:
        回填后的新矩阵（不修改入参）。
    """
    grid = [list(row) for row in rows]
    for r0, c0, r1, c1 in merged_ranges:
        if r0 >= len(grid) or c0 >= len(grid[r0]):
            continue
        anchor = grid[r0][c0]
        for r in range(r0, min(r1, len(grid) - 1) + 1):
            for c in range(c0, c1 + 1):
                if c < len(grid[r]) and not grid[r][c]:
                    grid[r][c] = anchor
    return grid


def window_rows(
    rows: list[list[str]],
    header_rows: int = 1,
    threshold: int = LARGE_TABLE_ROW_THRESHOLD,
    window: int = WINDOW_DATA_ROWS,
) -> list[list[list[str]]]:
    """大表按行分窗口，每个窗口前置表头行。

    行数不超过 ``threshold`` 时整表作为单个窗口返回；否则每 ``window`` 个
    数据行切一窗，窗口开头补上表头行，避免数据行脱离列含义。

    Args:
        rows: 完整矩阵（含表头）。
        header_rows: 表头占用的行数。
        threshold: 超过该行数才分窗口。
        window: 每个窗口的数据行数。

    Returns:
        窗口列表，每个窗口是一个含表头的矩阵。
    """
    if len(rows) <= threshold:
        return [rows]

    header = rows[:header_rows]
    body = rows[header_rows:]
    windows: list[list[list[str]]] = []
    for start in range(0, len(body), window):
        chunk = body[start: start + window]
        windows.append(header + chunk)
    return windows


def matrix_to_html(rows: list[list[str]]) -> str:
    """把矩阵渲染为 HTML 表格。首行作为表头行。"""
    if not rows:
        return "<table></table>"

    def _row(cells: list[str], tag: str) -> str:
        return "<tr>" + "".join(f"<{tag}>{_escape(c)}</{tag}>" for c in cells) + "</tr>"

    head = _row(rows[0], "th")
    body = "".join(_row(r, "td") for r in rows[1:])
    return f"<table>{head}{body}</table>"


def _escape(text: str) -> str:
    """最小化 HTML 转义。"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
