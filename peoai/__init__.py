"""PeoAI Server —— 把真人接入任何 AI API 的桥接服务。

模块划分：
    config     配置读写与模型注册表
    store      请求队列与状态机
    protocols  OpenAI / Anthropic / Gemini / Ollama 协议适配
    api_*      HTTP 路由
    auth       凭据、会话与登录限流
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
