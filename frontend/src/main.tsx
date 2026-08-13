import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Source = {
  source_id: string;
  rule_number: string | null;
  title: string;
  source_type: "rule" | "guidance";
  source_url: string;
  normalized: boolean;
};

type RetrievedChunk = {
  chunk_id: string;
  rule_number: string | null;
  section_path: string;
  subsection: string | null;
  source_type: "rule" | "guidance";
  source_url: string;
  retrieved_at: string;
  content: string;
  score: number;
};

type QueryResponse = {
  answer: string;
  citations: Array<{
    rule_number: string | null;
    subsection: string | null;
    title: string;
    source_url: string;
    supporting_excerpt: string;
  }>;
  abstained: boolean;
  retrieved_chunks: RetrievedChunk[];
  retrieval_configuration: string;
  prompt_version: string;
  disclaimer: string;
};

function App() {
  const [question, setQuestion] = useState("What customer information must a member maintain?");
  const [mode, setMode] = useState("hybrid");
  const [sources, setSources] = useState<Source[]>([]);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/sources")
      .then((response) => response.json())
      .then(setSources)
      .catch(() => setError("Could not load the FINRA source manifest."));
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, retrieval_mode: mode, top_k: 5 }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Query failed.");
      setResult(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Query failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">FINRA-ONLY · SOURCE-GROUNDED</p>
        <h1>Compliance evidence, not confident guesses.</h1>
        <p className="lede">
          Ask about the indexed FINRA rules, inspect the exact retrieved passages, and see when
          the evidence is insufficient.
        </p>
      </header>

      <section className="card query-card">
        <form onSubmit={submit}>
          <label htmlFor="question">Question</label>
          <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} />
          <div className="controls">
            <select value={mode} onChange={(event) => setMode(event.target.value)} aria-label="Retrieval mode">
              <option value="hybrid">Hybrid (keyword + vector when configured)</option>
              <option value="keyword">Keyword</option>
              <option value="vector">Vector (requires embeddings)</option>
            </select>
            <button disabled={loading || question.trim().length < 3}>{loading ? "Retrieving…" : "Ask FINRA sources"}</button>
          </div>
        </form>
        {error && <p className="error">{error}</p>}
      </section>

      {result && (
        <section className="card result-card">
          <div className="result-heading">
            <div>
              <p className="eyebrow">{result.retrieval_configuration}</p>
              <h2>{result.abstained ? "Insufficient evidence" : "Grounded evidence"}</h2>
            </div>
            <span className={result.abstained ? "badge warning" : "badge"}>{result.abstained ? "ABSTAINED" : "CITED"}</span>
          </div>
          <p className="answer">{result.answer}</p>
          {result.citations.length > 0 && (
            <div className="citations">
              <h3>Citations</h3>
              {result.citations.map((citation, index) => (
                <a href={citation.source_url} target="_blank" rel="noreferrer" key={`${citation.source_url}-${index}`}>
                  FINRA Rule {citation.rule_number ?? "guidance"} {citation.subsection ?? ""} · {citation.title}
                </a>
              ))}
            </div>
          )}
          <details>
            <summary>Retrieved evidence ({result.retrieved_chunks.length} passages)</summary>
            {result.retrieved_chunks.map((chunk) => (
              <article className="evidence" key={chunk.chunk_id}>
                <div className="evidence-meta">{chunk.section_path} · retrieved {new Date(chunk.retrieved_at).toLocaleDateString()}</div>
                <p>{chunk.content}</p>
              </article>
            ))}
          </details>
          <p className="disclaimer">{result.disclaimer}</p>
        </section>
      )}

      <section className="card corpus-card">
        <div>
          <p className="eyebrow">INDEXED CORPUS</p>
          <h2>{sources.filter((source) => source.source_type === "rule").length} rules · {sources.filter((source) => source.source_type === "guidance").length} guidance pages</h2>
        </div>
        <div className="source-list">
          {sources.map((source) => <a href={source.source_url} target="_blank" rel="noreferrer" key={source.source_id}>{source.rule_number ?? source.title}</a>)}
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
