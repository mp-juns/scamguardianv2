"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type DataStats = {
  classifier: { total: number; labels: Record<string, number> };
  gliner: { total: number; total_entities: number };
};

type SessionInfo = {
  session_id: string;
  model: "classifier" | "gliner";
  status: "running" | "completed" | "failed" | "cancelled";
  started_at: number;
  ended_at: number | null;
  exit_code: number | null;
  pid: number | null;
  output_dir: string;
  params: Record<string, unknown>;
  last_metrics: Record<string, unknown> | null;
};

type SessionDetail = {
  session: SessionInfo;
  metrics: Record<string, unknown>[];
  log_tail: string;
};

type SessionsResponse = {
  sessions: SessionInfo[];
  active_models: Record<string, string>;
};

const STATUS_BADGE: Record<string, string> = {
  running: "bg-cyan-500/20 text-cyan-200 border-cyan-400/30",
  completed: "bg-emerald-500/20 text-emerald-200 border-emerald-400/30",
  failed: "bg-rose-500/20 text-rose-200 border-rose-400/30",
  cancelled: "bg-slate-500/20 text-slate-200 border-slate-400/30",
};

function fmtSeconds(value: number | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value * 1000);
  return d.toLocaleString("ko-KR", { hour12: false });
}

function fmtDuration(start: number, end: number | null | undefined): string {
  const sec = Math.floor(((end ?? Date.now() / 1000) - start));
  if (sec < 60) return `${sec}초`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return `${m}분 ${s}초`;
  const h = Math.floor(m / 60);
  return `${h}시간 ${m % 60}분`;
}

