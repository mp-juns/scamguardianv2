export const runtime = "nodejs";

const API_BASE_URL =
  process.env.SCAMGUARDIAN_API_URL ?? "http://127.0.0.1:8000";

type Context = {
  params: Promise<{ runId: string }>;
};

export async function GET(request: Request, context: Context) {
  const { runId } = await context.params;
  const targetUrl = `${API_BASE_URL}/api/admin/runs/${encodeURIComponent(runId)}/media`;

  const forwardHeaders = new Headers();
  const range = request.headers.get("range");
  if (range) forwardHeaders.set("range", range);

  try {
    const upstream = await fetch(targetUrl, {
      method: "GET",
      headers: forwardHeaders,
      cache: "no-store",
    });

    const passthrough = new Headers();
    for (const key of [
      "content-type",
      "content-length",
      "content-range",
      "accept-ranges",
      "content-disposition",
      "cache-control",
    ]) {
      const v = upstream.headers.get(key);
      if (v) passthrough.set(key, v);
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: passthrough,
    });
  } catch (error) {
    return Response.json(
      {
        detail: "미디어 프록시 실패",
        debug: {
          target_url: targetUrl,
          error: error instanceof Error ? error.message : String(error),
        },
      },
      { status: 502 },
    );
  }
}
