# -*- coding: utf-8 -*-
"""英文 RAG 评估集 (针对英文理发书 'Practice and Science of Standard Barbering')."""
from dataclasses import dataclass


@dataclass
class EvalQuery:
    query: str
    expected_keywords: list[str]
    category: str = "knowledge"


# 15 个英文 query (匹配 PDF 内容)
EVAL_SET_EN: list[EvalQuery] = [
    # Haircut techniques
    EvalQuery("How to cut a short haircut for round face",
              ["round", "short", "haircut"], category="knowledge"),
    EvalQuery("What is the procedure for a basic haircut",
              ["procedure", "haircut", "cut"], category="knowledge"),
    EvalQuery("How to hold scissors and comb",
              ["scissors", "comb", "hold"], category="knowledge"),
    # Shaving
    EvalQuery("What is the proper shaving technique",
              ["shaving", "razor", "technique"], category="knowledge"),
    EvalQuery("How to prepare a customer for shaving",
              ["prepare", "shaving", "customer"], category="knowledge"),
    # Hair coloring
    EvalQuery("How to mix hair color",
              ["color", "mix", "dye"], category="knowledge"),
    EvalQuery("What are the steps for hair coloring",
              ["color", "step", "process"], category="knowledge"),
    # Scalp treatment
    EvalQuery("How to do a scalp treatment",
              ["scalp", "treatment", "massage"], category="knowledge"),
    # Customer service
    EvalQuery("How to greet a customer professionally",
              ["greet", "customer", "professional"], category="knowledge"),
    # Hygiene
    EvalQuery("What are the hygiene practices in barbering",
              ["hygiene", "clean", "sanitize"], category="knowledge"),
    # Tools
    EvalQuery("What tools are used for a haircut",
              ["tools", "scissors", "clippers"], category="knowledge"),
    # Products
    EvalQuery("What products are used for hair styling",
              ["product", "styling", "tonic"], category="knowledge"),
    # General
    EvalQuery("What is the history of barbering",
              ["history", "barber", "ancient"], category="knowledge"),
    # Service
    EvalQuery("How to give a customer a haircut consultation",
              ["consultation", "customer", "service"], category="knowledge"),
    # Hair care
    EvalQuery("What hair care products are recommended",
              ["hair", "care", "product"], category="knowledge"),
]
