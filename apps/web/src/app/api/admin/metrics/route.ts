import { proxyGet } from "../../_lib/backend";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return proxyGet(`/api/admin/metrics${search}`);
}

