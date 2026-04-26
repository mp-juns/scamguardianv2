export const runtime = "nodejs";

const API_BASE_URL =
  process.env.SCAMGUARDIAN_API_URL ?? "http://127.0.0.1:8000";

function buildUrl(path: string) {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function POST(request: Request) {
  const formData = await request.formData();
  const response = await fetch(buildUrl("/api/analyze-upload"), {
    method: "POST",
    body: formData,
    cache: "no-store",
  });

  const text = await response.text();
  try {
    const json = text ? JSON.parse(text) : {};
    return new Response(JSON.stringify(json), {
      status: response.status,
      headers: {
        "content-type": "application/json",
      },
    });
  } catch {
    return new Response(
      JSON.stringify({
        detail: text || "분석 API 응답을 해석하지 못했습니다.",
      }),
      {
        status: response.status,
        headers: {
          "content-type": "application/json",
        },
      },
    );
  }
}

