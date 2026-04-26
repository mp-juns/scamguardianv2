import { proxyGet } from "../../../_lib/backend";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const params = new URLSearchParams();
  if (searchParams.get("status")) params.set("status", searchParams.get("status")!);
  if (searchParams.get("limit")) params.set("limit", searchParams.get("limit")!);
  if (searchParams.get("offset")) params.set("offset", searchParams.get("offset")!);
  const qs = params.toString();
  return proxyGet(`/api/admin/runs${qs ? `?${qs}` : ""}`);
}
