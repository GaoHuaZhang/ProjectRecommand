"""集中配置：从 config/.env 读取所有参数。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（src 的上一级）
ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "config" / ".env"


class ConfigError(RuntimeError):
    """配置缺失或非法。"""


@dataclass
class Config:
    base_url: str
    api_key: str
    model: str
    students_xlsx: Path
    topics_xlsx: Path
    output_dir: Path
    top_n: int
    temperature: float
    timeout: int
    max_retries: int
    verify_ssl: bool = True   # False 等效 curl -k（内网自签证书用）
    ca_bundle: str = ""       # 自定义 CA 证书路径（比关闭校验更安全）


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise ConfigError(
            f"缺少必需配置 {name}。请复制 config/.env.example 为 config/.env 并填写。"
        )
    return val


def _resolve(path_str: str) -> Path:
    """相对路径按项目根目录解析。"""
    p = Path(path_str)
    return p if p.is_absolute() else (ROOT / p)


def load_config() -> Config:
    """加载 .env 并构造 Config；缺失关键项时抛出 ConfigError。"""
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    # 若无 .env 也允许直接从进程环境变量读取（方便 CI / 容器注入）

    base_url = _require("LLM_BASE_URL")
    api_key = _require("LLM_API_KEY")
    model = _require("LLM_MODEL")

    students = _resolve(os.getenv("STUDENTS_XLSX", "data/students.xlsx"))
    topics = _resolve(os.getenv("TOPICS_XLSX", "data/topics.xlsx"))
    output_dir = _resolve(os.getenv("OUTPUT_DIR", "output"))

    try:
        top_n = int(os.getenv("TOP_N", "3"))
        temperature = float(os.getenv("TEMPERATURE", "0.2"))
        timeout = int(os.getenv("LLM_TIMEOUT", "60"))
        max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
    except ValueError as e:
        raise ConfigError(f"数值型配置解析失败：{e}") from e

    verify_ssl = os.getenv("LLM_VERIFY_SSL", "true").strip().lower() not in (
        "0", "false", "no", "off",
    )
    ca_bundle = os.getenv("LLM_CA_BUNDLE", "").strip()

    return Config(
        base_url=base_url,
        api_key=api_key,
        model=model,
        students_xlsx=students,
        topics_xlsx=topics,
        output_dir=output_dir,
        top_n=top_n,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        verify_ssl=verify_ssl,
        ca_bundle=ca_bundle,
    )
