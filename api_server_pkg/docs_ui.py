"""커스텀 /docs (Swagger UI) + /redoc — 한국어 친화 폰트 + 가독성 폴리시.

기본 FastAPI 가 제공하는 Swagger UI / ReDoc 의 폰트와 색이 한국어 본문과 잘
어울리지 않아서 (Helvetica 기본, 자간이 좁고 한글 라인높이 부족) 다음을 적용:

- 본문 폰트: Pretendard (CDN, gh/orioncactus/pretendard)
- 코드 폰트: JetBrains Mono (CDN)
- 라인 높이 1.65 (한글 가독성 기본값)
- 태그 헤더 색·간격 정돈, opblock 카드 그림자 부드럽게

CDN 만 사용하므로 빌드 단계 추가 자산 없음.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

# Pretendard — 한국어 화면 디자인 표준 OSS 폰트. cdn.jsdelivr.net 미러 사용.
_FONT_LINKS = """
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap">
"""

# Swagger UI 커스텀 — 인라인 <style> 로 주입 (외부 CSS 파일 호스팅 회피)
_SWAGGER_CUSTOM_CSS = """
<style>
:root {
  --sg-font: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, system-ui, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
  --sg-mono: 'JetBrains Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
  --sg-bg: #fafbfc;
  --sg-card: #ffffff;
  --sg-border: #e5e9f0;
  --sg-ink: #1f2937;
  --sg-ink-soft: #4b5563;
  --sg-accent: #4f46e5;
}

html, body {
  background: var(--sg-bg) !important;
}

body, .swagger-ui {
  font-family: var(--sg-font) !important;
  color: var(--sg-ink);
  font-feature-settings: "ss05", "ss10", "tnum";
  letter-spacing: -0.005em;
  line-height: 1.65;
}

.swagger-ui .info {
  margin: 32px 0 28px;
}
.swagger-ui .info .title {
  font-family: var(--sg-font) !important;
  font-weight: 800;
  letter-spacing: -0.02em;
  font-size: 36px;
  color: var(--sg-ink);
}
.swagger-ui .info .title small.version-stamp {
  background: #4f46e5;
  border-radius: 999px;
  padding: 2px 10px;
  font-weight: 600;
}
.swagger-ui .info .description,
.swagger-ui .info p,
.swagger-ui .info li {
  font-size: 15px;
  color: var(--sg-ink-soft);
  line-height: 1.75;
}
.swagger-ui .info a {
  color: var(--sg-accent);
}

/* 검색·필터 */
.swagger-ui .filter .operation-filter-input {
  font-family: var(--sg-font) !important;
  border-radius: 10px;
  border: 1px solid var(--sg-border);
  padding: 10px 14px;
  font-size: 14px;
}

/* 태그(섹션) 헤더 */
.swagger-ui .opblock-tag {
  font-family: var(--sg-font) !important;
  font-weight: 700;
  font-size: 22px;
  letter-spacing: -0.015em;
  color: var(--sg-ink);
  border-bottom: 1px solid var(--sg-border);
  padding: 18px 0 12px;
  margin-top: 24px;
}
.swagger-ui .opblock-tag small {
  font-weight: 500;
  color: var(--sg-ink-soft);
  font-size: 14px;
  letter-spacing: 0;
}

/* operation 카드 */
.swagger-ui .opblock {
  border-radius: 12px !important;
  border: 1px solid var(--sg-border) !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.04) !important;
  background: var(--sg-card);
  margin: 10px 0 14px;
}
.swagger-ui .opblock .opblock-summary {
  border-radius: 12px 12px 0 0 !important;
  padding: 12px 16px;
}
.swagger-ui .opblock .opblock-summary-method {
  font-family: var(--sg-mono) !important;
  font-weight: 600;
  border-radius: 6px;
  min-width: 78px;
  text-align: center;
  font-size: 12px;
  letter-spacing: 0.04em;
}
.swagger-ui .opblock .opblock-summary-path,
.swagger-ui .opblock .opblock-summary-path__deprecated {
  font-family: var(--sg-mono) !important;
  font-size: 14.5px;
  color: var(--sg-ink);
}
.swagger-ui .opblock .opblock-summary-description {
  font-family: var(--sg-font) !important;
  color: var(--sg-ink-soft);
  font-size: 14px;
}

/* 본문 sections */
.swagger-ui .opblock-section-header {
  background: #f7f9fc;
  border-radius: 8px;
  padding: 8px 14px;
  margin-bottom: 12px;
  box-shadow: none;
}
.swagger-ui .opblock-section-header h4 {
  font-family: var(--sg-font) !important;
  font-weight: 700;
  font-size: 14px;
  color: var(--sg-ink);
}
.swagger-ui .opblock-description-wrapper p,
.swagger-ui .opblock-external-docs-wrapper p,
.swagger-ui .opblock-title_normal p,
.swagger-ui .markdown p,
.swagger-ui .renderedMarkdown p {
  font-size: 15px;
  line-height: 1.8;
  color: var(--sg-ink-soft);
}
.swagger-ui .markdown ul,
.swagger-ui .renderedMarkdown ul {
  padding-left: 22px;
}
.swagger-ui .markdown li,
.swagger-ui .renderedMarkdown li {
  font-size: 14.5px;
  color: var(--sg-ink-soft);
  margin: 4px 0;
}

