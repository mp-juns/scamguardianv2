import PlatformClient from "./PlatformClient";

export const dynamic = "force-dynamic";

export default function PlatformPage() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#111827_0%,#020617_60%,#000000_100%)] px-4 py-8 text-slate-100 sm:px-6">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <header>
          <p className="text-sm text-slate-400">ScamGuardian Admin</p>
          <h1 className="text-3xl font-semibold text-white">⚙️ Platform</h1>
          <p className="mt-2 text-sm text-slate-400">
            API key 발급·관리 · 요청 observability · 외부 API 비용 추적.
          </p>
        </header>
        <PlatformClient />
      </div>
    </main>
  );
}
