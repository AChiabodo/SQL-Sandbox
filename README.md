# PostgreSQL Sandbox

Ambiente Docker-first per sperimentare con PostgreSQL tramite backend FastAPI e frontend React/Vite.

## Avvio

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Al primo avvio il database parte vuoto. Le raccolte dati di esempio si inizializzano dalla UI oppure via API.

Servizi:

- Frontend: http://localhost:15173
- Backend API: http://localhost:18000
- PostgreSQL: localhost:55432 (`sandbox` / `sandbox`)

## Funzionalita

- Catalogo di raccolte dati di esempio inizializzabili on-demand:
  - `sales_dw`: data warehouse vendite con schema a stella
  - `saas_billing`: account, sottoscrizioni, fatture e usage events
  - `support_ops`: ticketing, storico eventi e survey CSAT
- Ogni raccolta dati vive in uno schema PostgreSQL dedicato e puo essere rigenerata senza intaccare le altre.
- Esplorazione schemi, tabelle e colonne.
- Visualizzazione righe tabellari con paginazione.
- Query builder low-code per `SELECT`, filtri, aggregazioni, `GROUP BY`, ordinamenti e `LIMIT`.
- Editor SQL diretto con `EXPLAIN` ed esecuzione.
- Guardrail per query distruttive: `DROP`, `TRUNCATE`, `DELETE` senza `WHERE`, `UPDATE` senza `WHERE` e pattern simili richiedono conferma esplicita dalla UI/API.
- Stub LLM pronto per futuri provider di traduzione linguaggio naturale -> SQL.

## API principali

- `GET /health`
- `GET /db/status`
- `GET /db/schema`
- `GET /datasets`
- `POST /datasets/{dataset_id}/initialize`
- `GET /db/tables/{schema}/{table}/rows`
- `POST /sql/execute`
- `POST /sql/explain`
- `POST /query-builder/compile`
- `POST /query-builder/execute`
- `GET /llm/status`
- `POST /llm/translate-query`

## Test backend

Da container:

```powershell
docker compose run --rm --no-deps backend python -m pytest tests
```

Da host:

```powershell
cd backend
python -m pytest tests
```

## Workflow dataset

1. Avvia lo stack con `docker compose up --build`.
2. Apri la UI e seleziona una raccolta dati nella sidebar.
3. Usa `Inizializza` per creare lo schema e popolare migliaia di record.
4. Cambia raccolta dati per filtrare lo schema attivo e usare le query starter dedicate.
5. Usa `Rigenera` per ricreare da zero una singola raccolta senza toccare le altre.

## Reset di un volume gia esistente

Se hai gia avviato una versione precedente con dati seed nel vecchio schema `public`, fai un reset una tantum del volume PostgreSQL:

```powershell
docker compose down -v
docker compose up --build
```

## Note LLM

Per abilitare la generazione SQL, configura:

- `DEFAULT_PROVIDER`
- `<PROVIDER>__API_KEY`
- `<PROVIDER>__DEFAULT_MODEL`

Esempio OpenRouter:

```powershell
DEFAULT_PROVIDER=openrouter
OPENROUTER__API_KEY=...
OPENROUTER__DEFAULT_MODEL=openai/gpt-4o-mini
```

L'endpoint `POST /llm/translate-query` restituisce uno stato esplicito se il provider selezionato non e configurato.
