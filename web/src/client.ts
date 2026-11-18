// Typed client for synthlayer-rag-core. Zero dependencies: only fetch, FormData and AbortSignal.

export type Mode = "dense" | "lexical" | "hybrid" | "hybrid_rerank";

export interface Citation {
  n: number;
  document_id: number;
  title: string;
  page: number;
  snippet: string;
}
export interface Source {
  title: string;
  page: number;
  score: number;
  content: string;
}
export interface Answer {
  answer: string;
  grounded: boolean;
  generator: string;
  citations: Citation[];
  sources: Source[];
}
export interface Hit {
  chunk_id: number;
  document_id: number;
  title: string;
  page: number;
  content: string;
  score: number;
  dense_rank: number | null;
  lexical_rank: number | null;
  rerank_score: number | null;
}
export interface Doc {
  id: number;
  title: string;
  source: string;
  pages: number;
  chunks: number;
  created_at: string;
}
export interface UploadResult {
  document_id: number;
  title: string;
  pages: number;
  chunks: number;
  skipped: boolean;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ClientOptions {
  baseUrl?: string; // "/api" behind the bundled nginx, or e.g. "http://localhost:8020"
  apiKey?: string; // sent as X-API-Key when the server has API_KEY set
  timeoutMs?: number;
  fetch?: typeof fetch; // injectable for tests
}

export class RagClient {
  private base: string;
  private key?: string;
  private timeout: number;
  private f: typeof fetch;

  constructor(opts: ClientOptions = {}) {
    this.base = (opts.baseUrl ?? "/api").replace(/\/+$/, "");
    this.key = opts.apiKey;
    this.timeout = opts.timeoutMs ?? 60_000;
    this.f = opts.fetch ?? ((...a) => fetch(...a));
  }

  private async req<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (this.key) headers.set("X-API-Key", this.key);
    const res = await this.f(this.base + path, {
      ...init,
      headers,
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        // FastAPI: {detail: "..."} or, for validation errors, {detail: [{msg}, ...]}
        detail = typeof body.detail === "string" ? body.detail : (body.detail?.[0]?.msg ?? detail);
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(res.status, detail);
    }
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  }

  private json(body: unknown): RequestInit {
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    };
  }

  ask(query: string, topK = 5): Promise<Answer> {
    return this.req("/ask", this.json({ query, top_k: topK }));
  }

  async search(query: string, mode: Mode = "hybrid_rerank", topK = 5): Promise<Hit[]> {
    const r = await this.req<{ hits: Hit[] }>("/search", this.json({ query, mode, top_k: topK }));
    return r.hits;
  }

  listDocuments(): Promise<Doc[]> {
    return this.req("/documents");
  }

  upload(file: File): Promise<UploadResult> {
    const form = new FormData();
    form.append("file", file, file.name);
    return this.req("/documents", { method: "POST", body: form });
  }

  deleteDocument(id: number): Promise<void> {
    return this.req(`/documents/${id}`, { method: "DELETE" });
  }
}
