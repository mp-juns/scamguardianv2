import Link from "next/link";

const API_BASE_URL =
  process.env.SCAMGUARDIAN_API_URL ?? "http://127.0.0.1:8000";

type Flag = {
  flag: string;
  label_ko: string;
  score_delta: number;
  rationale: string;
  source: string;
};

type RiskBand = {
  min: number;
  max: number;
  level: string;
  description: string;
};

type Methodology = {
  flags: Flag[];
  risk_bands: RiskBand[];
  weights: {
    llm_flag_score_ratio: number;
    llm_entity_merge_threshold: number;
    llm_flag_score_threshold: number;
    llm_scam_type_override_threshold: number;
    classification_threshold: number;
    gliner_threshold: number;
    keyword_boost_weight: number;
  };
  models: Record<string, string>;
};

const RISK_BAND_COLORS: Record<string, string> = {
  "매우 위험": "bg-red-700/30 border-red-500 text-red-200",
  "위험": "bg-orange-700/30 border-orange-500 text-orange-200",
  "주의": "bg-yellow-700/30 border-yellow-500 text-yellow-200",
  "안전": "bg-emerald-700/30 border-emerald-500 text-emerald-200",
};

async function fetchMethodology(): Promise<Methodology | { error: string }> {
  try {
    const resp = await fetch(`${API_BASE_URL}/api/methodology`, {
      next: { revalidate: 600 },
    });
    if (!resp.ok) {
      return { error: `백엔드 응답: HTTP ${resp.status}` };
    }
    return (await resp.json()) as Methodology;
  } catch (err) {
    return { error: err instanceof Error ? err.message : String(err) };
  }
}

export const metadata = {
  title: "점수 산정 방식 — ScamGuardian",
  description: "위험도 점수 합산식, 등급 기준, 플래그별 정당성과 출처를 설명합니다.",
};

