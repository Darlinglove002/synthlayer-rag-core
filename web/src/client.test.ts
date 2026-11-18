import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, RagClient } from "./client.js";

type Call = { url: string; init: RequestInit };

function mock(status: number, body: unknown) {
  const calls: Call[] = [];
  const f = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(status === 204 ? null : JSON.stringify(body), { status });
  }) as unknown as typeof fetch;
  return { calls, f };
}

test("ask posts JSON to /ask and returns the typed answer", async () => {
  const body = { answer: "14 days [1]", grounded: true, generator: "extractive", citations: [], sources: [] };
  const { calls, f } = mock(200, body);
  const out = await new RagClient({ baseUrl: "/api/", fetch: f }).ask("how long?", 3);
  assert.equal(out.answer, "14 days [1]");
  assert.equal(calls[0]!.url, "/api/ask"); // trailing slash in baseUrl is normalised
  assert.deepEqual(JSON.parse(calls[0]!.init.body as string), { query: "how long?", top_k: 3 });
});

test("search unwraps hits and sends the mode", async () => {
  const { calls, f } = mock(200, { hits: [{ chunk_id: 1 }] });
  const hits = await new RagClient({ fetch: f }).search("x", "lexical", 2);
  assert.equal(hits.length, 1);
  assert.deepEqual(JSON.parse(calls[0]!.init.body as string), { query: "x", mode: "lexical", top_k: 2 });
});

test("api key is sent as X-API-Key only when configured", async () => {
  const a = mock(200, []);
  await new RagClient({ apiKey: "k", fetch: a.f }).listDocuments();
  assert.equal(new Headers(a.calls[0]!.init.headers).get("X-API-Key"), "k");
  const b = mock(200, []);
  await new RagClient({ fetch: b.f }).listDocuments();
  assert.equal(new Headers(b.calls[0]!.init.headers).get("X-API-Key"), null);
});

test("errors carry status and the FastAPI detail message", async () => {
  const { f } = mock(422, { detail: "unsupported file type: .exe" });
  await assert.rejects(
    new RagClient({ fetch: f }).listDocuments(),
    (e: unknown) => e instanceof ApiError && e.status === 422 && e.message === "unsupported file type: .exe",
  );
});

test("validation errors (detail is a list) use the first message", async () => {
  const { f } = mock(422, { detail: [{ msg: "String should have at least 1 character" }] });
  await assert.rejects(new RagClient({ fetch: f }).ask(""), /at least 1 character/);
});

test("delete handles 204 without a body", async () => {
  const { calls, f } = mock(204, null);
  await new RagClient({ fetch: f }).deleteDocument(7);
  assert.equal(calls[0]!.url, "/api/documents/7");
  assert.equal(calls[0]!.init.method, "DELETE");
});

test("upload sends multipart without forcing a Content-Type", async () => {
  const { calls, f } = mock(201, { document_id: 1, title: "a", pages: 1, chunks: 1, skipped: false });
  await new RagClient({ fetch: f }).upload(new File(["hello"], "a.txt"));
  assert.ok(calls[0]!.init.body instanceof FormData);
  assert.equal(new Headers(calls[0]!.init.headers).get("Content-Type"), null); // browser adds the boundary
});

test("non-JSON error body falls back to the status text", async () => {
  const f = (async () => new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" })) as unknown as typeof fetch;
  await assert.rejects(new RagClient({ fetch: f }).listDocuments(), (e: unknown) => e instanceof ApiError && e.status === 502);
});
