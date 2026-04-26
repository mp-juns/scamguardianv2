export const runtime = "nodejs";

import { proxyGet, proxyJsonRequest } from "../../_lib/backend";

export async function GET() {
  return proxyGet("/api/admin/scam-types");
}

export async function POST(request: Request) {
  return proxyJsonRequest(request, "/api/admin/scam-types");
}
