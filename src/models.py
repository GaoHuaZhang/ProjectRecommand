"""数据模型：Student / Topic / Recommendation。"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


@dataclass
class Student:
    """一位同学的面试信息。"""
    name: str
    position: str = ""              # 投递岗位
    location: str = ""             # 工作地（仅作参考信息）
    professional_review: str = ""  # 专业面试意见（专1意见）
    overall_review: str = ""       # 综合面试意见
    extra: dict = field(default_factory=dict)  # 其余未识别列，原样保留

    @property
    def evaluation(self) -> str:
        """兼容旧调用：把专业/综合意见合并成一段文本。"""
        parts = []
        if self.professional_review:
            parts.append(f"专业意见：{self.professional_review}")
        if self.overall_review:
            parts.append(f"综合意见：{self.overall_review}")
        return " ".join(parts) or " ".join(str(v) for v in self.extra.values())

    def to_prompt_block(self) -> str:
        lines = [f"姓名：{self.name}", f"投递岗位：{self.position or '未填'}"]
        if self.location:
            lines.append(f"工作地：{self.location}（参考信息）")
        if self.professional_review:
            lines.append(f"专业面试意见：{self.professional_review}")
        if self.overall_review:
            lines.append(f"综合面试意见：{self.overall_review}")
        for k, v in self.extra.items():
            if str(v).strip():
                lines.append(f"{k}：{v}")
        return "\n".join(lines)


@dataclass
class Topic:
    """一个课题。"""
    topic_id: str          # 编号（读表时自动生成 T1, T2... 若原表无编号列）
    name: str
    department: str = ""   # 部门
    location: str = ""     # 地域（仅作参考信息）
    background: str = ""   # 课题背景与挑战
    objective: str = ""    # 课题目标
    content: str = ""      # 课题内容
    description: str = ""  # 其余未识别列拼接（保底）

    def to_prompt_block(self) -> str:
        lines = [f"[{self.topic_id}] {self.name}"]
        ref = []
        if self.department:
            ref.append(f"部门：{self.department}")
        if self.location:
            ref.append(f"地域：{self.location}")
        if ref:
            lines.append("    " + " ｜ ".join(ref) + "（参考信息）")
        if self.background:
            lines.append(f"    背景与挑战：{self.background}")
        if self.objective:
            lines.append(f"    课题目标：{self.objective}")
        if self.content:
            lines.append(f"    课题内容：{self.content}")
        if self.description:
            lines.append(f"    其他信息：{self.description}")
        return "\n".join(lines)


class RecItem(BaseModel):
    """模型返回的单条推荐（用于校验）。"""
    topic_id: str = Field(..., description="课题编号，必须来自给定清单")
    topic_name: str = Field(default="", description="课题名称")
    score: float = Field(..., ge=0, le=100, description="匹配度 0-100")
    reason: str = Field(..., description="推荐理由，结合面试评价")


class RecResult(BaseModel):
    """模型对单个同学的完整返回。"""
    recommendations: list[RecItem]


@dataclass
class StudentResult:
    """最终写入报告的一位同学结果。"""
    student: Student
    items: list[RecItem]
    error: str | None = None   # 非空表示该同学需人工复核
