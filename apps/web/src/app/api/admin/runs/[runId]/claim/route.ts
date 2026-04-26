import { proxyJsonRequest } from "../../../../_lib/backend";

export const runtime = "nodejs";

type Context = {
  params: Promise<{ runId: string }>;
};

export async function POST(request: Request, context: Context) {
  const { runId } = await context.params;
  return proxyJsonRequest(request, `/api/admin/runs/${runId}/claim`);
}
