import AdminRunEditor from "./AdminRunEditor";

type PageProps = {
  params: Promise<{ runId: string }>;
};

export default async function AdminRunPage({ params }: PageProps) {
  const { runId } = await params;

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#111827_0%,#020617_60%,#000000_100%)] px-6 py-10 text-slate-100">
      <div className="mx-auto w-full max-w-7xl">
        <AdminRunEditor runId={runId} />
      </div>
    </main>
  );
}

