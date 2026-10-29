"""Gọi LLM qua CrewAI (mỗi lần = 1 Agent + 1 Task + 1 Crew), trả về text + token đã dùng."""
import json
import re
import time
from dataclasses import dataclass

from . import config

AGENTS = {
    "researcher": (
        "Content Researcher",
        "Turn search results into a factual, well-structured outline with a focus keyword and cited sources",
        "A meticulous SEO researcher who only uses facts present in the provided material.",
    ),
    "writer": (
        "Long-form Blog Writer",
        "Write an engaging, accurate, well-structured blog post that follows the outline and style guide",
        "A senior content marketer who writes clear, useful articles and always cites the sources provided.",
    ),
    "editor": (
        "Copy Editor",
        "Fix grammar, spelling, flow and tone without shortening the article or changing facts",
        "A strict editor fluent in Vietnamese and English who polishes drafts and applies reviewer feedback.",
    ),
    "social": (
        "Social Media Adapter",
        "Rewrite a blog post into native posts for each requested social platform following its style guide",
        "A social media manager who knows what works on Threads, Facebook and LinkedIn.",
    ),
    "seo": (
        "SEO Optimizer",
        "Optimise the article and metadata for the focus keyword without hurting readability",
        "A technical SEO specialist applying Yoast-style rules to Vietnamese and English content.",
    ),
    "images": (
        "Visual Prompt Designer",
        "Write image-generation prompts and alt text that illustrate the article",
        "An art director who briefs text-to-image models with concrete, visual descriptions.",
    ),
    "qa": (
        "QA Checker",
        "Review the final package and report concrete issues with facts, citations, tone and structure",
        "A critical reviewer who points out specific problems and how to fix them.",
    ),
}


@dataclass
class Usage:
    prompt: int = 0
    completion: int = 0

    def __iadd__(self, o: "Usage"):
        self.prompt += o.prompt
        self.completion += o.completion
        return self

    @property
    def cost(self) -> float:
        return (self.prompt * config.PRICE_IN + self.completion * config.PRICE_OUT) / 1e6


def clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return re.sub(r"^.*?</think>", "", text, flags=re.S).strip()  # <think> mở ở prompt, chỉ còn thẻ đóng


def extract_json(text: str):
    text = clean(text)
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON found")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def _llm(temperature: float):
    from crewai import LLM

    return LLM(
        model=config.MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        temperature=temperature,
        max_tokens=8000,
        # cố định provider để kết quả/chi phí nhất quán
        extra_body={"provider": {"order": [config.PROVIDER], "allow_fallbacks": False}},
    )


def run(agent: str, task: str, expected: str, temperature: float = 0.6, retries: int = 2) -> tuple[str, Usage]:
    from crewai import Agent, Crew, Process, Task

    role, goal, backstory = AGENTS[agent]
    last = None
    for attempt in range(retries + 1):
        try:
            a = Agent(role=role, goal=goal, backstory=backstory, llm=_llm(temperature), allow_delegation=False, verbose=False)
            t = Task(description=task + "\n\n/no_think", expected_output=expected, agent=a)
            crew = Crew(agents=[a], tasks=[t], process=Process.sequential, verbose=False, tracing=False)
            out = crew.kickoff()
            m = crew.usage_metrics
            return clean(out.raw), Usage(m.prompt_tokens, m.completion_tokens)
        except Exception as e:  # lỗi mạng/429 -> thử lại với backoff
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last}")


def run_json(agent: str, task: str, expected: str, temperature: float = 0.4):
    """Như run() nhưng ép ra JSON; nếu parse lỗi thì hỏi lại 1 lần."""
    usage = Usage()
    for attempt in range(2):
        text, u = run(agent, task, expected, temperature)
        usage += u
        try:
            return extract_json(text), usage
        except ValueError:
            task += "\n\nYour previous answer was not valid JSON. Return ONLY one valid JSON value, no commentary."
    raise RuntimeError("LLM did not return valid JSON")
