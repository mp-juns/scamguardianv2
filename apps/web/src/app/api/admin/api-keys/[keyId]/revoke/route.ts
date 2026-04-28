import { proxyJsonRequest } from "../../../../_lib/backend";

export const runtime = "nodejs";

type Context = { params: Promise<{ keyId: string }> };

export async function POST(request: Request, context: Context) {
  const { keyId } = await context.params;
  return proxyJsonRequest(request, `/api/admin/api-keys/${encodeURIComponent(keyId)}/revoke`);
}
