"""在线大模型对接（OpenAI 兼容 Chat Completions）。

配置通过环境变量注入，密钥不写入代码仓库：

- ``AI_API_KEY``：大模型服务商密钥；留空则不调用在线模型，直接走本地兜底应答。
- ``AI_BASE_URL``：兼容接口前缀，默认 DeepSeek ``https://api.deepseek.com/v1``。
- ``AI_MODEL``：模型名，默认 ``deepseek-chat``。

未配置密钥、网络不可达或接口报错时，统一回退到本地规则应答，保证演示流程不中断。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

SYSTEM_PROMPT = (
    "你是养老服务 App 的智能助手，面向老年人及其家属。"
    "回答要简洁、口语化、亲切，使用中文，字号与表达适合长辈阅读；"
    "只回答健康记录、用药提醒、上门服务、紧急求助和 App 使用相关的问题，"
    "不确定的内容请如实说明，不要编造医疗诊断。"
)

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
REQUEST_TIMEOUT = 15


def is_configured() -> bool:
    """是否已配置在线大模型密钥。"""
    return bool(os.environ.get("AI_API_KEY", "").strip())


def _config() -> tuple[str, str, str]:
    base = os.environ.get("AI_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.environ.get("AI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    key = os.environ.get("AI_API_KEY", "").strip()
    return base, model, key


def local_reply(text: str) -> str:
    """本地规则兜底应答（未接入在线模型或在线调用失败时使用）。"""
    t = text or ""
    if any(k in t for k in ("血压", "血糖", "心率", "体重", "体征", "体温")):
        return "您可以在「健康」页查看和录入血压、血糖、心率、体重等体征；如指标异常，系统会自动提醒您的家属。"
    if any(k in t for k in ("服药", "吃药", "用药", "药品", "剂量")):
        return "请按用药提醒按时服药，「健康」页可查看用药计划并标记已服；漏服时家属会收到提醒。"
    if any(k.lower() in t.lower() for k in ("紧急", "求助", "sos", "摔倒", "跌倒", "帮助")):
        return "如遇紧急情况，请点击首页或底部中央的「SOS 一键求助」，系统会立即通知紧急联系人。"
    if any(k in t for k in ("服务", "上门", "预约", "助洁", "助浴", "陪诊", "护理", "送餐", "理发")):
        return "您可以在「服务」页浏览居家上门、社区服务和养老机构项目，选择项目后预约下单即可。"
    if any(k.lower() in t.lower() for k in ("你好", "您好", "在吗", "hi", "hello")):
        return "您好，请问需要我帮您了解哪方面的内容？健康、用药、服务还是紧急求助？"
    return "这是演示版应答，暂未获取到在线模型回复。您可以换个说法，或咨询健康、用药、服务、求助相关问题。"


def _call_llm(message: str, history: list[dict] | None) -> str:
    """调用 OpenAI 兼容接口，返回模型文本；失败抛异常由上层兜底。"""
    base, model, key = _config()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history or []:
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": message})

    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.6}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def chat(message: str, history: list[dict] | None = None) -> dict:
    """生成助手回复。

    返回 ``{"reply": str, "source": "llm" | "local"}``；在线不可用时回退本地规则。
    """
    text = (message or "").strip()
    if not text:
        return {"reply": "请输入您的问题。", "source": "local"}

    if not is_configured():
        return {"reply": local_reply(text), "source": "local"}

    try:
        reply = _call_llm(text, history)
        if reply:
            return {"reply": reply, "source": "llm"}
        return {"reply": local_reply(text), "source": "local"}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError, OSError):
        return {"reply": local_reply(text), "source": "local"}
