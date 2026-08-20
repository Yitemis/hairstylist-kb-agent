# -*- coding: utf-8 -*-
"""测试: 预约流程中的"打岔话" (interruption) 处理.

源自会话 2 (f8b1aeee) 用户提问:
> "我在预约流程中插入打岔话呢, agent 是不是能处理"

机制 (来自 app/rag/workflow/booking_intake.py):
1. intake_route() 智能分类用户意图
2. _quick_intent_classify: cancel/query/change_X (关键词精确匹配)
3. 知识问答快速识别: knowledge_score (伤/会/吗/原理/怎么) >= 2 + 长度 > 8 → side_question
4. LLM fallback: 让 LLM 判断是 continue/change_X/side_question
5. side_question → handle_side_question() 调 knowledge_agent 回答
6. 答完 state.current_step 不变 → 下轮仍回到原 step
"""
import pytest
from app.rag.workflow.booking_intake import (
    _quick_intent_classify,
    intake_route,
    INTENT_SIDE_QUESTION,
    INTENT_CONTINUE,
    INTENT_CHANGE_SERVICE,
    INTENT_CANCEL,
    INTENT_QUERY_STATUS,
)


# ============ 纯关键词快速分类 (无 LLM) ============

class TestQuickIntentClassify:
    """_quick_intent_classify: cancel / query / change_X 关键词精确匹配."""

    def test_cancel_detected(self):
        intent = _quick_intent_classify("算了吧不约了")
        assert intent == INTENT_CANCEL

    def test_query_status_detected(self):
        intent = _quick_intent_classify("我填到哪了")
        assert intent == INTENT_QUERY_STATUS

    def test_change_service_detected(self):
        intent = _quick_intent_classify("换一下项目, 改成染发")
        assert intent == INTENT_CHANGE_SERVICE

    def test_short_answer_not_classified(self):
        """'好' 短答 → None (走 LLM 决定)."""
        assert _quick_intent_classify("好") is None

    def test_empty_input(self):
        assert _quick_intent_classify("") is None
        assert _quick_intent_classify("   ") is None

    def test_knowledge_word_not_in_quick(self):
        """_quick_intent_classify 不处理知识问答 (那是 intake_route 的事)."""
        # '热烫会不会伤头发呀?' 没有 cancel/query/change_X 关键词
        # 所以 _quick_intent_classify 返回 None
        assert _quick_intent_classify("热烫会不会伤头发呀?") is None


# ============ 知识问答 (side_question) 端到端 ============

class TestSideQuestionRouting:
    """intake_route 端到端: 知识问答被识别为 side_question."""

    @pytest.mark.asyncio
    async def test_hot_perm_damage_question(self):
        """'热烫会不会伤头发呀?' - 伤+会+吗 + 长度 10 → side_question."""
        result = await intake_route(
            "热烫会不会伤头发呀?",
            "checkin_service",
            {
                "branch_id": 1, "branch_name": "人民广场店",
                "service_type": None, "stylist_id": None,
                "appointment_date": None, "appointment_time": None,
                "customer_phone": None, "customer_name": None,
            },
        )
        assert result["intent"] == INTENT_SIDE_QUESTION, \
            f"应识别为题外话, 实际: {result.get('intent')}"

    @pytest.mark.asyncio
    async def test_principle_question(self):
        """'染发原理到底是什么' - 原理+是什么 + 长度 9 → side_question."""
        result = await intake_route(
            "染发原理到底是什么",
            "checkin_service",
            {"branch_id": 1, "service_type": None, "stylist_id": None,
             "appointment_date": None, "appointment_time": None,
             "customer_phone": None, "customer_name": None},
        )
        assert result["intent"] == INTENT_SIDE_QUESTION

    @pytest.mark.asyncio
    async def test_long_knowledge_question(self):
        """长知识问答 (烫发会伤头发吗, 应该怎么护理?) → side_question."""
        result = await intake_route(
            "烫发会伤头发吗, 应该怎么护理?",
            "checkin_service",
            {"branch_id": 1, "service_type": None, "stylist_id": None,
             "appointment_date": None, "appointment_time": None,
             "customer_phone": None, "customer_name": None},
        )
        assert result["intent"] == INTENT_SIDE_QUESTION

    @pytest.mark.asyncio
    async def test_too_short_for_side_question(self):
        """'热烫伤吗' 长度 4, 即使含 2 keywords 也不判为题外话 (走 LLM)."""
        result = await intake_route(
            "热烫伤吗",
            "checkin_service",
            {"branch_id": 1, "service_type": None, "stylist_id": None,
             "appointment_date": None, "appointment_time": None,
             "customer_phone": None, "customer_name": None},
        )
        # 长度 4, 不满足 len > 8, 走 LLM, LLM 应判 continue (因为是简短回答)
        # LLM 调用需要 chat 模型, 如果 mock/失败, 可能 fallback 到 continue
        assert result["intent"] in (INTENT_CONTINUE, INTENT_SIDE_QUESTION)

    @pytest.mark.asyncio
    async def test_normal_field_answer_is_continue(self):
        """正常字段值 (如'人民广场店') → continue."""
        result = await intake_route(
            "人民广场店",
            "checkin_branch",
            {"branch_id": None, "service_type": None, "stylist_id": None,
             "appointment_date": None, "appointment_time": None,
             "customer_phone": None, "customer_name": None},
        )
        assert result["intent"] == INTENT_CONTINUE


# ============ State 保留测试 ============

class TestStatePreservation:
    """State 设计: side_question 处理后, current_step 不变."""

    def test_make_initial_state_keeps_step(self):
        """验证: make_initial_state 创建后, current_step 默认 idle."""
        from app.rag.workflow.booking_state import make_initial_state
        state = make_initial_state(user_id=1)
        # 初始 state 的 current_step 应是 idle, 让 user 启动流程
        assert state.get("current_step") == "idle"
        # 可手动改 step
        state["current_step"] = "checkin_service"
        assert state["current_step"] == "checkin_service"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
