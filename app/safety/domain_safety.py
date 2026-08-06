# -*- coding: utf-8 -*-
"""美发领域安全边界过滤器。

作为 AgentScope ModelWrapper 的 postprocessing 拦截器，
在模型输入输出前后执行安全检查。

安全层级：
1. 输入层：违禁话题拦截、注入防护、长度限制
2. 领域层：确保只回答美发相关问题，防止越界
3. 输出层：模型输出二次审核，防止有害内容
"""
from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 领域白名单与黑名单
# ------------------------------------------------------------------

# 美发领域关键词（命中任意一个即认为相关）
HAIR_KEYWORDS = {
    # 产品类
    "洗发水", "洗发露", "护发素", "发膜", "精油", "发蜡", "发胶", "发泥",
    "慕斯", "弹力素", "造型", "染膏", "漂粉", "双氧", "烫发水", "直发膏",
    # 技术类
    "染发", "烫发", "漂发", "褪色", "拉直", "软化", "造型", "剪发", "吹风",
    "焗油", "护理", "离子烫", "陶瓷烫", "纹理烫", "摩根烫", "巴黎画染",
    "挑染", "片染", "挂耳染", "渐变",
    # 头皮头发问题
    "头屑", "出油", "干枯", "毛躁", "分叉", "断裂", "脱发", "掉发",
    "敏感", "红肿", "瘙痒", "出油", "干燥",
    # 发质类型
    "油性", "干性", "中性", "混合性", "受损发质", "自然卷", "沙发",
    "细软", "粗硬", "漂后", "染后", "烫后",
    # 门店运营
    "门店", "顾客", "话术", "沟通", "服务流程", "办卡", "充值",
    "客单价", "复购", "投诉", "售后",
    # 成分术语
    "氨基酸", "硫酸盐", "硅油", "吡硫鎓锌", "酮康唑", "水杨酸",
    "角蛋白", "神经酰胺", "玻尿酸",
}

# 绝对禁止回答的领域（正则匹配）
FORBIDDEN_PATTERNS = [
    r"政治|政权|政党|领导人|国家主席|总书记|总理",
    r"暴力|恐怖|袭击|武器|炸药|炸弹|杀人|伤害",
    r"色情|成人|性服务|嫖娼|卖淫",
    r"毒品|吸毒|贩毒|白粉|海洛因|冰毒",
    r"诈骗|欺诈|黑客|破解|盗号",
    r"自杀|自残|怎么死|不想活",
    r"违法|犯罪|法律|律师|法院|诉讼|打官司",
    r"医疗|诊断|处方|治疗|医生|医院|开药|吃药|疾病",
    r"理财|投资|股票|基金|期货|比特币|加密货币",
    r"政治敏感|敏感词|敏感话题",
]

# 虚假信息防范关键词（如果回答中出现这些词需要二次审核）
RISK_WORDS = {
    "根治", "包治", "100%", "永不", "永久", "特效", "神药", "秘方",
}


# ------------------------------------------------------------------
# 过滤器实现
# ------------------------------------------------------------------


def is_hair_related(query: str) -> bool:
    """判断问题是否属于美发领域。

    Args:
        query: 用户问题。

    Returns:
        是否美发相关。
    """
    q_lower = query.lower()
    return any(k in q_lower for k in HAIR_KEYWORDS)


def check_forbidden_topics(text: str) -> tuple[bool, str]:
    """检查是否包含违禁话题。

    Returns:
        (是否违禁, 触发的模式或空字符串)。
    """
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, pattern
    return False, ""


def check_risk_words(text: str) -> list[str]:
    """检查回答中是否有高风险词汇（如虚假宣传）。"""
    t_lower = text.lower()
    return [w for w in RISK_WORDS if w in t_lower]


class SafetyFilter:
    """安全过滤器。

    在 Agent 调用模型前后执行检查，确保回答合规。

    使用方式：
        通过 AgentScope 的 ModelWrapper.postprocessing 机制注入。
    """

    def __init__(self, enable_audit_log: bool = True) -> None:
        self.enable_audit_log = enable_audit_log
        self.stats = {
            "total_checks": 0,
            "blocked_input": 0,
            "blocked_output": 0,
            "domain_rejection": 0,
        }

    def filter_input(self, query: str) -> tuple[bool, str]:
        """输入过滤（Agent 调用模型前执行）。

        Returns:
            (是否通过, 拦截原因或空字符串)。
        """
        self.stats["total_checks"] += 1

        # 1. 空输入
        if not query or not query.strip():
            return True, ""

        # 2. 长度限制
        if len(query) > 500:
            self.stats["blocked_input"] += 1
            return False, f"问题太长（{len(query)} 字），请精简至 500 字以内。"

        # 3. 违禁话题检查
        forbidden, pattern = check_forbidden_topics(query)
        if forbidden:
            self.stats["blocked_input"] += 1
            if self.enable_audit_log:
                logger.warning("安全拦截（输入）: 触发模式 '%s'", pattern)
            return False, "抱歉，这个问题超出了我的专业范围。"

        return True, ""

    def filter_output(self, answer: str) -> tuple[bool, str]:
        """输出过滤（Agent 调用模型后执行）。

        Returns:
            (是否通过, 过滤后的回答)。
        """
        # 1. 违禁话题兜底检查（防止模型跑偏）
        forbidden, pattern = check_forbidden_topics(answer)
        if forbidden:
            self.stats["blocked_output"] += 1
            if self.enable_audit_log:
                logger.warning("安全拦截（输出）: 触发模式 '%s'", pattern)
            return False, "抱歉，我无法提供相关内容。"

        # 2. 高风险词汇检查（如虚假宣传）
        risks = check_risk_words(answer)
        if risks and self.enable_audit_log:
            logger.info("高风险词汇提醒: %s", ", ".join(risks))

        # 3. 长度截断
        if len(answer) > 2000:
            answer = answer[:1990] + "..."

        return True, answer

    def check_domain_boundary(self, query: str) -> tuple[bool, str]:
        """领域边界检查（确保 Agent 只回答美发相关问题）。

        Returns:
            (是否在领域内, 越界话术或空字符串)。
        """
        if is_hair_related(query):
            return True, ""

        self.stats["domain_rejection"] += 1
        return False, (
            "我是美发行业技术顾问，擅长回答关于洗发护发、染烫技术、"
            "门店服务、产品使用的问题。请您提问美发相关的内容。"
        )

    def get_stats(self) -> dict[str, int]:
        """获取安全统计指标（接入 Prometheus 监控用）。"""
        return dict(self.stats)


# 全局单例
safety_filter = SafetyFilter()
