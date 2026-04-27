import { proxyGet } from "../../../api/_lib/backend";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ token: string }>;
};

// 카카오 카드의 "자세히 보기" 링크 → 백엔드 /api/result/{token} 으로 프록시
export async function GET(_request: Request, context: RouteContext) {
  const { token } = await context.params;
  return proxyGet(`/api/result/${encodeURIComponent(token)}`);
}
