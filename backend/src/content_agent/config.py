import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]  # thư mục gốc dự án
load_dotenv(ROOT / ".env")

# CrewAI mặc định hỏi chia sẻ trace (chặn 20s) và in banner ra stdout — làm hỏng giao thức stdio của MCP
for _k in ("CREWAI_DISABLE_TELEMETRY", "OTEL_SDK_DISABLED"):
    os.environ.setdefault(_k, "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


MODEL = env("MODEL", "openrouter/qwen/qwen3-14b")
PROVIDER = env("PROVIDER", "DeepInfra")
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
SERPER_API_KEY = env("SERPER_API_KEY")  # trống -> dùng DuckDuckGo (ddgs)
MCP_TOKEN = env("MCP_TOKEN")  # trống -> không kiểm tra token ở chế độ HTTP
DB_PATH = env("DB_PATH", str(ROOT / "data.db"))
# $/1M token, dùng tính chi phí (mặc định = qwen3-14b @ DeepInfra)
PRICE_IN = float(env("PRICE_IN", "0.12"))
PRICE_OUT = float(env("PRICE_OUT", "0.24"))
PORT = int(env("PORT", "8787"))  # 8000 hay bị WSL/dịch vụ khác chiếm
MAX_QA_ROUNDS = 2
PLATFORMS = ("threads", "facebook", "linkedin")
PLATFORM_LIMITS = {"threads": 500, "facebook": 1500, "linkedin": 3000}  # ký tự
