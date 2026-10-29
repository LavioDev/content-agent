"""Gọi thử OpenRouter bằng key trong .env để kiểm tra kết nối model. Chạy: python scripts/check_llm.py"""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

env = {}
for line in (Path(__file__).parent.parent / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

body = {
    # OpenRouter API không dùng tiền tố "openrouter/" của LiteLLM
    "model": env["MODEL"].removeprefix("openrouter/"),
    "messages": [{"role": "user", "content": "Viết 2 câu giới thiệu về Hải Phòng. /no_think"}],
    "max_tokens": 200,
    "provider": {"order": [env["PROVIDER"]], "allow_fallbacks": False},
}
req = urllib.request.Request(
    env["OPENROUTER_BASE_URL"] + "/chat/completions",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {env['OPENROUTER_API_KEY']}", "Content-Type": "application/json"},
)
start = time.time()
try:
    res = json.load(urllib.request.urlopen(req, timeout=60))
except urllib.error.HTTPError as e:
    raise SystemExit(f"Lỗi {e.code}: {e.read().decode()}")

print(res["choices"][0]["message"]["content"])
print(f"\nprovider={res.get('provider')} tokens={res['usage']} time={time.time() - start:.1f}s")