/* 코드 블록 — 외곽 컨테이너만 스타일링. 내부 highlight.js span 의 line-height 를
   override 하면 라인끼리 겹친다. 그래서 .microlight / pre code 에는 폰트만 지정하고
   layout 은 swagger 기본값 유지. */
.swagger-ui .highlight-code,
.swagger-ui .opblock-body pre.example,
.swagger-ui .opblock-body pre.microlight,
.swagger-ui .responses-inner pre {
  background: #0f172a !important;
  border-radius: 10px;
  padding: 14px 16px;
}
.swagger-ui pre,
.swagger-ui pre code,
.swagger-ui .microlight,
.swagger-ui .microlight span,
.swagger-ui .highlight-code .microlight {
  font-family: var(--sg-mono) !important;
  font-size: 13px;
  /* line-height·padding·display 절대 건드리지 말 것 — highlight.js 라인 단위 span 깨짐 */
}
.swagger-ui .microlight,
.swagger-ui pre code {
  color: #e2e8f0 !important;
  background: transparent !important;
}
/* 인라인 코드 (description 안 백틱) */
.swagger-ui :not(pre) > code {
  font-family: var(--sg-mono) !important;
  background: #f1f5f9;
  color: #0f172a;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.92em;
}

/* 테이블 */
.swagger-ui table {
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--sg-border);
}
.swagger-ui table thead tr td,
.swagger-ui table thead tr th {
  font-family: var(--sg-font) !important;
  font-weight: 600;
  font-size: 13px;
  background: #f7f9fc;
  color: var(--sg-ink);
}
.swagger-ui .response-col_status {
  font-family: var(--sg-mono) !important;
  font-weight: 600;
}

/* 버튼 */
.swagger-ui .btn {
  font-family: var(--sg-font) !important;
  border-radius: 8px;
  font-weight: 600;
  letter-spacing: -0.005em;
  transition: transform .04s ease, box-shadow .15s ease;
}
.swagger-ui .btn:hover {
  transform: translateY(-1px);
}
.swagger-ui .btn.execute {
  background: linear-gradient(180deg, #6366f1, #4f46e5) !important;
  border-color: #4338ca !important;
  color: white;
}
.swagger-ui .btn.try-out__btn {
  border-radius: 8px;
}

/* topbar 숨김 — 더 깔끔 */
.swagger-ui .topbar { display: none; }

/* scheme(인증) 컨테이너 */
.swagger-ui .scheme-container {
  background: var(--sg-card);
  border: 1px solid var(--sg-border);
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  margin: 20px 0;
}
</style>
"""

_REDOC_CUSTOM_HEAD = """
<style>
body, html {
  font-family: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, system-ui, 'Segoe UI', Roboto, sans-serif !important;
  letter-spacing: -0.005em;
}
h1, h2, h3, h4, h5, h6 {
  font-family: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont, sans-serif !important;
  font-weight: 700 !important;
  letter-spacing: -0.018em !important;
}
code, pre, .token {
  font-family: 'JetBrains Mono', SFMono-Regular, Consolas, monospace !important;
}
</style>
"""

_REDOC_OPTIONS = (
    "theme='{\"typography\":{\"fontFamily\":\"Pretendard Variable, Pretendard, -apple-system, BlinkMacSystemFont, system-ui, sans-serif\","
    "\"headings\":{\"fontFamily\":\"Pretendard Variable, Pretendard, sans-serif\",\"fontWeight\":\"700\"},"
    "\"code\":{\"fontFamily\":\"JetBrains Mono, SFMono-Regular, monospace\"}}}'"
)


def install_custom_docs(app: FastAPI) -> None:
    """기본 /docs · /redoc 을 비우고 커스텀 HTML 라우트로 대체.

    `app.docs_url=None, redoc_url=None` 으로 만든 뒤 호출해야 한다 (create_app 에서 처리).
    `/openapi.json` 은 FastAPI 기본 경로 그대로 사용.
    """

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui() -> HTMLResponse:
        base_html = get_swagger_ui_html(
            openapi_url=app.openapi_url or "/openapi.json",
            title=f"{app.title} — API Docs",
            swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
            swagger_ui_parameters={
                "docExpansion": "list",        # 태그 펼침, operation 은 접힘
                "defaultModelsExpandDepth": 0, # 하단 schema 섹션 접기
                "displayRequestDuration": True,
                "filter": True,                # 검색창 활성
                "tryItOutEnabled": True,
                "syntaxHighlight.theme": "obsidian",
            },
        )
        html = base_html.body.decode("utf-8")
        # <head> 끝에 폰트 + 커스텀 스타일 주입
        html = html.replace(
            "</head>",
            _FONT_LINKS + _SWAGGER_CUSTOM_CSS + "</head>",
            1,
        )
        return HTMLResponse(html)

    @app.get("/redoc", include_in_schema=False)
    async def custom_redoc() -> HTMLResponse:
        base_html = get_redoc_html(
            openapi_url=app.openapi_url or "/openapi.json",
            title=f"{app.title} — Reference",
            redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        )
        html = base_html.body.decode("utf-8")
        html = html.replace(
            "</head>",
            _FONT_LINKS + _REDOC_CUSTOM_HEAD + "</head>",
            1,
        )
        return HTMLResponse(html)
