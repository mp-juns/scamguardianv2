import Link from "next/link";

export const dynamic = "force-static";

export const metadata = {
  title: "Fine-tuning 동작 원리 — ScamGuardian",
};

type ModelCardProps = {
  emoji: string;
  title: string;
  phase: string;
  base: string;
  role: string;
  inputs: string;
  outputs: string;
  pains: string[];
  fineTuneEffects: string[];
  metricKey: string;
};

function ModelCard({ emoji, title, phase, base, role, inputs, outputs, pains, fineTuneEffects, metricKey }: ModelCardProps) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <div className="mb-4 flex flex-wrap items-baseline gap-3">
        <span className="text-3xl">{emoji}</span>
        <h2 className="text-2xl font-semibold text-white">{title}</h2>
        <span className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200">
          {phase}
        </span>
      </div>

      <p className="mb-4 text-sm leading-relaxed text-slate-300">{role}</p>

      <div className="mb-5 grid gap-3 sm:grid-cols-3 text-sm">
        <Field label="Base 모델" value={base} mono />
        <Field label="입력" value={inputs} />
        <Field label="출력" value={outputs} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-rose-400/20 bg-rose-500/5 p-4">
          <div className="mb-2 text-sm font-semibold text-rose-200">😩 지금 한계</div>
          <ul className="space-y-1.5 text-sm text-slate-300">
            {pains.map((p, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-rose-300">•</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl border border-emerald-400/20 bg-emerald-500/5 p-4">
          <div className="mb-2 text-sm font-semibold text-emerald-200">🎯 fine-tune 으로 좋아지는 것</div>
          <ul className="space-y-1.5 text-sm text-slate-300">
            {fineTuneEffects.map((p, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-emerald-300">•</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-white/10 bg-slate-950/40 p-3 text-xs text-slate-400">
        측정 지표 <span className="font-mono text-slate-200">{metricKey}</span> — 학습 전후 비교 권장
      </div>
    </section>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`mt-1 ${mono ? "font-mono text-xs" : "text-sm"} text-slate-100 break-words`}>
        {value}
      </div>
    </div>
  );
}

const PHASES = [
  { num: 0, title: "Safety", desc: "VirusTotal — URL·파일 악성 여부 (v3 신규)", model: null },
  { num: 1, title: "STT / OCR", desc: "Whisper / Claude vision — 음성·이미지·PDF → 텍스트", model: null },
  { num: 2, title: "분류", desc: "스캠 유형 12종 + 신뢰도 산출", model: "classifier" },
  { num: 3, title: "추출 / RAG / LLM (병렬)", desc: "엔티티 추출 + 유사 사례 + LLM 통합 보조", model: "gliner" },
  { num: 4, title: "검증", desc: "Serper API — 추출 엔티티 교차 검증", model: null },
  { num: 5, title: "스코어링", desc: "플래그 합산 → 0~100 위험 점수", model: null },
];

export default function TrainingAboutPage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#111827_0%,#020617_60%,#000000_100%)] px-4 py-8 text-slate-100 sm:px-6">
      <div className="mx-auto w-full max-w-5xl space-y-8">
        <header className="space-y-2">
          <p className="text-sm text-slate-400">
            <Link href="/admin/training" className="hover:text-slate-200">
              ← Fine-tuning
            </Link>
          </p>
          <h1 className="text-3xl font-semibold text-white">📖 Fine-tuning 어떻게 동작하나</h1>
          <p className="max-w-3xl text-sm leading-relaxed text-slate-400">
            ScamGuardian 분석 파이프라인은 6단계로 구성됩니다. 그중 <strong className="text-cyan-200">분류기</strong>(Phase 2) 와{" "}
            <strong className="text-fuchsia-200">GLiNER</strong>(Phase 3) 두 모델이 도메인 데이터로 학습할수록 정확도가 올라가요.
            학습된 체크포인트를 활성화하면 다음 분석부터 자동으로 swap 됩니다.
          </p>
        </header>

        {/* 파이프라인 다이어그램 */}
        <section className="rounded-3xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">🧭 파이프라인 안에서 어디에 쓰이나</h2>
          <div className="space-y-2">
            {PHASES.map((p) => {
              const highlight =
                p.model === "classifier"
                  ? "border-cyan-400/40 bg-cyan-500/5"
                  : p.model === "gliner"
                  ? "border-fuchsia-400/40 bg-fuchsia-500/5"
                  : "border-white/10 bg-slate-950/40";
              return (
                <div key={p.num} className={`flex items-center gap-4 rounded-2xl border px-4 py-3 ${highlight}`}>
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/15 bg-black/30 font-mono text-sm">
                    {p.num}
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-semibold text-white">
                      Phase {p.num} · {p.title}
                    </div>
                    <div className="text-xs text-slate-400">{p.desc}</div>
                  </div>
                  {p.model === "classifier" && (
                    <span className="rounded-full border border-cyan-400/40 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200">
                      🎯 classifier
                    </span>
                  )}
                  {p.model === "gliner" && (
                    <span className="rounded-full border border-fuchsia-400/40 bg-fuchsia-500/10 px-3 py-1 text-xs text-fuchsia-200">
                      🔖 gliner
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* 각 모델 상세 */}
        <ModelCard
          emoji="🎯"
          title="classifier — 스캠 유형 분류기"
          phase="Phase 2"
          base="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
          role={
            "텍스트 한 덩어리를 보고 12개 스캠 유형(투자 사기·기관 사칭·메신저 피싱·로맨스 스캠 등) 중 어느 것에 가까운지 + 신뢰도(0~1)를 산출합니다. 분석 결과 카드 상단에 노출되는 '스캠 유형: 투자 사기 (신뢰도 92%)' 가 바로 이 모델의 출력이에요."
          }
          inputs="STT/OCR 결과 텍스트 (최대 2000자)"
          outputs="scam_type + confidence + 12개 유형별 점수"
          pains={[
            "Zero-shot NLI 라 한국어 보이스피싱 발화 톤(반말·생략·강세)을 모름",
            "신뢰도가 자주 0.3~0.5 → LLM 오버라이드(`LLM_SCAM_TYPE_OVERRIDE_THRESHOLD=0.7`) 자주 발동",
            "키워드 부스팅 의존 — '투자' 단어만 있어도 투자 사기로 잘못 분기되는 false positive",
            "새 스캠 유형 추가하려면 prompt 수정해야 함",
          ]}
          fineTuneEffects={[
            "분류 정확도 ~70% → 90%+ 도달 가능 (도메인 데이터 충분 시)",
            "신뢰도가 높아져 LLM 오버라이드 호출 빈도 ↓ → Claude API 비용·지연 ↓",
            "키워드 부스팅 의존도 ↓ → false positive 감소",
            "새 라벨 추가만으로 학습 가능 (prompt 수정 불필요)",
          ]}
          metricKey="macro_f1, accuracy, llm_override_rate"
        />

        <ModelCard
          emoji="🔖"
          title="gliner — 스캠 엔티티 추출기"
          phase="Phase 3 (병렬)"
          base="taeminlee/gliner_ko"
          role={
            "텍스트에서 스캠 유형별 의미 라벨(예: 투자 사기 → '수익 퍼센트', '보장 발화', '계좌번호', '긴급성 표현') 에 해당하는 단어·구를 잘라냅니다. Serper 검증·LLM 보조·결과 카드의 '추출 엔티티' 섹션이 모두 이 출력을 사용해요. 27개 라벨이 정의돼 있습니다."
          }
          inputs="텍스트 + 스캠 유형별 허용 라벨 리스트"
          outputs="[{text: '연 30%', label: '수익 퍼센트', score: 0.9}, ...]"
          pains={[
            "범용 한국어 NER 이라 추상 라벨('긴박감 표현', '권위 사칭') 거의 못 잡음",
            "precision 낮음 → 검증 단계에서 노이즈 엔티티 다량 발생",
            "recall 낮음 → 결정적 단서(긴급성, 사칭 표지) 누락",
            "부족분을 LLM 으로 메우느라 비용 추가",
          ]}
          fineTuneEffects={[
            "엔티티 micro F1 ~50% → 80%+ — 도메인 라벨 구조에 맞는 모델로 변신",
            "검증할 만한 엔티티만 잘 뽑힘 → Serper API 호출 수 ↓ + 검증 시간 단축",
            "LLM 엔티티 병합 컷오프(`LLM_ENTITY_MERGE_THRESHOLD=0.7`) 통과율 ↓ → LLM 결과 더 깐깐하게 받음",
            "신규 라벨 추가 후 데이터만 모이면 즉시 학습",
          ]}
          metricKey="entity micro F1, serper_calls_per_case, llm_entity_acceptance_rate"
        />

        {/* before / after 직관 표 */}
        <section className="rounded-3xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">📊 학습 전 vs 학습 후 (예상치)</h2>
          <p className="mb-3 text-sm text-slate-400">
            라벨당 50건+ 데이터 기준의 일반적 기댓값. 실제 결과는 데이터 품질·도메인 적합도에 따라 다릅니다.
          </p>
          <div className="overflow-x-auto rounded-2xl border border-white/10">
            <table className="w-full text-sm">
              <thead className="bg-slate-800/60 text-xs uppercase tracking-wider text-slate-400">
                <tr>
                  <th className="px-3 py-2 text-left">모델 / 지표</th>
                  <th className="px-3 py-2 text-right">학습 전</th>
                  <th className="px-3 py-2 text-right">학습 후</th>
                  <th className="px-3 py-2 text-left">파이프라인 영향</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                <tr>
                  <td className="px-3 py-3 text-slate-200">classifier · macro F1</td>
                  <td className="px-3 py-3 text-right font-mono text-rose-300">~0.65</td>
                  <td className="px-3 py-3 text-right font-mono text-emerald-300">~0.90</td>
                  <td className="px-3 py-3 text-xs text-slate-400">잘못 분류된 케이스 줄어들고, 자신 있게 답해서 LLM 안 부름</td>
                </tr>
                <tr>
                  <td className="px-3 py-3 text-slate-200">classifier · LLM override 호출률</td>
                  <td className="px-3 py-3 text-right font-mono text-rose-300">~40%</td>
                  <td className="px-3 py-3 text-right font-mono text-emerald-300">~10%</td>
                  <td className="px-3 py-3 text-xs text-slate-400">분석당 Claude API 비용·지연 직접 절감</td>
                </tr>
                <tr>
                  <td className="px-3 py-3 text-slate-200">gliner · entity micro F1</td>
                  <td className="px-3 py-3 text-right font-mono text-rose-300">~0.50</td>
                  <td className="px-3 py-3 text-right font-mono text-emerald-300">~0.80</td>
                  <td className="px-3 py-3 text-xs text-slate-400">검증 노이즈 줄어 Serper 호출 수도 ~30% 감소 기대</td>
                </tr>
                <tr>
                  <td className="px-3 py-3 text-slate-200">gliner · 추출 엔티티 평균 수</td>
                  <td className="px-3 py-3 text-right font-mono text-slate-300">10~15</td>
                  <td className="px-3 py-3 text-right font-mono text-slate-300">8~12</td>
                  <td className="px-3 py-3 text-xs text-slate-400">노이즈 ↓ — 적게 뽑되 정확도 ↑</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* 권장 학습 분량 */}
        <section className="rounded-3xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">📦 권장 학습 분량</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/5 p-4">
              <div className="text-sm font-semibold text-cyan-200">classifier</div>
              <ul className="mt-2 space-y-1 text-sm text-slate-300">
                <li>최소: 라벨당 5건</li>
                <li>권장: 라벨당 50건+</li>
                <li>총 700건 (12라벨 × 50 + negative)</li>
              </ul>
            </div>
            <div className="rounded-2xl border border-fuchsia-400/20 bg-fuchsia-500/5 p-4">
              <div className="text-sm font-semibold text-fuchsia-200">gliner</div>
              <ul className="mt-2 space-y-1 text-sm text-slate-300">
                <li>최소: 라벨당 30 mention</li>
                <li>권장: 라벨당 200 mention+</li>
                <li>한 문서에 평균 10~30 mention</li>
              </ul>
            </div>
          </div>
          <p className="mt-4 text-xs text-slate-400">
            데이터 부족 시: 사람 라벨링 큐(<code className="rounded bg-slate-950/40 px-1">/admin</code>) 진행, AI Hub 정상 콜센터 데이터로 negative 보강, Claude 합성으로 희귀 유형(코인·로맨스·납치협박) 채우기.
          </p>
        </section>

        {/* swap 흐름 */}
        <section className="rounded-3xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">🔄 학습 후 활성화는 어떻게 적용되나</h2>
          <ol className="space-y-3 text-sm text-slate-300">
            <li className="rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
              <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/20 font-mono text-xs text-cyan-200">1</span>
              세션 완료 후 <strong className="text-white">[파이프라인 적용]</strong> 클릭
            </li>
            <li className="rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
              <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/20 font-mono text-xs text-cyan-200">2</span>
              <code className="rounded bg-black/40 px-1 font-mono text-xs">.scamguardian/active_models.json</code> 에 체크포인트 경로 기록
            </li>
            <li className="rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
              <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/20 font-mono text-xs text-cyan-200">3</span>
              <code className="rounded bg-black/40 px-1 font-mono text-xs">pipeline/active_models.py</code> 캐시 즉시 무효화
            </li>
            <li className="rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
              <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/20 font-mono text-xs text-cyan-200">4</span>
              다음 분석 호출 시 classifier 는 <strong>task-specific 모드</strong>로 (zero-shot 아님), gliner 는 새 path 로 재로드
            </li>
            <li className="rounded-2xl border border-emerald-400/20 bg-emerald-500/5 px-4 py-3">
              <span className="mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/30 font-mono text-xs text-emerald-200">✓</span>
              체크포인트가 무효(경로 사라짐 등)면 자동으로 base 모델로 fallback — 안전장치
            </li>
          </ol>
        </section>

        {/* 학습 데이터 소스 */}
        <section className="rounded-3xl border border-white/10 bg-white/5 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">🗂 학습 데이터는 어디서 오나</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="text-sm font-semibold text-white">사람 라벨링 (DB)</div>
              <p className="mt-1 text-xs text-slate-400">
                <code className="rounded bg-black/40 px-1">human_annotations</code> 테이블 — Admin UI 에서 매긴 정답이 자동으로 학습 입력으로 들어옵니다.
              </p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="text-sm font-semibold text-white">외부 JSONL (선택)</div>
              <p className="mt-1 text-xs text-slate-400">
                AI Hub 데이터를 <code className="rounded bg-black/40 px-1">scripts/ingest_aihub.py</code> 로 변환한 JSONL 을 폼의 <span className="text-slate-200">extra JSONL</span> 필드에 경로 입력. 정상 콜센터 = negative, 합성 데이터 = 롱테일 보강.
              </p>
            </div>
          </div>
        </section>

        <footer className="pt-2 text-center text-xs text-slate-500">
          <Link href="/admin/training" className="hover:text-slate-300">
            ← Fine-tuning 으로 돌아가기
          </Link>
        </footer>
      </div>
    </main>
  );
}
