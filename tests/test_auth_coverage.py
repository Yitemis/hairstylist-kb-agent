# -*- coding: utf-8 -*-
"""55 端点鉴权覆盖测试 (P1-1 全覆盖验收)。

策略: 静态 AST 扫描所有 routers/*.py 中带 @router.X 装饰的函数,
确保每个端点都有 Depends(get_current_user/require_user/require_staff),
除白名单。

这是"防搬代码漏鉴权"的最后一道闸 - 任何新增端点不带 auth 都会 fail。
"""
import ast
from pathlib import Path
import pytest


# 白名单: 不需要鉴权的端点 (公开接口)
WHITELIST = {
    # 公开认证
    ("/api/auth/register", "POST"),
    ("/api/auth/login", "POST"),
    ("/api/auth/staff/login", "POST"),
    # 公开浏览 (C 端消费者无需登录就能查询门店/服务/发型师/可用时段)
    ("/api/branches", "GET"),
    ("/api/branches/nearby", "GET"),
    ("/api/services", "GET"),
    ("/api/stylists", "GET"),
    ("/api/orders/available-slots", "GET"),
}


def _get_router_decorators(filepath):
    """从一个 routers/*.py 文件中提取所有 @router.X 装饰的 endpoint 签名。"""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not isinstance(func, ast.Attribute):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "router"):
                continue
            method = func.attr.upper()
            if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                continue
            if not dec.args:
                continue
            path_arg = dec.args[0]
            if not isinstance(path_arg, ast.Constant):
                continue
            path = path_arg.value
            # 处理 router prefix (从源码中读 APIRouter(prefix=...))
            full_path = _resolve_prefix(filepath) + path
            has_auth = False
            for ann in node.args.args:
                ann_str = ast.unparse(ann.annotation) if ann.annotation else ""
                if any(s in ann_str for s in ("get_current_user", "require_staff", "require_user")):
                    has_auth = True
                    break
            for dep_str in [ast.unparse(d) for d in node.args.defaults]:
                if any(s in dep_str for s in ("get_current_user", "require_staff", "require_user")):
                    has_auth = True
                    break
            for d in node.args.kw_defaults:
                if d is None:
                    continue
                dep_str = ast.unparse(d)
                if any(s in dep_str for s in ("get_current_user", "require_staff", "require_user")):
                    has_auth = True
                    break
            results.append({
                "file": filepath.name,
                "func": node.name,
                "method": method,
                "path": full_path,
                "has_auth": has_auth,
            })
    return results


def _resolve_prefix(filepath):
    """从 routers/<name>.py 读 router = APIRouter(prefix=...) 的 prefix。"""
    src = filepath.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "router":
                    if isinstance(node.value, ast.Call):
                        for kw in node.value.keywords:
                            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                return kw.value.value
    return ""


def test_all_endpoints_have_auth():
    """P1-1: 扫描所有 routers/, 验证每个端点都有 auth (除白名单)。"""
    routers_dir = Path("app/server/routers")
    issues = []
    total = 0
    with_auth = 0
    public = 0

    for f in sorted(routers_dir.glob("*.py")):
        if f.name == "__init__.py":
            continue
        endpoints = _get_router_decorators(f)
        for ep in endpoints:
            total += 1
            key = (ep["path"], ep["method"])
            if key in WHITELIST:
                public += 1
                continue
            if ep["has_auth"]:
                with_auth += 1
            else:
                issues.append(f"  {ep['file']}:{ep['func']}  {ep['method']} {ep['path']}  无 auth")

    print(f"\n=== 鉴权覆盖统计 ===")
    print(f"总端点数: {total}")
    print(f"有鉴权: {with_auth}")
    print(f"公开 (白名单): {public}")
    print(f"漏鉴权: {len(issues)}")

    if issues:
        msg = "以下端点缺鉴权 (N12 防搬代码漏鉴权):\n" + "\n".join(issues)
        pytest.fail(msg)


def test_auth_whitelist_actually_works():
    """白名单端点确实存在。"""
    routers_dir = Path("app/server/routers")
    all_endpoints = set()
    for f in sorted(routers_dir.glob("*.py")):
        if f.name == "__init__.py":
            continue
        for ep in _get_router_decorators(f):
            all_endpoints.add((ep["path"], ep["method"]))

    for path, method in WHITELIST:
        assert (path, method) in all_endpoints, f"白名单端点 {method} {path} 不存在"


def test_count_at_least_40_endpoints():
    """至少 40 个业务端点 (防 router 全空)。"""
    routers_dir = Path("app/server/routers")
    total = 0
    for f in sorted(routers_dir.glob("*.py")):
        if f.name == "__init__.py":
            continue
        total += len(_get_router_decorators(f))
    assert total >= 40, f"端点总数 {total} < 40 (router 拆分丢失端点?)"
    print(f"\n总端点: {total}")
