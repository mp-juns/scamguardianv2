import { NextResponse } from "next/server";

export const runtime = "nodejs";

const API_BASE_URL =
  process.env.SCAMGUARDIAN_API_URL ?? "http://127.0.0.1:8000";

function buildUrl(path: string) {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

function errorToMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function parseJsonSafely(text: string) {
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export async function proxyJsonRequest(request: Request, path: string) {
  const body = await request.text();
  const targetUrl = buildUrl(path);

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
    });

    const text = await response.text();
    return NextResponse.json(parseJsonSafely(text), {
      status: response.status,
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail:
          "분석 API에 연결하지 못했습니다. Python 서버와 환경 변수를 확인해주세요.",
        debug: {
          target_url: targetUrl,
          error: errorToMessage(error),
        },
      },
      { status: 502 },
    );
  }
}

export async function proxyRaw(request: Request, path: string) {
  const targetUrl = buildUrl(path);
  try {
    const body = await request.arrayBuffer();
    const headers = new Headers();
    request.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (!["host", "connection", "transfer-encoding"].includes(lower)) {
        headers.set(key, value);
      }
    });
    const response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: body.byteLength > 0 ? body : undefined,
      cache: "no-store",
    });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail: "분석 API에 연결하지 못했습니다.",
        debug: { target_url: targetUrl, error: errorToMessage(error) },
      },
      { status: 502 },
    );
  }
}

export async function proxyGet(path: string) {
  const targetUrl = buildUrl(path);
  try {
    const response = await fetch(targetUrl, {
      cache: "no-store",
    });
    const text = await response.text();
    return NextResponse.json(parseJsonSafely(text), {
      status: response.status,
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail:
          "분석 API에 연결하지 못했습니다. Python 서버와 환경 변수를 확인해주세요.",
        debug: {
          target_url: targetUrl,
          error: errorToMessage(error),
        },
      },
      { status: 502 },
    );
  }
}

