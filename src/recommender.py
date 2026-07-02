"""核心推荐逻辑：为每位同学从课题清单中选 Top N。"""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from .config import Config
from .llm_client import LLMClient
from .models import RecItem, RecResult, Student, StudentResult, Topic

SYSTEM_PROMPT = """你是一位资深的科研课题分配专家。你的任务是：根据一位同学的面试意见与投递岗位，\
从给定的课题清单中挑选最匹配的课题，并给出可解释的匹配理由与分数。

【匹配依据】按重要性从高到低：
1. 技术能力契合：面试意见（专业面试意见 / 综合面试意见）中体现的能力/技术栈/项目经历，与课题的「背景与挑战 / 课题目标 / 课题内容」所需能力是否吻合；专业面试意见权重更高。
2. 岗位方向契合：投递岗位与课题所属方向是否一致或相近。
3. 兴趣与经历匹配：面试意见中透露的兴趣点、擅长领域是否指向该课题。

【仅作参考、不得作为主要加减分项】
- 同学的「工作地」与课题的「地域」「部门」：仅作信息展示。除非同学明确表达地域偏好，否则不因工作地与课题地域是否一致而抬高或压低匹配度。

【评分与理由】
- score 为 0-100 的匹配度，综合上述 1/2/3 维度给出，技术契合越强分数越高。
- reason 用中文，必须引用面试意见中的具体点（如某项技术、项目、能力），并对应到该课题「课题目标 / 课题内容」中的具体点，说明为什么匹配；避免空泛套话。

【硬约束】
1. 只能从提供的课题清单里选择，topic_id 必须严格来自清单，不得编造或改写。
2. 按 score 从高到低排序。
3. 只输出一个 JSON 对象，不要输出任何解释性文字或 markdown 代码块。"""

USER_TEMPLATE = """请为以下同学推荐最匹配的 {top_n} 个课题。

【同学信息】（含投递岗位、专业面试意见、综合面试意见；「工作地」为参考信息）
{student_block}

【课题清单】（每个课题含 编号、名称，以及背景与挑战 / 课题目标 / 课题内容；「部门」「地域」为参考信息）
{topics_block}

【输出格式】严格返回如下 JSON（recommendations 长度为 {top_n}，按匹配度降序）：
{{
  "recommendations": [
    {{"topic_id": "课题编号", "topic_name": "课题名称", "score": 88, "reason": "结合面试意见的具体点与课题目标/内容说明匹配理由"}}
  ]
}}"""


def _extract_json(text: str) -> dict:
    """从模型输出里鲁棒地抠出 JSON 对象。"""
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 截取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"无法从模型输出解析 JSON：{text[:200]}")


class Recommender:
    def __init__(self, cfg: Config, client: LLMClient, topics: list[Topic]):
        self.cfg = cfg
        self.client = client
        self.topics = topics
        self.topics_block = "\n".join(t.to_prompt_block() for t in topics)
        self.valid_ids = {t.topic_id for t in topics}
        self.id_to_name = {t.topic_id: t.name for t in topics}

    def recommend_one(self, student: Student) -> StudentResult:
        user = USER_TEMPLATE.format(
            top_n=self.cfg.top_n,
            student_block=student.to_prompt_block(),
            topics_block=self.topics_block,
        )
        try:
            raw = self.client.chat(SYSTEM_PROMPT, user, json_mode=True)
            result = self._parse_and_validate(raw)
        except Exception as e:  # noqa: BLE001 单人失败不影响整体
            return StudentResult(student=student, items=[], error=str(e))

        return StudentResult(student=student, items=result)

    def _parse_and_validate(self, raw: str) -> list[RecItem]:
        data = _extract_json(raw)
        try:
            parsed = RecResult.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"模型返回结构非法：{e}") from e

        # 过滤掉不在清单里的 topic_id，并回填名称
        clean: list[RecItem] = []
        for item in parsed.recommendations:
            if item.topic_id not in self.valid_ids:
                continue
            if not item.topic_name:
                item.topic_name = self.id_to_name.get(item.topic_id, "")
            clean.append(item)

        if not clean:
            raise ValueError("模型未返回任何有效课题（topic_id 均不在清单中）")
        return clean[: self.cfg.top_n]

    def recommend_all(self, students: list[Student], progress=None) -> list[StudentResult]:
        results: list[StudentResult] = []
        for s in students:
            results.append(self.recommend_one(s))
            if progress is not None:
                progress(s.name)
        return results
