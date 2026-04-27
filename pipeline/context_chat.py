"""
ScamGuardian v2 — 카카오 챗봇 컨텍스트 수집 대화 오케스트레이터

분석 대기 시간 동안 Claude Haiku로 사용자에게 짧은 질문을 던져
출처 / 사용자가 의심한 포인트 / 권유받은 행동 등을 수집한다.

STT/파이프라인과 병렬로 실행되며, 모인 답변은 user_context로 묶여
analyze_unified() 의 prior 로 주입된다.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

_client = None

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
# 사용자가 '결과확인'으로 끝낼 때까지 계속 질문하므로 매우 높게 — 안전망 용도일 뿐
MAX_TURNS = 20
USER_ANSWER_MAX_CHARS = 500
BOT_MESSAGE_MAX_CHARS = 300


def _get_client():
    global _client
    if _client is None:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _model_name() -> str:
    return os.getenv("ANTHROPIC_HAIKU_MODEL", DEFAULT_MODEL)


@dataclass
class ContextTurn:
    """대화 한 발화."""

    role: Literal["bot", "user"]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "message": self.message}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextTurn":
        return cls(role=data["role"], message=data["message"])


@dataclass
class NextAction:
    """Claude 가 결정한 다음 액션."""

    action: Literal["ASK", "DONE"]
    message: str  # 사용자에게 보낼 한국어 텍스트
    reasoning: str = ""

    @property
    def is_done(self) -> bool:
        return self.action == "DONE"


_SYSTEM_PROMPT = """당신은 한국어 보이스피싱·전화사기 탐지 챗봇의 컨텍스트 수집 도우미입니다.
사용자가 의심 콘텐츠(텍스트/URL/영상)를 보냈고, 분석 정확도를 높일 prior 정보를
대화로 수집하는 역할입니다.

가장 중요한 원칙 — 능동적 질문:
- **본문이 주어지면 본문을 정독한 뒤, 그 안의 구체적 단서를 짚어가며 질문하세요.**
  (예: 본문에 "솔라텍 바이오"라는 단어가 있으면 → "이 솔라텍 바이오라는 종목 직접 들어보신 적 있으세요?")
  (예: "월 30% 보장"이 있으면 → "그 월 30% 보장 이야기, 누가 어떤 상황에서 했나요?")
- **일반론적 질문 금지.** "출처가 어디예요?" 같은 추상 질문보다 "이거 카톡으로 받으신 거죠? 단톡방인가요 1대1인가요?" 처럼 본문에서 추론한 가설을 던지세요.
- 본문이 없거나 짧으면(URL/영상 STT 미완료) 일반 가이드 4축 참고:
    (1) 왜 의심하시게 됐는지 / 분석을 요청한 계기
    (2) 출처(누구에게/어디서 받았는지)
    (3) 어떤 부분이 가장 수상하신지 구체적 포인트
    (4) 권유받은 행동(송금/앱설치/계좌·연락처 공유 등)
- 채워진 정보 다음엔 더 깊은 디테일: 상대가 쓴 표현, 신원 단서, 본인이 실제로 한 행동, 비슷한 피해 들었는지 등.

대화 운영 원칙:
- **절대 스스로 대화를 끝내지 마세요.** 사용자가 '결과확인'을 누르거나 분석 요청할 때까지 계속 ASK.
- 한 번에 한 가지만, 짧고 친근한 한국어 1~2문장.
- 같은 질문 반복 금지. 사용자의 직전 답변을 한 단어라도 받아치며 자연스럽게 이어가세요.
- 답변이 모호하면 명확화 질문 1번까지만, 그래도 모호하면 다른 주제로.
- 절대 분석 결과를 추측·미리 말하지 마세요. "스캠 같다", "안전해 보인다" 금지.
- 마크다운, 코드블록, 이모지 금지. 순수 텍스트만.

출력은 항상 JSON (다른 텍스트 금지):
{"action": "ASK", "message": "사용자에게 보낼 한국어 질문", "reasoning": "내부용 짧은 메모"}"""


_TRANSCRIPT_PREVIEW_MAX = 2000


def _build_user_prompt(
    input_type: str,
    history: list[ContextTurn],
    transcript_text: str | None = None,
) -> str:
    if history:
        history_lines = [f"[{turn.role}] {turn.message}" for turn in history]
        history_block = "\n".join(history_lines)
    else:
        history_block = "(아직 대화 없음 — 첫 질문을 던지세요)"

    if transcript_text:
        body = transcript_text.strip()
        truncated_note = ""
        if len(body) > _TRANSCRIPT_PREVIEW_MAX:
            body = body[:_TRANSCRIPT_PREVIEW_MAX]
            truncated_note = f"\n(본문 길어서 앞 {_TRANSCRIPT_PREVIEW_MAX}자만 표시)"
        transcript_block = f"\n=== 사용자가 보낸 본문 ({len(transcript_text)}자) ==={truncated_note}\n{body}\n=== 본문 끝 ===\n"
    else:
        transcript_block = "\n(본문 아직 준비되지 않음 — STT 진행 중이거나 일반 질문으로 시작)\n"

    return f"""사용자가 보낸 자료 유형: {input_type}
{transcript_block}
지금까지의 대화 ({len(history)}턴):
{history_block}

