import { proxyRaw } from "../../api/_lib/backend";

export const runtime = "nodejs";

// 카카오 오픈빌더 Skill 엔드포인트 프록시
// Next.js(3100)를 Tailscale Funnel로 노출하면 이 경로로 웹훅이 들어온다.
export async function POST(request: Request) {
  return proxyRaw(request, "/webhook/kakao");
}
