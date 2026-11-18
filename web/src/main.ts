import { ApiError, type Answer, type Doc, RagClient } from "./client.js";

const client = new RagClient({ baseUrl: "/api" });
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

// All dynamic text goes through textContent / createTextNode: document content is untrusted.
function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  cls?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Request failed");

async function refreshDocs(): Promise<void> {
  const list = $("docs");
  let docs: Doc[];
  try {
    docs = await client.listDocuments();
  } catch (e) {
    list.replaceChildren(el("li", "muted", errText(e)));
    return;
  }
  if (!docs.length) return list.replaceChildren(el("li", "muted", "No documents yet"));
  list.replaceChildren(
    ...docs.map((d) => {
      const li = el("li");
      li.append(el("span", "name", d.title), el("span", "muted", ` ${d.pages}p · ${d.chunks} chunks`));
      const del = el("button", "link", "delete");
      del.onclick = async () => {
        await client.deleteDocument(d.id).catch(() => undefined);
        void refreshDocs();
      };
      li.append(del);
      return li;
    }),
  );
}

function renderAnswer(a: Answer): HTMLElement {
  const box = el("div", a.grounded ? "msg bot" : "msg bot refused");
  box.append(el("p", "", a.answer));
  if (a.citations.length) {
    const row = el("div", "cites");
    for (const c of a.citations) {
      const chip = el("details", "cite");
      chip.append(el("summary", "", `[${c.n}] ${c.title}, p.${c.page}`), el("blockquote", "", c.snippet));
      row.append(chip);
    }
    box.append(row);
  }
  return box;
}

$<HTMLFormElement>("chat").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const input = $<HTMLInputElement>("q");
  const q = input.value.trim();
  if (!q) return;
  input.value = "";
  const log = $("log");
  log.append(el("div", "msg user", q));
  const pending = el("div", "msg bot muted", "Searching…");
  log.append(pending);
  try {
    pending.replaceWith(renderAnswer(await client.ask(q)));
  } catch (e) {
    pending.replaceWith(el("div", "msg bot refused", errText(e)));
  }
  log.scrollTop = log.scrollHeight;
});

$<HTMLInputElement>("file").addEventListener("change", async (ev) => {
  const input = ev.target as HTMLInputElement;
  const status = $("status");
  for (const f of Array.from(input.files ?? [])) {
    status.textContent = `Indexing ${f.name}…`;
    try {
      const r = await client.upload(f);
      status.textContent = r.skipped ? `${f.name}: already indexed` : `${f.name}: ${r.chunks} chunks`;
    } catch (e) {
      status.textContent = `${f.name}: ${errText(e)}`;
    }
  }
  input.value = "";
  void refreshDocs();
});

void refreshDocs();
