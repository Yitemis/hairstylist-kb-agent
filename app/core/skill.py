# -*- coding: utf-8 -*-
"""技能库：让 Agent 从成功经验中学习。

借鉴 AgentScope 2.0 的 AgentSkill 设计：
- 技能 = 一个 Markdown 文档，描述"如何完成某个任务"
- 存在 SkillRegistry（内存）或 SkillRepository（持久化）
- DynamicSkillMiddleware 在 onReasoning 阶段自动匹配 + 注入 system prompt
- 业务价值：随着使用增多，技能积累，Agent 越来越聪明
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """单个技能 = Markdown 描述。"""
    skill_id: str
    name: str
    description: str
    content: str  # Markdown 正文
    tags: list[str] = field(default_factory=list)
    version: str = "1.0"

    def to_markdown(self) -> str:
        """导出为标准 Markdown（带 frontmatter）。"""
        tags_str = "[" + ", ".join(self.tags) + "]" if self.tags else "[]"
        return f"""---
skill_id: {self.skill_id}
name: {self.name}
description: {self.description}
tags: {tags_str}
version: {self.version}
---

# {self.name}

{self.description}

{self.content}
"""

    def render_for_prompt(self) -> str:
        """渲染为可注入到 system prompt 的格式。"""
        return f"""
【技能：{self.name}】

{self.content}
""".strip()


class SkillRegistry:
    """技能注册表（内存版）。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.skill_id] = skill
        logger.debug("注册技能: %s", skill.skill_id)

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def search(self, query: str, top_k: int = 3) -> list[Skill]:
        """简单的关键词匹配：按 tag/description/content 中命中数排序。

        策略：英文按空格分词，中文按单字切分。
        匹配命中数 = 多个 token 都在 tag/desc/content 里出现。
        """
        query_lower = query.lower()
        # 英文按 \w 分词，中文按单字切分
        en_tokens = set(re.findall(r"[a-zA-Z0-9_]+", query_lower))
        cn_chars = set(re.findall(r"[一-鿿]", query_lower))
        query_tokens = en_tokens | cn_chars
        scored: list[tuple[float, Skill]] = []
        for skill in self._skills.values():
            score = 0
            for tag in skill.tags:
                if any(tok in tag.lower() for tok in query_tokens):
                    score += 2
            if any(tok in skill.description.lower() for tok in query_tokens):
                score += 1
            if any(tok in skill.content.lower() for tok in query_tokens):
                score += 0.5
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:top_k]]

    def load_from_dir(self, dir_path: str) -> int:
        """从目录加载 .md 技能文件。"""
        p = Path(dir_path)
        if not p.exists():
            return 0
        count = 0
        for f in p.glob("*.md"):
            try:
                skill = _parse_skill_markdown(f.read_text(encoding="utf-8"))
                self.register(skill)
                count += 1
            except Exception as e:
                logger.warning("加载技能 %s 失败: %s", f, e)
        logger.info("从 %s 加载了 %d 个技能", dir_path, count)
        return count


def _parse_skill_markdown(content: str) -> Skill:
    """解析带 frontmatter 的 Markdown 技能文件。"""
    # 解析 frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            front = content[3:end].strip()
            body = content[end + 3:].strip()
            meta = {}
            for line in front.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            skill_id = meta.get("skill_id", "")
            name = meta.get("name", skill_id)
            description = meta.get("description", "")
            tags_str = meta.get("tags", "[]").strip("[]")
            tags = [t.strip().strip("\"'") for t in tags_str.split(",") if t.strip()]
            version = meta.get("version", "1.0")
            return Skill(
                skill_id=skill_id,
                name=name,
                description=description,
                content=body,
                tags=tags,
                version=version,
            )
    # 无 frontmatter：兜底
    return Skill(
        skill_id=content[:20].strip() or "unknown",
        name=content[:20].strip() or "Unknown",
        description="",
        content=content,
    )


# 全局注册表
_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册表（懒加载）。"""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        # 注册预置技能
        _register_builtin_skills(_registry)
    return _registry


def _register_builtin_skills(registry: SkillRegistry) -> None:
    """注册预置技能（HarnessAgent 招牌能力）。"""
    registry.register(Skill(
        skill_id="confirmation_pattern",
        name="确认前必问",
        description="对涉及金钱、时间、不可逆操作需先确认",
        content="""- 确认订单前，列出订单全字段让用户核对
- 涉及金额时，明确显示金额
- 涉及时间时，明确显示日期 + 时段
- 取消/退款等不可逆操作，必须二次确认
- 默认使用敬语（您/请），不要命令式
""",
        tags=["确认", "订单", "客服"],
    ))
    registry.register(Skill(
        skill_id="booking_flow",
        name="预约流程引导",
        description="一步步引导用户完成预约订单",
        content="""- 先确认分店，再选发型师，再选服务，再约时间
- 每次只问 1-2 个问题，不要一次问太多
- 用户犹豫时给推荐（'我建议人民广场店，离您最近'）
- 时间冲突时主动给替代方案
- 完成时列出订单全字段让用户确认
""",
        tags=["预约", "流程", "引导"],
    ))
    registry.register(Skill(
        skill_id="hair_knowledge_basics",
        name="美发基础知识",
        description="回答专业问题时要先检索知识库再回答",
        content="""- 用户问专业问题（如烫发原理、染发技术、护理知识），必须先调 search_hair_knowledge
- 不要凭训练数据编造产品成分或技术细节
- 引用知识库结果时说明来源
- 不确定时明确说'这个需要您咨询专业发型师'
- 用通俗类比解释专业概念
""",
        tags=["知识", "检索", "专业"],
    ))
    registry.register(Skill(
        skill_id="emotional_response",
        name="情绪化用户应对",
        description="用户抱怨/着急时，先共情再处理",
        content="""- 用户抱怨时，先共情（'我能理解您的心情'），再解决问题
- 不要急着解释技术细节，先确认问题
- 用户着急时给具体时间（'我帮您查一下，2 分钟内回复'）
- 严重问题主动升级（'我帮您联系店长处理'）
""",
        tags=["客服", "情绪", "体验"],
    ))
    logger.info("注册了 %d 个预置技能", len(registry.list_all()))


def find_skills_for(query: str, top_k: int = 2) -> list[Skill]:
    """查找与 query 相关的技能。"""
    return get_skill_registry().search(query, top_k=top_k)


def build_skill_injection(query: str) -> str:
    """根据 query 找出相关技能，渲染为可注入到 system prompt 的格式。"""
    skills = find_skills_for(query, top_k=2)
    if not skills:
        return ""
    parts = ["# 相关技能（参考以下经验）"]
    for s in skills:
        parts.append(s.render_for_prompt())
        parts.append("")
    return "\n".join(parts)
