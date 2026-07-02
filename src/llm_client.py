"""OpenAI 兼容大模型客户端封装（可换 base_url），带重试与 JSON 模式降级。"""
from __future__ import annotations

import time

from openai import OpenAI

from .config import Config


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = OpenAI(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            timeout=cfg.timeout,
            max_retries=0,  # 重试逻辑自己控制，便于降级
        )
        # 记录网关是否支持 response_format=json_object；探测失败后置 False 避免反复试
        self._json_mode_ok = True

    def chat(self, system: str, user: str, json_mode: bool = True) -> str:
        """返回模型输出文本。失败按指数退避重试 max_retries 次。"""
        last_err: Exception | None = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                return self._call(system, user, json_mode)
            except Exception as e:  # noqa: BLE001 网关错误形态多样，统一兜底重试
                last_err = e
                if attempt < self.cfg.max_retries:
                    wait = min(2 ** attempt, 10)
                    time.sleep(wait)
        raise RuntimeError(f"LLM 调用失败（已重试 {self.cfg.max_retries} 次）：{last_err}")

    def _call(self, system: str, user: str, json_mode: bool) -> str:
        kwargs = dict(
            model=self.cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.cfg.temperature,
        )
        if json_mode and self._json_mode_ok:
            try:
                resp = self.client.chat.completions.create(
                    response_format={"type": "json_object"}, **kwargs
                )
                return resp.choices[0].message.content or ""
            except Exception:
                # 网关不支持 response_format，降级为普通调用（仅探测一次）
                self._json_mode_ok = False

        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""
