"""读取 students.xlsx 与 topics.xlsx，做列名模糊映射。"""
from __future__ import annotations

from pathlib import Path

import openpyxl

from .models import Student, Topic


class ExcelReadError(RuntimeError):
    """读表失败（文件不存在 / 缺列 / 空表）。"""


# 列名别名：字段 -> 可能出现的表头（全部小写、去空格后匹配）
STUDENT_ALIASES = {
    "name": ["姓名", "名字", "name", "学生", "同学", "学生姓名"],
    "position": ["投递岗位", "岗位", "应聘岗位", "报名岗位", "position", "岗位方向"],
    "location": ["工作地", "工作地点", "工作城市", "地点", "城市", "base"],
    "professional_review": ["专1意见", "专业面试意见", "专业意见", "专业评价", "一面意见"],
    "overall_review": ["综合面试意见", "综合意见", "综合评价", "总评", "面试评价", "面评", "面试反馈", "面试评语"],
}

TOPIC_ALIASES = {
    "id": ["编号", "id", "课题编号", "序号", "no", "no."],
    "name": ["课题", "课题名称", "题目", "名称", "topic", "title", "课题名"],
    "department": ["部门", "team", "组", "小组", "department"],
    "location": ["地域", "地点", "城市", "工作地点", "location", "base"],
    "background": ["课题背景与挑战", "课题背景", "背景与挑战", "背景", "挑战", "background"],
    "objective": ["课题目标", "目标", "objective", "goal"],
    "content": ["课题内容", "内容", "工作内容", "content"],
}


def _norm(s) -> str:
    return str(s).strip().lower().replace(" ", "") if s is not None else ""


def _read_rows(path: Path) -> tuple[list[str], list[list]]:
    """返回 (表头列表, 数据行列表)。data_only 读计算后的值。"""
    if not path.exists():
        raise ExcelReadError(f"文件不存在：{path}")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise ExcelReadError(f"空表：{path}")
    header = [("" if c is None else str(c).strip()) for c in rows[0]]
    data = [list(r) for r in rows[1:]]
    return header, data


def _match_columns(header: list[str], aliases: dict[str, list[str]]) -> dict[str, int]:
    """字段 -> 列索引。用 normalize 后包含匹配。"""
    norm_header = [_norm(h) for h in header]
    result: dict[str, int] = {}
    for field, names in aliases.items():
        for idx, h in enumerate(norm_header):
            if not h:
                continue
            if any(_norm(n) == h or _norm(n) in h or h in _norm(n) for n in names):
                result[field] = idx
                break
    return result


def read_students(path: Path) -> list[Student]:
    header, data = _read_rows(path)
    cols = _match_columns(header, STUDENT_ALIASES)

    # 至少要有姓名，以及任意一列面试意见（专业/综合）
    if "name" not in cols:
        raise ExcelReadError(
            f"同学表缺少必需列 姓名。\n实际表头：{header}"
        )
    if "professional_review" not in cols and "overall_review" not in cols:
        raise ExcelReadError(
            f"同学表缺少面试意见列。\n实际表头：{header}\n"
            f"期望能匹配到：专1意见 / 专业面试意见 或 综合面试意见。"
        )

    used = set(cols.values())
    students: list[Student] = []
    for row in data:
        name = _cell(row, cols["name"])
        if not name:
            continue  # 跳过空行
        extra = {
            header[i]: _cell(row, i)
            for i in range(len(header))
            if i not in used and header[i] and _cell(row, i)
        }
        students.append(Student(
            name=name,
            position=_cell(row, cols.get("position")),
            location=_cell(row, cols.get("location")),
            professional_review=_cell(row, cols.get("professional_review")),
            overall_review=_cell(row, cols.get("overall_review")),
            extra=extra,
        ))

    if not students:
        raise ExcelReadError(f"同学表无有效数据行：{path}")
    return students


def read_topics(path: Path) -> list[Topic]:
    header, data = _read_rows(path)
    cols = _match_columns(header, TOPIC_ALIASES)

    if "name" not in cols:
        raise ExcelReadError(
            f"课题表缺少课题名称列。\n实际表头：{header}\n期望能匹配到：课题 / 课题名称 / 题目。"
        )

    id_idx = cols.get("id")
    name_idx = cols["name"]
    struct_fields = ("department", "location", "background", "objective", "content")
    struct_idx = {f: cols[f] for f in struct_fields if f in cols}
    # 已被识别（有专属字段）的列，不再进 description
    used = {name_idx}
    if id_idx is not None:
        used.add(id_idx)
    used.update(struct_idx.values())

    topics: list[Topic] = []
    for i, row in enumerate(data, start=1):
        name = _cell(row, name_idx)
        if not name:
            continue
        tid = _cell(row, id_idx) if id_idx is not None else ""
        if not tid:
            tid = f"T{i}"
        kwargs = {f: _cell(row, struct_idx[f]) for f in struct_idx}
        # description = 其余未识别列拼接（保底，防再次漂移丢信息）
        parts = []
        for j in range(len(header)):
            if j in used:
                continue
            val = _cell(row, j)
            if header[j] and val:
                parts.append(f"{header[j]}：{val}")
        topics.append(
            Topic(topic_id=str(tid), name=name, description="；".join(parts), **kwargs)
        )

    if not topics:
        raise ExcelReadError(f"课题表无有效数据行：{path}")
    return topics


def _cell(row: list, idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    v = row[idx]
    return "" if v is None else str(v).strip()
