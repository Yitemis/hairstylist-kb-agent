# -*- coding: utf-8 -*-
"""端到端业务测试（聚焦每模块的端点验证，不依赖完整 chat 流程）。"""
import sys
import time
import random
import requests

BASE = "http://localhost:8000"


class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"


def check(name: str, cond: bool, detail: str = "") -> None:
    icon = "✅" if cond else "❌"
    color = C.GREEN if cond else C.RED
    msg = f"  {icon} {name}"
    if detail:
        msg += f" — {detail[:100]}"
    print(f"{color}{msg}{C.RESET}")
    if not cond:
        sys.exit(1)


def auth(phone: str, name: str, role: str) -> dict:
    """登录失败则注册。"""
    r = requests.post(f"{BASE}/api/auth/login", json={"phone": phone, "password": "123456", "role": role})
    if r.status_code == 200:
        return r.json()
    r = requests.post(f"{BASE}/api/auth/register", json={"name": name, "phone": phone, "password": "123456", "role": role})
    check(f"注册 {role} {phone}", r.status_code == 200, r.text)
    return r.json()


def main() -> None:
    print(f"\n{C.YELLOW}=== 美发智能助手 E2E 回归测试 ==={C.RESET}\n")

    # ==========================================
    # 0. 健康检查
    # ==========================================
    print("【0. 健康检查】")
    r = requests.get(f"{BASE}/health", timeout=5)
    check("/health", r.status_code == 200, str(r.json()))

    # ==========================================
    # 1. 认证
    # ==========================================
    print("\n【1. 认证】")
    user = auth(f"138{random.randint(10000000, 99999999)}", "e2e_u", "user")
    check("C端 token 拿到", len(user.get("access_token", "")) > 50)
    check("C端 user.id > 0", user["user"]["id"] > 0)

    staff = auth(f"138{random.randint(10000000, 99999999)}", "e2e_s", "staff")
    check("B端 token 拿到", len(staff.get("access_token", "")) > 50)

    # 测试错误：密码错
    r = requests.post(f"{BASE}/api/auth/login", json={"phone": "13800000001", "password": "wrong", "role": "user"})
    check("错误密码被拒绝", r.status_code == 401)

    # 测试错误：手机号格式
    r = requests.post(f"{BASE}/api/auth/register", json={"name": "x", "phone": "123", "password": "123456", "role": "user"})
    check("错误手机号被拒绝", r.status_code == 422 or r.status_code == 400)

    # ==========================================
    # 2. 公共数据
    # ==========================================
    print("\n【2. 公共数据】")
    r = requests.get(f"{BASE}/api/branches")
    check("/api/branches", r.status_code == 200 and len(r.json()) >= 3, f"分店数 {len(r.json())}")
    r = requests.get(f"{BASE}/api/stylists")
    check("/api/stylists", r.status_code == 200 and len(r.json()) >= 4)
    r = requests.get(f"{BASE}/api/services")
    check("/api/services", r.status_code == 200 and len(r.json()) >= 5)

    # ==========================================
    # 3. 我的订单
    # ==========================================
    print("\n【3. 我的订单】")
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    r = requests.get(f"{BASE}/api/orders", headers=headers)
    check("/api/orders", r.status_code == 200)
    check("  返回数据是数组", isinstance(r.json(), list))

    # ==========================================
    # 4. B端管理
    # ==========================================
    print("\n【4. B端管理】")
    staff_h = {"Authorization": f"Bearer {staff['access_token']}"}
    r = requests.get(f"{BASE}/api/admin/orders", headers=staff_h)
    check("/api/admin/orders", r.status_code == 200)

    r = requests.get(f"{BASE}/api/admin/branches", headers=staff_h)
    if r.status_code == 200:
        check("  B端能管分店", True)
    else:
        check("  B端管分店（接口需 401/403）", r.status_code in (401, 403, 405))

    # ==========================================
    # 5. P1：技能库
    # ==========================================
    print("\n【5. P1 技能库】")
    r = requests.get(f"{BASE}/api/skills", headers=headers)
    check("/api/skills", r.status_code == 200 and len(r.json()) >= 4)

    r = requests.post(f"{BASE}/api/skills/search", json={"query": "怎么确认订单"}, headers=headers)
    check("  技能搜索（确认）", len(r.json()["matched"]) > 0)

    r = requests.post(f"{BASE}/api/skills/search", json={"query": "发型师推荐"}, headers=headers)
    check("  技能搜索（推荐）", isinstance(r.json()["matched"], list))

    # ==========================================
    # 6. P1：权限三态
    # ==========================================
    print("\n【6. P1 权限三态】")
    r = requests.post(f"{BASE}/api/permission/evaluate", json={"tool_name": "confirm_order", "tool_args": {}}, headers=headers)
    check("  confirm_order → ASKING", r.json()["decision"] == "asking")
    check("  含 ask_id", "ask_id" in r.json())

    r = requests.post(f"{BASE}/api/permission/evaluate", json={"tool_name": "list_branches", "tool_args": {}}, headers=headers)
    check("  list_branches → ALLOWED", r.json()["decision"] == "allowed")

    r = requests.post(f"{BASE}/api/permission/evaluate", json={"tool_name": "unknown_tool"}, headers=headers)
    check("  未知工具 → ALLOWED（默认）", r.json()["decision"] == "allowed")

    # ==========================================
    # 7. P1：长期记忆
    # ==========================================
    print("\n【7. P1 长期记忆】")
    r = requests.post(f"{BASE}/api/user/facts/extract",
                      json={"user_message": "我住徐汇区，希望找张托尼", "ai_message": "好的"},
                      headers=headers)
    check("  事实提取", r.json()["saved"] >= 2, f"提取={r.json()['extracted']} 保存={r.json()['saved']}")

    r = requests.get(f"{BASE}/api/user/facts", headers=headers)
    check("  列出事实", len(r.json()) >= 2, f"事实数 {len(r.json())}")

    # ==========================================
    # 8. P1：状态持久化
    # ==========================================
    print("\n【8. P1 状态持久化】")
    sess = f"e2e_{int(time.time())}"
    r = requests.post(f"{BASE}/api/chat", json={"message": "你好", "user_id": user["user"]["id"], "session_id": sess}, headers=headers)
    check("  chat 触发", r.status_code == 200)

    r = requests.get(f"{BASE}/api/chat/sessions", headers=headers)
    check("  列出会话", r.status_code == 200)
    s_data = r.json()
    check("  file_sessions 字段存在", "file_sessions" in s_data)

    r = requests.get(f"{BASE}/api/chat/sessions/{sess}/state", headers=headers)
    check("  恢复 session state", r.status_code == 200 and "mode" in r.json())

    # ==========================================
    # 9. RAG 健康检查
    # ==========================================
    print("\n【9. RAG 引擎】")
    r = requests.get(f"{BASE}/api/rag/stats")
    check("/api/rag/stats", r.status_code == 200)
    check("  返回 total_chunks 字段", "total_chunks" in r.json())

    # ==========================================
    # 10. SSE 流式
    # ==========================================
    print("\n【10. SSE 流式】")
    r = requests.post(
        f"{BASE}/api/chat/stream",
        json={"message": "测试 SSE", "user_id": user["user"]["id"], "session_id": "sse_test"},
        headers=headers,
        stream=True, timeout=10,
    )
    check("  /api/chat/stream 状态 200", r.status_code == 200)
    check("  Content-Type 是 text/event-stream", "text/event-stream" in r.headers.get("content-type", ""))
    # 收几个事件（短超时，避免卡住）
    events = []
    try:
        for line in r.iter_lines():
            if not line:
                continue
            s = line.decode("utf-8", errors="ignore")
            if "event:" in s:
                events.append(s.replace("event: ", "").strip())
                if len(events) >= 3:
                    break
    except Exception:
        pass
    check(f"  收到至少 1 个事件", len(events) >= 1, f"事件 {events[:3]}")
    if events:
        check("  第一个事件是 intent", "intent" in events[0], str(events[:1]))

    print(f"\n{C.GREEN}=== 全部回归测试通过 ==={C.RESET}")
    print(f"  用户 ID: {user['user']['id']}")
    print(f"  员工 ID: {staff['user']['id']}")


if __name__ == "__main__":
    main()
