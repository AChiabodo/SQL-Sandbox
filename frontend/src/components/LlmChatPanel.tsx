import { Bot, MessageSquareText, Send, Sparkles } from "lucide-react";

import type { ChatMessage, DatasetCatalogItem, LlmProgressEvent, LlmStatus } from "../types";

type LlmChatPanelProps = {
  llmStatus: LlmStatus | null;
  activeDataset: DatasetCatalogItem | null;
  prompt: string;
  loading: boolean;
  messages: ChatMessage[];
  progressEvents: LlmProgressEvent[];
  onPromptChange: (value: string) => void;
  onSubmit: () => Promise<void>;
  onUseSql: (sql: string) => void;
};

export function LlmChatPanel({
  llmStatus,
  activeDataset,
  prompt,
  loading,
  messages,
  progressEvents,
  onPromptChange,
  onSubmit,
  onUseSql
}: LlmChatPanelProps) {
  return (
    <div className="mode-layout llm-layout">
      <section className="workspace-card llm-hero-card">
        <div className="section-title split">
          <div>
            <p className="section-kicker">Assistente</p>
            <h2>Chat LLM</h2>
          </div>
          <span className={llmStatus?.enabled ? "status-pill active" : "status-pill"}>
            {llmStatus?.enabled ? "Configurato" : "Non configurato"}
          </span>
        </div>
        <p className="muted">
          Conversa in linguaggio naturale sul dataset attivo e genera SQL riutilizzabile
          nell'editor.
        </p>
        <div className="workspace-context spacious">
          <span>{activeDataset?.name ?? "Nessuna raccolta selezionata"}</span>
          <MessageSquareText size={14} />
          <span>{llmStatus?.provider ?? "provider non impostato"}</span>
          {llmStatus?.model && <span>{llmStatus.model}</span>}
        </div>
      </section>

      <div className="llm-chat-shell">
        <section className="workspace-card chat-transcript-card">
          <div className="section-title">
            <Bot size={18} />
            <h2>Conversazione</h2>
          </div>
          {messages.length === 0 ? (
            <div className="chat-empty-state">
              <Sparkles size={18} />
              <p>Invia una richiesta come “mostra il fatturato mensile per piano”.</p>
            </div>
          ) : (
            <div className="chat-thread">
              {messages.map((message) => (
                <article
                  key={message.id}
                  className={message.role === "assistant" ? "chat-bubble assistant" : "chat-bubble user"}
                >
                  <span className="chat-role">
                    {message.role === "assistant" ? "Assistente" : "Tu"}
                  </span>
                  <p>{message.content}</p>
                  {message.clarifyingQuestions && message.clarifyingQuestions.length > 0 && (
                    <div className="chat-detail-list">
                      <strong>Domande</strong>
                      {message.clarifyingQuestions.map((question) => (
                        <span key={question}>{question}</span>
                      ))}
                    </div>
                  )}
                  {message.sql && (
                    <div className="chat-sql-preview">
                      <pre>{message.sql}</pre>
                      <button onClick={() => onUseSql(message.sql ?? "")}>Usa nell'editor SQL</button>
                    </div>
                  )}
                  {(message.usedTables?.length || message.assumptions?.length || message.validationSummary) && (
                    <div className="chat-detail-list">
                      {message.usedTables?.length ? (
                        <span> Tabelle: {message.usedTables.join(", ")}</span>
                      ) : null}
                      {message.assumptions?.length ? (
                        <span> Assunzioni: {message.assumptions.join("; ")}</span>
                      ) : null}
                      {message.validationSummary ? <span>{message.validationSummary}</span> : null}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="workspace-card chat-composer-card">
          <div className="section-title">
            <Send size={18} />
            <h2>Nuovo prompt</h2>
          </div>
          {!llmStatus?.enabled && (
            <div className="warning">
              <Sparkles size={16} />
              <span>
                Provider non configurato: configura un provider LangChain nel file .env.
              </span>
            </div>
          )}
          {progressEvents.length > 0 && (
            <div className="progress-stack">
              {progressEvents.map((event, index) => (
                <div key={`${event.stage}-${index}`} className="progress-row">
                  <span>{event.stage}</span>
                  <p>{event.message}</p>
                </div>
              ))}
            </div>
          )}
          <textarea
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            placeholder="Descrivi la query che vuoi ottenere..."
          />
          <div className="actions">
            <button className="primary" onClick={() => void onSubmit()} disabled={loading}>
              <Send size={16} />
              Invia
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