export default function TrainingClient() {
  const [stats, setStats] = useState<DataStats | null>(null);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [activeModels, setActiveModels] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    model: "classifier" as "classifier" | "gliner",
    epochs: 3,
    batch_size: 8,
    lora: true,
    extra_jsonl: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const refreshList = useCallback(async () => {
    try {
      const [s1, s2] = await Promise.all([
        fetch("/api/admin/training/data-stats", { cache: "no-store" }),
        fetch("/api/admin/training/sessions", { cache: "no-store" }),
      ]);
      if (s1.ok) setStats(await s1.json());
      if (s2.ok) {
        const data = (await s2.json()) as SessionsResponse;
        setSessions(data.sessions);
        setActiveModels(data.active_models ?? {});
        if (!selectedId && data.sessions[0]) {
          setSelectedId(data.sessions[0].session_id);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "목록 로드 실패");
    }
  }, [selectedId]);

  const refreshDetail = useCallback(async () => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    try {
      const r = await fetch(`/api/admin/training/sessions/${selectedId}`, { cache: "no-store" });
      if (!r.ok) {
        setDetail(null);
        return;
      }
      setDetail((await r.json()) as SessionDetail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "상세 로드 실패");
    }
  }, [selectedId]);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  useEffect(() => {
    void refreshDetail();
  }, [refreshDetail]);

  // 진행 중 세션이 있으면 5초마다 폴링
  useEffect(() => {
    const hasRunning = sessions.some((s) => s.status === "running");
    if (!hasRunning && detail?.session.status !== "running") return;
    const id = setInterval(() => {
      void refreshList();
      void refreshDetail();
    }, 5000);
    return () => clearInterval(id);
  }, [sessions, detail, refreshList, refreshDetail]);

  async function startSession() {
    setSubmitting(true);
    setError("");
    try {
      const r = await fetch("/api/admin/training/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: form.model,
          epochs: form.epochs,
          batch_size: form.batch_size,
          lora: form.lora,
          extra_jsonl: form.extra_jsonl.trim() || null,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail ?? "세션 시작 실패");
      setSelectedId(data.session_id);
      await refreshList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "세션 시작 실패");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelSession(id: string) {
    if (!confirm("이 세션을 취소할까요?")) return;
    const r = await fetch(`/api/admin/training/sessions/${id}/cancel`, { method: "POST" });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      setError(data.detail ?? "취소 실패");
    }
    await refreshList();
    await refreshDetail();
  }

  async function activateSession(id: string) {
    if (!confirm("이 세션의 모델을 파이프라인에 적용할까요?")) return;
    const r = await fetch(`/api/admin/training/sessions/${id}/activate`, { method: "POST" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      setError(data.detail ?? "활성화 실패");
      return;
    }
    await refreshList();
  }

  const chartData = useMemo(() => {
    if (!detail) return [];
    return detail.metrics
      .filter((m) => typeof m.step === "number")
      .map((m) => ({
        step: m.step as number,
        loss: typeof m.loss === "number" ? m.loss : null,
        eval_loss: typeof m.eval_loss === "number" ? m.eval_loss : null,
        eval_macro_f1: typeof m.eval_macro_f1 === "number" ? m.eval_macro_f1 : null,
        eval_accuracy: typeof m.eval_accuracy === "number" ? m.eval_accuracy : null,
      }));
  }, [detail]);

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </div>
      )}

      {/* 데이터 현황 + 활성 모델 */}
      <section className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
          <div className="text-xs uppercase tracking-widest text-slate-400">분류기 학습 데이터</div>
          <div className="mt-2 text-3xl font-bold">
            {stats?.classifier.total ?? "-"}
            <span className="ml-2 text-base font-normal text-slate-400">건</span>
          </div>
          {stats && (
            <div className="mt-3 max-h-32 space-y-1 overflow-auto pr-2 text-xs text-slate-300">
              {Object.entries(stats.classifier.labels).map(([label, n]) => (
                <div key={label} className="flex justify-between">
                  <span>{label}</span>
                  <span className="font-mono">{n}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
          <div className="text-xs uppercase tracking-widest text-slate-400">GLiNER 학습 데이터</div>
          <div className="mt-2 text-3xl font-bold">
            {stats?.gliner.total ?? "-"}
            <span className="ml-2 text-base font-normal text-slate-400">문서</span>
          </div>
          <div className="mt-2 text-sm text-slate-400">
            엔티티 합계 {stats?.gliner.total_entities ?? 0}개
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
          <div className="text-xs uppercase tracking-widest text-slate-400">활성 모델</div>
          <div className="mt-3 space-y-2 text-sm">
            {(["classifier", "gliner"] as const).map((m) => (
              <div key={m} className="flex items-center justify-between">
                <span className="text-slate-300">{m}</span>
                <span className="truncate font-mono text-xs text-slate-400">
                  {activeModels[m] ?? "default"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 세션 시작 폼 */}
      <section className="rounded-2xl border border-white/10 bg-white/5 p-6">
        <h2 className="mb-4 text-lg font-semibold">새 학습 세션</h2>
        <div className="grid gap-4 md:grid-cols-5">
          <label className="space-y-1 text-sm">
            <span className="block text-slate-300">모델</span>
            <select
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value as "classifier" | "gliner" })}
              className="w-full rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2 text-slate-100"
            >
              <option value="classifier">classifier (mDeBERTa)</option>
              <option value="gliner">gliner</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="block text-slate-300">epochs</span>
            <input
              type="number"
              min={1}
              max={20}
              value={form.epochs}
              onChange={(e) => setForm({ ...form, epochs: Number(e.target.value) })}
              className="w-full rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="block text-slate-300">batch size</span>
            <input
              type="number"
              min={1}
              max={64}
              value={form.batch_size}
              onChange={(e) => setForm({ ...form, batch_size: Number(e.target.value) })}
              className="w-full rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2"
            />
          </label>
          <label className="flex items-center gap-2 text-sm md:mt-6">
            <input
              type="checkbox"
              checked={form.lora}
              onChange={(e) => setForm({ ...form, lora: e.target.checked })}
              className="h-4 w-4 accent-cyan-300"
              disabled={form.model !== "classifier"}
            />
            <span>LoRA (classifier 만)</span>
          </label>
          <label className="space-y-1 text-sm md:col-span-1">
            <span className="block text-slate-300">extra JSONL (선택)</span>
            <input
              type="text"
              placeholder="data/processed/aihub.jsonl"
              value={form.extra_jsonl}
              onChange={(e) => setForm({ ...form, extra_jsonl: e.target.value })}
              className="w-full rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2 font-mono text-xs"
            />
          </label>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            onClick={() => void startSession()}
            disabled={submitting}
            className="rounded-xl bg-cyan-300 px-5 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "시작 중..." : "학습 시작"}
          </button>
        </div>
      </section>

      {/* 세션 목록 + 상세 */}
      <section className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
          <div className="mb-2 px-2 text-xs uppercase tracking-widest text-slate-400">세션 ({sessions.length})</div>
          <div className="max-h-[600px] space-y-1 overflow-y-auto pr-1">
            {sessions.length === 0 && (
              <div className="px-2 py-4 text-sm text-slate-500">아직 세션이 없습니다.</div>
            )}
            {sessions.map((s) => (
              <button
                key={s.session_id}
                onClick={() => setSelectedId(s.session_id)}
                className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                  selectedId === s.session_id
                    ? "border-cyan-400/40 bg-cyan-500/10"
                    : "border-transparent hover:bg-white/5"
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono text-slate-400">{s.session_id.slice(0, 8)}</span>
                  <span className={`rounded-full border px-2 py-0.5 ${STATUS_BADGE[s.status] ?? ""}`}>
                    {s.status}
                  </span>
                </div>
                <div className="mt-1 text-sm text-slate-200">{s.model}</div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {fmtSeconds(s.started_at)} · {fmtDuration(s.started_at, s.ended_at)}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
          {detail ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-mono text-xs text-slate-400">{detail.session.session_id}</div>
                  <div className="text-xl font-semibold">{detail.session.model}</div>
                </div>
                <div className="flex gap-2">
                  {detail.session.status === "running" && (
                    <button
                      onClick={() => void cancelSession(detail.session.session_id)}
                      className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-200 hover:bg-rose-500/20"
                    >
                      취소
                    </button>
                  )}
                  {detail.session.status === "completed" && (
                    <button
                      onClick={() => void activateSession(detail.session.session_id)}
                      className="rounded-xl bg-emerald-300 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-200"
                    >
                      파이프라인 적용
                    </button>
                  )}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-3 text-sm">
                <Stat label="상태" value={detail.session.status} />
                <Stat label="시작" value={fmtSeconds(detail.session.started_at)} />
                <Stat label="경과" value={fmtDuration(detail.session.started_at, detail.session.ended_at)} />
              </div>

              {chartData.length > 0 && (
                <div className="rounded-xl border border-white/10 bg-slate-950/40 p-3">
                  <div className="mb-2 text-xs uppercase tracking-widest text-slate-400">메트릭 그래프</div>
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={chartData}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                      <XAxis dataKey="step" stroke="#64748b" fontSize={11} />
                      <YAxis stroke="#64748b" fontSize={11} />
                      <Tooltip
                        contentStyle={{ background: "#0f172a", border: "1px solid #334155" }}
                        labelStyle={{ color: "#cbd5f5" }}
                      />
                      <Legend />
                      <Line type="monotone" dataKey="loss" stroke="#22d3ee" dot={false} connectNulls />
                      <Line type="monotone" dataKey="eval_loss" stroke="#f97316" dot={false} connectNulls />
                      <Line type="monotone" dataKey="eval_macro_f1" stroke="#22c55e" dot={false} connectNulls />
                      <Line type="monotone" dataKey="eval_accuracy" stroke="#a78bfa" dot={false} connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              <div className="rounded-xl border border-white/10 bg-slate-950/60 p-3">
                <div className="mb-2 text-xs uppercase tracking-widest text-slate-400">로그 (tail 8KB)</div>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-xs text-slate-300">
                  {detail.log_tail || "(아직 출력 없음)"}
                </pre>
              </div>

              <details className="rounded-xl border border-white/10 bg-slate-950/40 p-3 text-sm">
                <summary className="cursor-pointer text-slate-300">파라미터 / raw status</summary>
                <pre className="mt-2 overflow-auto text-xs text-slate-400">
                  {JSON.stringify(detail.session, null, 2)}
                </pre>
              </details>
            </div>
          ) : (
            <div className="py-10 text-center text-sm text-slate-500">
              왼쪽에서 세션을 선택하세요.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-1 font-mono text-slate-100">{value}</div>
    </div>
  );
}
