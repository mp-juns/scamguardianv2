import { proxyGet } from "../../../_lib/backend";

export const runtime = "nodejs";

type Context = {
  params: Promise<{ runId: string }>;
};

export async function GET(_: Request, context: Context) {
  const { runId } = await context.params;
  return proxyGet(`/api/admin/runs/${runId}`);
}

