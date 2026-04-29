import Link from "next/link";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

const API_BASE_URL =
  process.env.SCAMGUARDIAN_API_URL ?? "http://127.0.0.1:8000";

type PageProps = {
  params: Promise<{ token: string }>;
};

type FlagDict = {
  flag?: string;
  score_delta?: number;
  evidence?: Record<string, unknown> | string[];
  flag_description?: string;
  description?: string;
  source?: string;  // "rule" 또는 "llm"
};

// 위험도 레벨 구간 (pipeline/config.py:RISK_LEVELS 동기화)
const RISK_BANDS: Array<{ min: number; max: number; level: string; desc: string }> = [
  { min: 0, max: 20, level: "안전", desc: "특이사항 없음" },
  { min: 21, max: 40, level: "주의", desc: "일부 의심 요소" },
  { min: 41, max: 70, level: "위험", desc: "다수의 스캠 징후" },
  { min: 71, max: 100, level: "매우 위험", desc: "높은 확률의 스캠" },
];

type EntityDict = {
  label?: string;
  text?: string;
  score?: number;
  source?: string;
};

type LLMAssessment = {
  model?: string;
  summary?: string;
  reasoning?: string[];
  suggested_entities?: Array<{ label?: string; text?: string; reason?: string }>;
  suggested_flags?: Array<{ flag?: string; reason?: string; evidence?: string }>;
  error?: string;
};

type SafetyCheckDict = {
  target_kind?: string;
  target?: string;
  scanner?: string;
  threat_level?: string;  // safe | suspicious | malicious | unknown
  detections?: number;
  suspicious?: number;
  total_engines?: number;
  threat_categories?: string[];
  permalink?: string | null;
  error?: string | null;
};

type ReportDict = {
  scam_type?: string;
  classification_confidence?: number;
  is_uncertain?: boolean;
  total_score?: number;
  risk_level?: string;
  risk_description?: string;
  scam_type_reason?: string;
  scam_type_source?: string;
  transcript_text?: string;
  entities?: EntityDict[];
  triggered_flags?: FlagDict[];
  llm_assessment?: LLMAssessment | null;
  safety_check?: SafetyCheckDict | null;
};

type QAPair = { question?: string; answer?: string };

type UserContextDict = {
  qa_pairs?: QAPair[];
  summary_text?: string;
  turn_count?: number;
};

type ChatTurnDict = { role?: string; message?: string };

type FlagRationaleEntry = { rationale?: string; source?: string };

type ResultPayload = {
  result: ReportDict;
  user_context: UserContextDict | null;
  input_type: string;
  chat_history: ChatTurnDict[];
  flag_rationale?: Record<string, FlagRationaleEntry>;
  expires_at: number;
};

const RISK_COLORS: Record<string, string> = {
  "매우 위험": "bg-red-700/30 border-red-500 text-red-200",
  "위험": "bg-orange-700/30 border-orange-500 text-orange-200",
  "주의": "bg-yellow-700/30 border-yellow-500 text-yellow-200",
  "안전": "bg-emerald-700/30 border-emerald-500 text-emerald-200",
};

const INPUT_TYPE_LABEL: Record<string, string> = {
  text: "💬 텍스트",
  url: "🔗 URL/영상",
  video: "🎬 업로드 영상",
  file: "📎 파일",
};

async function fetchResult(token: string): Promise<ResultPayload | { status: number }> {
  const url = `${API_BASE_URL}/api/result/${encodeURIComponent(token)}`;
  try {
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) {
      return { status: resp.status };
    }
    return (await resp.json()) as ResultPayload;
  } catch {
    return { status: 502 };
  }
}

function fmtConfidence(c?: number): string {
  if (typeof c !== "number") return "-";
  return `${(c * 100).toFixed(0)}%`;
}

function fmtExpires(epoch: number): string {
  const remaining = epoch - Date.now() / 1000;
  if (remaining <= 0) return "만료됨";
  const minutes = Math.floor(remaining / 60);
  if (minutes < 1) return "1분 이내 만료";
  if (minutes < 60) return `${minutes}분 후 만료`;
  return `${Math.floor(minutes / 60)}시간 ${minutes % 60}분 후 만료`;
}