위 본문을 정독하고, 본문 단서를 짚어가며 능동적으로 다음 질문을 JSON 으로 결정하세요. (봇 발화 최대 {MAX_TURNS}턴)"""


def _parse_json(raw: str) -> dict[str, Any]:
    text = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}


def _call_claude(
    input_type: str,
    history: list[ContextTurn],
    transcript_text: str | None = None,
) -> dict[str, Any]:
    client = _get_client()
    model = _model_name()
    user_prompt = _build_user_prompt(input_type, history, transcript_text)

    body_len = len(transcript_text) if transcript_text else 0
    print(
        f"    [ContextChat] → {model}, history={len(history)}턴, body={body_len}자"
    )
    t0 = time.time()
    message = client.messages.create(
        model=model,
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    elapsed = time.time() - t0
    raw = message.content[0].text
    print(f"    [ContextChat] ← {len(raw)}자 ({elapsed:.1f}s)")
    return _parse_json(raw)


_FALLBACK_DONE = NextAction(
    action="DONE",
    message="확인했어요. 분석 결과 곧 알려드릴게요.",
    reasoning="fallback",
)


def _static_first_question(input_type: str) -> NextAction:
    """첫 질문은 Claude 호출 없이 즉답 — 사용자가 5초 기다리지 않게.

    Q2 부터는 Claude 가 본문 + 누적 답변을 보고 능동 질문 생성.
    """
    type_lower = (input_type or "").lower()
    if type_lower == "text":
        msg = "이 메시지 어떻게 받으셨어요? (예: 카톡, 문자, 이메일 등)"
    elif type_lower in ("url", "video"):
        msg = "이 영상 어디서 보거나 받으셨어요?"
    elif type_lower == "file":
        msg = "이 파일 어떻게 받으셨어요? 누가 보냈나요?"
    else:
        msg = "처음 어디서 받으셨는지 알려주실 수 있을까요?"
    return NextAction(action="ASK", message=msg, reasoning="static_first_question")


def next_turn(
    input_type: str,
    history: list[ContextTurn],
    transcript_text: str | None = None,
) -> NextAction:
    """다음 질문을 생성한다.

    첫 턴(history 비어있음)은 Claude 호출 없이 즉답.
    Q2 부터 transcript_text + history 로 본문 단서 짚어가며 능동 질문.
    MAX_TURNS 안전망에 걸렸을 때만 DONE 반환.
    """
    # 첫 턴 — 즉답으로 응답 속도 보장
    if not history:
        return _static_first_question(input_type)

    bot_turns = sum(1 for t in history if t.role == "bot")
    if bot_turns >= MAX_TURNS:
        return NextAction(
            action="DONE",
            message="충분히 알려주셔서 감사해요. 분석 결과 곧 알려드릴게요.",
            reasoning="max_turns_reached_safety",
        )

    try:
        raw = _call_claude(input_type, history, transcript_text)
    except Exception as exc:
        # Claude 실패 시 — 강제 종료하지 말고 안전한 일반 질문으로 폴백
        print(f"    [ContextChat] Claude 호출 실패 → 일반 질문 폴백: {exc}")
        return NextAction(
            action="ASK",
            message="혹시 더 알려주실 단서가 있으실까요? 없으면 '결과확인'을 눌러주세요.",
            reasoning=f"claude_error: {exc}",
        )

    message = str(raw.get("message", "")).strip()
    reasoning = str(raw.get("reasoning", "")).strip()

    # action 은 무조건 ASK 로 강제 — Claude 가 DONE 줘도 무시하고 계속 묻는다
    if not message:
        message = "조금 더 알려주실 수 있을까요? 충분히 답하셨다면 '결과확인'을 눌러주세요."

    return NextAction(
        action="ASK",
        message=message[:BOT_MESSAGE_MAX_CHARS],
        reasoning=reasoning,
    )


# ──────────────────────────────────────────────
# 첫 메시지 의도 분류 (능동 라우팅용)
# ──────────────────────────────────────────────

INTENT_GREETING = "GREETING"           # "안녕", "ㅎㅇ" 등 단순 인사
INTENT_HELP = "HELP"                   # "사용법", "어떻게 써?" 등
INTENT_CONTENT = "CONTENT"             # 메시지 자체가 의심 본문
INTENT_ANALYZE_NO_CONTENT = "ANALYZE_NO_CONTENT"  # "이거 분석해줘" 같은 요청만, 본문 없음
INTENT_CHAT = "CHAT"                   # "엄마가 이상한 거 받았는데" 같은 상황 묘사

_VALID_INTENTS = {
    INTENT_GREETING, INTENT_HELP, INTENT_CONTENT,
    INTENT_ANALYZE_NO_CONTENT, INTENT_CHAT,
}

_INTENT_SYSTEM_PROMPT = """당신은 한국어 보이스피싱·전화사기 탐지 챗봇의 첫 메시지 의도 분류기입니다.
사용자가 챗봇에 보낸 짧은 메시지를 보고 정확히 다음 5개 중 하나를 골라야 합니다.

