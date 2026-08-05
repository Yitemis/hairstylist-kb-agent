# -*- coding: utf-8 -*-
"""RAG 评估集：30 个真实美发问题 + 期望文档。

借鉴 JavaGuide RAG 评估章节 + RAGAS 框架：
- 30 个 query（覆盖知识检索 / 图片 / 闲聊等）
- 每个 query 期望的关键词 / 文档 ID
- 用真实 PDF 文档（从 mineru-output）

QA 分布：
- 知识问答 (20)：染发 / 烫发 / 护理 / 化学原理
- 业务流程 (5)：预约 / 改时间 / 取消
- 多模态 (3)：图片识别 + 推荐
- 闲聊 (2)：问候 / 闲聊
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvalQuery:
    query: str
    expected_keywords: list[str]  # 期望答案中应包含的关键词
    expected_doc_id: str | None = None  # 期望的源文档 ID
    category: str = "knowledge"  # knowledge / booking / multimodal / casual
    difficulty: str = "easy"  # easy / medium / hard


# 30 个评估 query
EVAL_SET: list[EvalQuery] = [
    # 知识问答 - 染发 (5)
    EvalQuery("染发前要做什么测试", ["皮肤", "过敏", "48"], category="knowledge"),
    EvalQuery("染发的化学原理是什么", ["化学", "氧化", "色素"], category="knowledge", difficulty="hard"),
    EvalQuery("染膏的成分有哪些", ["染膏", "成分", "化学"], category="knowledge"),
    EvalQuery("染发后多久可以洗头", ["洗头", "小时", "24"], category="knowledge"),
    EvalQuery("阿摩尼亚过敏怎么办", ["过敏", "阿摩尼亚", "染膏"], category="knowledge"),
    # 知识问答 - 烫发 (4)
    EvalQuery("烫发前要软化头发吗", ["软化", "烫发"], category="knowledge"),
    EvalQuery("烫发水的成分", ["烫发水", "成分", "化学"], category="knowledge", difficulty="hard"),
    EvalQuery("冷烫和热烫的区别", ["冷烫", "热烫", "区别"], category="knowledge"),
    EvalQuery("烫发后如何护理", ["护理", "护发", "烫发"], category="knowledge"),
    # 知识问答 - 护理 (4)
    EvalQuery("洗发水温多少度合适", ["水温", "38", "40"], category="knowledge"),
    EvalQuery("护发素怎么用", ["护发素", "停留", "3"], category="knowledge"),
    EvalQuery("头皮屑多怎么办", ["头皮屑", "护理", "去屑"], category="knowledge"),
    EvalQuery("头发分叉怎么修复", ["分叉", "护理", "修复"], category="knowledge"),
    # 知识问答 - 脸型 / 发型 (4)
    EvalQuery("圆脸适合什么发型", ["圆脸", "短发", "刘海"], category="knowledge"),
    EvalQuery("方脸适合什么刘海", ["方脸", "刘海", "适合"], category="knowledge"),
    EvalQuery("长发适合染什么颜色", ["长发", "染", "颜色"], category="knowledge"),
    EvalQuery("短发怎么打理", ["短发", "打理", "造型"], category="knowledge"),
    # 知识问答 - 难 (3)
    EvalQuery("头皮护理的化学原理", ["头皮", "化学", "护理"], category="knowledge", difficulty="hard"),
    EvalQuery("染发褪色的原因", ["褪色", "氧化", "洗发"], category="knowledge", difficulty="hard"),
    EvalQuery("烫发对头发的损伤", ["损伤", "烫发", "化学键"], category="knowledge", difficulty="hard"),
    # 业务 (3) - 应该走 booking 流程
    EvalQuery("我想预约明天下午 3 点", ["预约", "时间"], category="booking"),
    EvalQuery("我要改预约时间到后天", ["改", "预约", "时间"], category="booking"),
    EvalQuery("帮我取消订单", ["取消", "订单"], category="booking"),
    # 多模态 (3) - 应该需要图片
    EvalQuery("帮我看看这个脸型适合什么发型", ["脸型", "发型", "适合"], category="multimodal"),
    EvalQuery("我的头发受损了怎么修复", ["受损", "修复", "护理"], category="multimodal"),
    EvalQuery("看看这个发色适不适合我", ["发色", "适合"], category="multimodal"),
    # 闲聊 (2)
    EvalQuery("你好", ["你好"], category="casual"),
    EvalQuery("今天天气怎么样", [], category="casual"),
    EvalQuery("白头发可以染吗", ["白头发", "染"], category="knowledge"),
    EvalQuery("染发后能马上洗头吗", ["洗头", "染发"], category="knowledge"),
]
