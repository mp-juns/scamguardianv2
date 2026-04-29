import { proxyJsonRequest } from "../../../../_lib/backend";

export const runtime = "nodejs";

type Context = { params: Promise<{ userId: string }> };

export async function POST(request: Request, context: Context) {
  const { userId } = await context.params;
  return proxyJsonRequest(
    request,
    `/api/admin/abuse-blocks/${encodeURIComponent(userId)}/unblock`,
  );
}