export default async function ResultPage({ params }: PageProps) {
  const { token } = await params;
  const data = await fetchResult(token);

  if ("status" in data) {
    if (data.status === 404 || data.status === 410) {
      notFound();
    }
    return (
      <main className="min-h-screen bg-[radial-gradient(circle_at_top,#111827_0%,#020617_60%,#000000_100%)] px-6 py-10 text-slate-100">
        <div className="mx-auto max-w-3xl">
          <div className="rounded-2xl border border-red-500/40 bg-red-950/30 p-6">
            <h1 className="text-xl font-bold text-red-200">결과를 불러올 수 없습니다</h1>
            <p className="mt-2 text-sm text-red-300/80">
              백엔드 API 응답: HTTP {data.status}
            </p>
          </div>
        </div>
      </main>
    );
  }

  const { result, user_context, input_type, chat_history, expires_at } = data;
  const flagRationale = data.flag_rationale ?? {};
  const riskLevel = result.risk_level ?? "알 수 없음";
  const riskColor = RISK_COLORS[riskLevel] ?? "bg-slate-700/30 border-slate-500 text-slate-200";
  const inputLabel = INPUT_TYPE_LABEL[input_type] ?? input_type;
  const llm = result.llm_assessment ?? null;

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#111827_0%,#020617_60%,#000000_100%)] px-4 py-8 text-slate-100 sm:px-6 sm:py-10">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        {/* 헤더 */}
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm text-slate-400">ScamGuardian 분석 결과</p>
            <h1 className="text-2xl font-bold text-slate-100">
              {result.scam_type ?? "미분류"}
            </h1>
          </div>
          <p className="text-xs text-slate-500">{fmtExpires(expires_at)} · {inputLabel}</p>
        </header>

        {/* v3 Phase 0 안전성 경고 — malicious/suspicious 일 때 최상단 prominent */}
        {(() => {
          const sc = result.safety_check;
          if (!sc) return null;
          const level = (sc.threat_level ?? "").toLowerCase();
          if (level !== "malicious" && level !== "suspicious") return null;
          const isMal = level === "malicious";
          const styles = isMal
            ? "border-red-500 bg-red-950/40 text-red-100"
            : "border-amber-500 bg-amber-950/30 text-amber-100";
          const icon = isMal ? "🚨" : "⚠️";
          const targetLabel = sc.target_kind === "url" ? "URL" : "파일";
          const head = isMal
            ? `${icon} 위험! 이 ${targetLabel}은 악성으로 확인됐어요`
            : `${icon} 주의: 이 ${targetLabel}에 일부 의심 신호가 있어요`;
          return (
            <section className={`rounded-2xl border p-6 shadow-lg ${styles}`}>
              <div className="text-lg font-bold">{head}</div>
              <p className="mt-2 text-sm opacity-90">
                VirusTotal {sc.detections ?? 0}/{sc.total_engines ?? 0} 엔진이 위험 판정.
                {sc.target_kind === "url"
                  ? " 클릭하지 마시고 차단·신고를 권장합니다."
                  : " 실행하지 마시고 즉시 삭제하세요."}
              </p>
              {sc.threat_categories && sc.threat_categories.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {sc.threat_categories.slice(0, 5).map((c, i) => (
                    <span
                      key={i}
                      className="rounded-full border border-current/40 bg-black/20 px-2 py-0.5 text-xs"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              )}
              {sc.permalink && (
                <a
                  href={sc.permalink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-block text-xs underline opacity-80 hover:opacity-100"
                >
                  VirusTotal 상세 리포트 →
                </a>
              )}
            </section>
          );
        })()}

        {/* 위험도 배지 */}
        <section className={`rounded-2xl border p-6 shadow-lg ${riskColor}`}>
          <div className="flex items-baseline gap-4">
            <span className="text-3xl font-bold">{riskLevel}</span>
            <span className="text-2xl">{result.total_score ?? 0} / 100점</span>
          </div>
          {result.risk_description && (
            <p className="mt-2 text-sm opacity-80">{result.risk_description}</p>
          )}
          <p className="mt-2 text-xs opacity-70">
            분류 신뢰도: {fmtConfidence(result.classification_confidence)}
            {result.is_uncertain && " · ⚠️ 분류 신뢰도 낮음"}
          </p>
        </section>

        {/* AI 요약 */}
        {llm?.summary && (
          <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
            <h2 className="mb-3 text-lg font-semibold text-slate-100">🤖 AI 요약</h2>
            <p className="text-sm leading-relaxed text-slate-200">{llm.summary}</p>
            {llm.reasoning && llm.reasoning.length > 0 && (
              <ul className="mt-4 list-inside list-disc space-y-1 text-sm text-slate-300">
                {llm.reasoning.map((r, idx) => (
                  <li key={idx}>{r}</li>
                ))}
              </ul>
            )}
          </section>
        )}

        {/* 사용자 제공 정보 — prominent */}
        {(user_context?.qa_pairs?.length ?? 0) > 0 && (
          <section className="rounded-2xl border border-fuchsia-500/40 bg-fuchsia-950/20 p-6">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="text-lg font-semibold text-fuchsia-200">💡 사용자 제공 정보</h2>
              <span className="rounded bg-fuchsia-500/20 px-2 py-0.5 text-xs text-fuchsia-200">
                분석에 prior 로 반영됨
              </span>
            </div>
            <p className="mb-4 text-xs text-fuchsia-200/70">
              아래 정보는 분석가(Claude)가 사기 여부 판단에 직접 참고했어요.
            </p>
            <ol className="space-y-3">
              {(user_context?.qa_pairs ?? []).map((qa, idx) => (
                <li key={idx} className="rounded-lg bg-fuchsia-950/40 p-3">
                  {qa.question && (
                    <p className="text-xs text-fuchsia-300/80">Q. {qa.question}</p>
                  )}
                  <p className="mt-1 text-sm text-fuchsia-100">A. {qa.answer}</p>
                </li>
              ))}
            </ol>
          </section>
        )}

        {/* 점수 산정 방식 */}
        {(result.triggered_flags?.length ?? 0) > 0 && (() => {
          const flags = result.triggered_flags ?? [];
          const total = result.total_score ?? 0;
          const ruleFlags = flags.filter((f) => (f.source ?? "rule") !== "llm");
          const llmFlags = flags.filter((f) => f.source === "llm");
          const ruleSum = ruleFlags.reduce((a, b) => a + (b.score_delta ?? 0), 0);
          const llmSum = llmFlags.reduce((a, b) => a + (b.score_delta ?? 0), 0);
          return (
            <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold text-slate-100">
                  📊 점수 산정 방식
                </h2>
                <Link
                  href="/methodology"
                  className="rounded-full border border-slate-600 px-3 py-1 text-xs text-slate-300 transition hover:border-cyan-400/50 hover:text-cyan-200"
                >
                  점수 기준 자세히 보기 →
                </Link>
              </div>
              <p className="mb-4 text-sm text-slate-400">
                각 플래그의 점수를 합산해 총 위험도를 산출합니다.
                LLM 보조 제안 플래그는 가중치 0.5 가 적용돼 절반만 반영됩니다 (맹신 방지).
              </p>

              {/* 합산식 */}
              <div className="mb-4 rounded bg-slate-950/40 p-4 font-mono text-sm text-slate-200">
                <div className="space-y-3">
                  {flags.map((f, idx) => {
                    const delta = f.score_delta ?? 0;
                    const sign = delta >= 0 ? "+" : "";
                    const labelText = f.flag_description ?? f.description ?? f.flag ?? "?";
                    const isLlm = f.source === "llm";
                    const info = (f.flag && flagRationale[f.flag]) || null;
                    return (
                      <div key={idx} className="border-b border-slate-800 pb-2 last:border-0">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-300">
                            {isLlm ? "🤖 " : ""}
                            {labelText}
                            {isLlm ? (
                              <span className="ml-2 text-xs text-slate-500">
                                (LLM 가중치 0.5 적용)
                              </span>
                            ) : null}
                          </span>
                          <span className={delta >= 0 ? "text-red-300" : "text-emerald-300"}>
                            {sign}
                            {delta}점
                          </span>
                        </div>
                        {info ? (
                          <div className="mt-1 ml-2 space-y-0.5 font-sans text-xs text-slate-500">
                            {info.rationale ? <div>📖 {info.rationale}</div> : null}
                            {info.source ? (
                              <div className="text-slate-600">출처: {info.source}</div>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                  <div className="my-2 border-t border-slate-700" />
                  <div className="flex items-center justify-between text-base font-semibold">
                    <span className="text-slate-200">합계</span>
                    <span className="text-slate-100">
                      {ruleFlags.length > 0 && llmFlags.length > 0
                        ? `${ruleSum} (규칙) + ${llmSum} (LLM) = ${total}점`
                        : `${total}점`}
                    </span>
                  </div>
                </div>
              </div>

              {/* 위험도 등급 테이블 */}
              <div>
                <p className="mb-2 text-sm font-medium text-slate-200">위험도 등급 기준</p>
                <div className="overflow-hidden rounded border border-slate-700">
                  <table className="w-full text-sm">
                    <tbody>
                      {RISK_BANDS.map((band) => {
                        const inRange = total >= band.min && total <= band.max;
                        return (
                          <tr
                            key={band.level}
                            className={
                              inRange
                                ? "bg-amber-500/10 text-amber-200"
                                : "text-slate-400"
                            }
                          >
                            <td className="px-3 py-2 font-mono">
                              {band.min}~{band.max}
                            </td>
                            <td className="px-3 py-2 font-semibold">
                              {band.level}
                              {inRange ? " ← 현재" : ""}
                            </td>
                            <td className="px-3 py-2 text-xs">{band.desc}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          );
        })()}

        {/* 발동 플래그 — 상세 evidence */}
        {(result.triggered_flags?.length ?? 0) > 0 && (
          <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
            <h2 className="mb-3 text-lg font-semibold text-slate-100">
              🚩 발동 플래그 상세 ({result.triggered_flags?.length ?? 0}개)
            </h2>
            <ul className="space-y-3">
              {(result.triggered_flags ?? []).map((f, idx) => {
                const delta = f.score_delta ?? 0;
                const sign = delta >= 0 ? "+" : "";
                const evidenceList: string[] = Array.isArray(f.evidence)
                  ? (f.evidence as string[])
                  : f.evidence
                  ? [JSON.stringify(f.evidence)]
                  : [];
                return (
                  <li key={idx} className="rounded bg-slate-800/60 p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-200">
                        {f.flag_description ?? f.description ?? f.flag}
                      </span>
                      <span className={delta >= 0 ? "font-mono text-red-300" : "font-mono text-emerald-300"}>
                        {sign}
                        {delta}점
                      </span>
                    </div>
                    {evidenceList.length > 0 && (
                      <ul className="mt-2 space-y-1 text-xs text-slate-400">
                        {evidenceList.slice(0, 3).map((e, eidx) => (
                          <li key={eidx} className="truncate">• {e}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {/* 추출 엔티티 */}
        {(result.entities?.length ?? 0) > 0 && (
          <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
            <h2 className="mb-3 text-lg font-semibold text-slate-100">
              🔖 추출 엔티티 ({result.entities?.length ?? 0}개)
            </h2>
            <div className="flex flex-wrap gap-2">
              {(result.entities ?? []).map((e, idx) => (
                <span
                  key={idx}
                  className="rounded-full border border-slate-600 bg-slate-800/40 px-3 py-1 text-xs text-slate-200"
                  title={`source: ${e.source ?? "-"}, score: ${e.score?.toFixed?.(2) ?? "-"}`}
                >
                  <span className="text-slate-400">{e.label}: </span>
                  {e.text}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* 입력 본문 / 전사 */}
        {result.transcript_text && (
          <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
            <h2 className="mb-3 text-lg font-semibold text-slate-100">
              📜 {input_type === "text" ? "입력 본문" : "음성 전사"}
              <span className="ml-2 text-xs text-slate-500">
                ({result.transcript_text.length.toLocaleString()}자)
              </span>
            </h2>
            <details className="text-sm text-slate-300">
              <summary className="cursor-pointer text-slate-400 hover:text-slate-200">
                전체 보기 / 접기
              </summary>
              <pre className="mt-3 max-h-[60vh] overflow-auto whitespace-pre-wrap rounded bg-slate-950/60 p-4 text-xs leading-relaxed">
                {result.transcript_text}
              </pre>
            </details>
          </section>
        )}

        {/* 챗봇 대화 전체 (Q&A 외에 봇 발화도 포함된 풀 트랜스크립트) */}
        {chat_history.length > 0 && (
          <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
            <h2 className="mb-3 text-lg font-semibold text-slate-100">
              💬 챗봇 대화 전체 ({chat_history.length}턴)
            </h2>
            <details className="text-sm">
              <summary className="cursor-pointer text-slate-400 hover:text-slate-200">
                펼쳐서 보기
              </summary>
              <ol className="mt-3 space-y-2">
                {chat_history.map((t, idx) => (
                  <li
                    key={idx}
                    className={
                      t.role === "user"
                        ? "ml-8 rounded bg-blue-900/30 p-2 text-sm text-blue-100"
                        : "rounded bg-slate-800/40 p-2 text-sm text-slate-200"
                    }
                  >
                    <span className="text-xs text-slate-400">
                      {t.role === "user" ? "👤 사용자" : "🤖 챗봇"}
                    </span>
                    <p className="mt-1 whitespace-pre-wrap">{t.message}</p>
                  </li>
                ))}
              </ol>
            </details>
          </section>
        )}

        <footer className="pt-4 text-center text-xs text-slate-500">
          이 결과 페이지는 1시간 후 자동 만료됩니다.
        </footer>
      </div>
    </main>
  );
}