- GREETING: 단순 인사·아이스브레이커. 예) "안녕", "안녕하세요", "ㅎㅇ", "처음이에요"
- HELP: 봇 사용법/기능 문의. 예) "사용법 알려줘", "뭐 하는 봇이야?", "어떻게 쓰는거야?"
- CONTENT: 메시지 자체가 의심 본문(스캠 텍스트, 카톡 캡처 내용 등을 그대로 붙여넣음). 사기·투자 권유·송금 요구·링크 등이 본문에 있음.
- ANALYZE_NO_CONTENT: 분석 요청은 했는데 분석 대상 본문은 같이 안 보냄. 예) "이거 사기인지 봐줘", "분석 좀", "사기 같은데 확인해줘"
- CHAT: 상황을 설명·이야기하지만 본문은 없음. 예) "어제 이상한 카톡 받았어", "엄마가 이상한 거 받았다는데", "사기 당할 뻔했어"

출력은 JSON 한 줄만: {"intent": "<위 5개 중 하나>"}"""


# 매우 짧은 텍스트에 대해서는 LLM 없이 즉답 (비용·레이턴시 절약)
_GREETING_KEYWORDS = {
    "안녕", "안녕하세요", "ㅎㅇ", "헬로", "hi", "hello", "처음", "처음이에요",
    "여보세요",
}
_HELP_KEYWORDS = {
    "사용법", "도움말", "도움", "help", "?", "사용방법", "사용 방법",
    "어떻게써", "어떻게 써", "뭐야", "뭐하는거야", "뭐 하는 봇",
}


def classify_intent(utterance: str) -> str:
    """첫 메시지 의도를 분류한다.

    Heuristic fast-path → Claude Haiku.
    실패 시 안전한 폴백으로 CONTENT (분석 시도) 반환.
    """
    text = utterance.strip()
    if not text:
        return INTENT_GREETING

    # Fast path: 명백히 긴 텍스트는 본문으로 취급 (LLM 호출 X)
    if len(text) > 300:
        return INTENT_CONTENT

    # Fast path: 짧고 정확히 매칭되는 인사/사용법
    if text in _GREETING_KEYWORDS or text.lower() in _GREETING_KEYWORDS:
        return INTENT_GREETING
    if text in _HELP_KEYWORDS or text.lower() in _HELP_KEYWORDS:
        return INTENT_HELP

    # 그 외 — Claude Haiku 로 분류
    try:
        client = _get_client()
        model = _model_name()
        print(f"    [Intent] → {model}, len={len(text)}")
        t0 = time.time()
        message = client.messages.create(
            model=model,
            max_tokens=40,
            system=_INTENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        elapsed = time.time() - t0
        raw = message.content[0].text
        parsed = _parse_json(raw)
        intent = str(parsed.get("intent", "")).strip().upper()
        print(f"    [Intent] ← {intent} ({elapsed:.1f}s)")
        if intent in _VALID_INTENTS:
            return intent
    except Exception as exc:
        print(f"    [Intent] 분류 실패 → CONTENT 폴백: {exc}")

    return INTENT_CONTENT


def summarize_for_pipeline(history: list[ContextTurn]) -> dict[str, Any]:
    """대화 히스토리를 analyze_unified() 의 user_context 로 쓸 dict 로 정리.

    LLM 추가 호출 없이 단순 구조화만 한다.
    """
    qa_pairs: list[dict[str, str]] = []
    pending_q: str | None = None
    for turn in history:
        if turn.role == "bot":
            pending_q = turn.message
        else:  # user
            qa_pairs.append(
                {
                    "question": pending_q or "",
                    "answer": turn.message,
                }
            )
            pending_q = None

    summary_lines = []
    for qa in qa_pairs:
        if qa["question"]:
            summary_lines.append(f"Q: {qa['question']}")
        summary_lines.append(f"A: {qa['answer']}")

    return {
        "qa_pairs": qa_pairs,
        "summary_text": "\n".join(summary_lines),
        "turn_count": len(history),
        "answered_count": len(qa_pairs),
    }