export default async function MethodologyPage() {
  const data = await fetchMethodology();

  if ("error" in data) {
    return (
      <main className="min-h-screen bg-[radial-gradient(circle_at_top,#111827_0%,#020617_60%,#000000_100%)] px-6 py-10 text-slate-100">
        <div className="mx-auto max-w-3xl rounded-2xl border border-red-500/40 bg-red-950/30 p-6">
          <h1 className="text-xl font-bold text-red-200">점수 기준을 불러올 수 없습니다</h1>
          <p className="mt-2 text-sm text-red-300/80">{data.error}</p>
        </div>
      </main>
    );
  }

  const positive = data.flags.filter((f) => f.score_delta > 0);
  const negative = data.flags.filter((f) => f.score_delta < 0);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#111827_0%,#020617_60%,#000000_100%)] px-4 py-8 text-slate-100 sm:px-6 sm:py-10">
      <div className="mx-auto w-full max-w-4xl space-y-8">
        <header className="space-y-2">
          <p className="text-sm text-slate-400">ScamGuardian</p>
          <h1 className="text-3xl font-bold text-slate-100">📊 위험도 점수 산정 방식</h1>
          <p className="max-w-2xl text-sm leading-relaxed text-slate-400">
            ScamGuardian 은 발화·텍스트에서 사기 신호(플래그)를 탐지하고, 각 플래그에 사전 정의된 점수를 합산해 0~100+ 점의 위험도를 산출합니다.
            아래에서 각 플래그의 점수, 점수의 정당성·출처, 그리고 LLM 보조 가중치 같은 설계 결정을 확인할 수 있습니다.
          </p>
        </header>

        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
          <h2 className="mb-3 text-lg font-semibold text-slate-100">합산식</h2>
          <div className="rounded bg-slate-950/60 p-4 font-mono text-sm leading-relaxed text-slate-200">
            <div>총점 = Σ (규칙 기반 플래그 점수) + Σ (LLM 보조 플래그 점수 × {data.weights.llm_flag_score_ratio})</div>
          </div>
          <p className="mt-3 text-sm text-slate-400">
            LLM(Claude) 이 자체적으로 추가 제안한 플래그는 가중치 <span className="text-slate-200">{data.weights.llm_flag_score_ratio}</span> 가 곱해져 절반만 반영됩니다.
            맹신을 막기 위한 보수적 설계입니다.
          </p>
        </section>

        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
          <h2 className="mb-3 text-lg font-semibold text-slate-100">위험도 등급</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {data.risk_bands.map((band) => (
              <div
                key={band.level}
                className={`rounded-xl border px-4 py-3 ${RISK_BAND_COLORS[band.level] ?? "bg-slate-700/30 border-slate-500 text-slate-200"}`}
              >
                <div className="font-mono text-xs opacity-70">
                  {band.min}~{band.max}점
                </div>
                <div className="mt-1 text-lg font-semibold">{band.level}</div>
                <div className="mt-1 text-xs opacity-80">{band.description}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
          <h2 className="mb-1 text-lg font-semibold text-slate-100">
            가산 플래그 ({positive.length}개)
          </h2>
          <p className="mb-4 text-sm text-slate-400">
            발견되면 위험 점수에 가산됩니다. 점수가 높을수록 사기 확신도가 큰 신호입니다.
          </p>
          <div className="overflow-x-auto rounded-lg border border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-800/60 text-xs uppercase tracking-wider text-slate-400">
                <tr>
                  <th className="px-3 py-2 text-left">플래그</th>
                  <th className="px-3 py-2 text-right">점수</th>
                  <th className="px-3 py-2 text-left">정당성</th>
                  <th className="px-3 py-2 text-left">출처</th>
                </tr>
              </thead>
              <tbody>
                {positive.map((f) => (
                  <tr key={f.flag} className="border-t border-slate-800 align-top">
                    <td className="px-3 py-3">
                      <div className="font-semibold text-slate-100">{f.label_ko}</div>
                      <div className="font-mono text-xs text-slate-500">{f.flag}</div>
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-red-300">
                      +{f.score_delta}
                    </td>
                    <td className="px-3 py-3 text-xs text-slate-300">{f.rationale}</td>
                    <td className="px-3 py-3 text-xs text-slate-500">{f.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {negative.length > 0 && (
          <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
            <h2 className="mb-1 text-lg font-semibold text-slate-100">
              감산 플래그 ({negative.length}개)
            </h2>
            <p className="mb-4 text-sm text-slate-400">
              교차 검증에서 신뢰 신호가 발견되면 위험 점수가 감산됩니다.
            </p>
            <div className="overflow-x-auto rounded-lg border border-slate-700">
              <table className="w-full text-sm">
                <thead className="bg-slate-800/60 text-xs uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="px-3 py-2 text-left">플래그</th>
                    <th className="px-3 py-2 text-right">점수</th>
                    <th className="px-3 py-2 text-left">정당성</th>
                    <th className="px-3 py-2 text-left">출처</th>
                  </tr>
                </thead>
                <tbody>
                  {negative.map((f) => (
                    <tr key={f.flag} className="border-t border-slate-800 align-top">
                      <td className="px-3 py-3">
                        <div className="font-semibold text-slate-100">{f.label_ko}</div>
                        <div className="font-mono text-xs text-slate-500">{f.flag}</div>
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-emerald-300">
                        {f.score_delta}
                      </td>
                      <td className="px-3 py-3 text-xs text-slate-300">{f.rationale}</td>
                      <td className="px-3 py-3 text-xs text-slate-500">{f.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
          <h2 className="mb-3 text-lg font-semibold text-slate-100">설계 결정 (Threshold &amp; Weight)</h2>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div className="rounded bg-slate-950/40 p-3">
              <dt className="text-xs text-slate-400">LLM 플래그 가중치</dt>
              <dd className="mt-1 font-mono text-slate-100">
                {data.weights.llm_flag_score_ratio}
              </dd>
              <dd className="mt-1 text-xs text-slate-500">
                LLM 제안 플래그 점수에 곱해지는 비율. 1.0 미만이면 보수적.
              </dd>
            </div>
            <div className="rounded bg-slate-950/40 p-3">
              <dt className="text-xs text-slate-400">LLM 엔티티 병합 임계값</dt>
              <dd className="mt-1 font-mono text-slate-100">
                {data.weights.llm_entity_merge_threshold}
              </dd>
              <dd className="mt-1 text-xs text-slate-500">
                이 신뢰도 이상의 LLM 엔티티만 추출 결과에 합쳐집니다.
              </dd>
            </div>
            <div className="rounded bg-slate-950/40 p-3">
              <dt className="text-xs text-slate-400">LLM 플래그 신뢰 임계값</dt>
              <dd className="mt-1 font-mono text-slate-100">
                {data.weights.llm_flag_score_threshold}
              </dd>
              <dd className="mt-1 text-xs text-slate-500">
                이 신뢰도 이상이어야 LLM 제안 플래그가 채택됩니다.
              </dd>
            </div>
            <div className="rounded bg-slate-950/40 p-3">
              <dt className="text-xs text-slate-400">LLM 스캠 유형 오버라이드 임계값</dt>
              <dd className="mt-1 font-mono text-slate-100">
                {data.weights.llm_scam_type_override_threshold}
              </dd>
              <dd className="mt-1 text-xs text-slate-500">
                LLM 신뢰도가 이 이상이면 분류기 결과를 덮어씁니다.
              </dd>
            </div>
            <div className="rounded bg-slate-950/40 p-3">
              <dt className="text-xs text-slate-400">분류기 confidence 컷오프</dt>
              <dd className="mt-1 font-mono text-slate-100">
                {data.weights.classification_threshold}
              </dd>
              <dd className="mt-1 text-xs text-slate-500">
                mDeBERTa 분류 신뢰도가 이 이하면 &ldquo;판별 불가&rdquo;.
              </dd>
            </div>
            <div className="rounded bg-slate-950/40 p-3">
              <dt className="text-xs text-slate-400">GLiNER 추출 임계값</dt>
              <dd className="mt-1 font-mono text-slate-100">
                {data.weights.gliner_threshold}
              </dd>
              <dd className="mt-1 text-xs text-slate-500">
                재현율 우선(미탐 방지)으로 낮게 설정.
              </dd>
            </div>
          </dl>
        </section>

        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
          <h2 className="mb-3 text-lg font-semibold text-slate-100">📚 인용 학술·공식 출처</h2>
          <p className="mb-4 text-sm text-slate-400">
            플래그 점수 설계에 인용된 학술 자료와 공식 통계 출처입니다. 점수의 정량적 근거를 뒷받침합니다.
          </p>
          <div className="space-y-4 text-sm leading-relaxed text-slate-300">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-200">설득·사회공학 학술 자료</h3>
              <ul className="list-inside list-disc space-y-1 text-xs text-slate-400">
                <li>Cialdini, R. B. (2021). <em>Influence, New and Expanded: The Psychology of Persuasion</em>. Harper Business. — 권위·희소성·사회적 증거 6대 영향력 원리</li>
                <li>Whitty, M. T. (2013). The Scammers Persuasive Techniques Model. <em>British Journal of Criminology</em>, 53(4), 665–684.</li>
                <li>Whitty, M. T., &amp; Buchanan, T. (2012). The online romance scam: a serious cybercrime. <em>Cyberpsychology, Behavior, and Social Networking</em>, 15(3), 181–183.</li>
                <li>Stajano, F., &amp; Wilson, P. (2011). Understanding scam victims: Seven principles for systems security. <em>Communications of the ACM</em>, 54(3), 70–75.</li>
                <li>Modic, D., &amp; Lea, S. E. G. (2013). Scam Compliance and the Psychology of Persuasion. SSRN.</li>
                <li>Loewenstein, G. (1996). Out of control: Visceral influences on behavior. <em>Organizational Behavior and Human Decision Processes</em>, 65(3), 272–292.</li>
                <li>Witte, K. (1992). Putting the fear back into fear appeals: The Extended Parallel Process Model. <em>Communication Monographs</em>, 59(4), 329–349.</li>
                <li>Hadnagy, C. (2018). <em>Social Engineering: The Science of Human Hacking</em> (2nd ed.). Wiley.</li>
                <li>Anderson, R. (2008). <em>Security Engineering</em> (2nd ed.). Wiley. — Ch.2 사용자 보안 행동</li>
              </ul>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-200">금융사기·암호자산 사기</h3>
              <ul className="list-inside list-disc space-y-1 text-xs text-slate-400">
                <li>Frankel, T. (2012). <em>The Ponzi Scheme Puzzle</em>. Oxford University Press.</li>
                <li>Cross, C. (2023). Romance fraud and pig butchering. <em>Trends &amp; Issues in Crime and Criminal Justice</em>. Australian Institute of Criminology.</li>
                <li>FBI Internet Crime Complaint Center (IC3). <em>Annual Internet Crime Report</em>.</li>
                <li>Federal Trade Commission. <em>Consumer Sentinel Network Data Book</em>.</li>
              </ul>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-200">NLP·임베딩 기반 분석 기법</h3>
              <ul className="list-inside list-disc space-y-1 text-xs text-slate-400">
                <li>Reimers, N., &amp; Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. <em>EMNLP</em>.</li>
                <li>Cer, D. et al. (2017). SemEval-2017 Task 1: Semantic Textual Similarity Multilingual and Crosslingual Focused Evaluation. <em>SemEval</em>.</li>
              </ul>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-200">국내 공식 통계·법령</h3>
              <ul className="list-inside list-disc space-y-1 text-xs text-slate-400">
                <li>금융감독원 — 보이스피싱·유사수신 감독사례집 (연간), 메신저피싱 통계</li>
                <li>경찰청 사이버수사국 — 보이스피싱·메신저피싱·중고거래 사기 통계</li>
                <li>한국인터넷진흥원(KISA) — 보이스피싱 동향 보고서, 스미싱 차단 시스템, 피싱사이트 신고센터</li>
                <li>전기통신금융사기 피해 방지 및 환급에 관한 특별법, 자본시장법, 약사법, 직업안정법, 대부업법</li>
                <li>APWG (Anti-Phishing Working Group) — Phishing Activity Trends Report (분기 발행)</li>
                <li>SNU FactCheck, IFCN (International Fact-Checking Network) Code of Principles</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6">
          <h2 className="mb-3 text-lg font-semibold text-slate-100">사용 모델</h2>
          <ul className="space-y-2 text-sm">
            {Object.entries(data.models).map(([k, v]) => (
              <li key={k} className="flex justify-between rounded bg-slate-950/40 px-3 py-2">
                <span className="text-slate-400">{k}</span>
                <span className="font-mono text-slate-100">{v}</span>
              </li>
            ))}
          </ul>
        </section>

        <footer className="pt-2 text-center text-xs text-slate-500">
          <Link href="/" className="hover:text-slate-300">
            ← 홈으로
          </Link>
        </footer>
      </div>
    </main>
  );
}
