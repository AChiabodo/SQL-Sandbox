# PostgreSQL Sandbox

PostgreSQL Sandbox e un laboratorio locale Docker-first per esplorare dataset realistici su PostgreSQL con una UI React/Vite, un backend FastAPI e strumenti assistiti per scrivere, validare e visualizzare query SQL.

L'applicazione nasce per fare pratica con modelli dati relazionali senza dover preparare manualmente schemi, seed e query di esempio: avvii lo stack, inizializzi una raccolta dati, navighi tabelle e colonne, esegui SQL o costruisci query low-code, poi trasformi i risultati in dashboard.

## Screenshot

### Editor SQL

![Editor SQL con dataset Sales Data Warehouse](docs/screenshots/sql-workbench.png)

### Dashboard

![Dashboard avanzata con widget generati dalle query starter](docs/screenshots/dashboard.png)

### Browser tabelle

![Browser tabelle con struttura e righe tabellari](docs/screenshots/table-browser.png)

## Obiettivo dell'applicazione

Il progetto fornisce una sandbox completa per:

- sperimentare con PostgreSQL su dataset realistici e rigenerabili;
- imparare a leggere schemi, relazioni, chiavi e tipi colonna;
- scrivere query SQL dirette con feedback immediato;
- costruire query `SELECT` senza codice tramite un query builder;
- creare dashboard operative da query read-only;
- testare guardrail contro query distruttive;
- preparare un flusso LLM naturale -> SQL configurabile con provider esterni o locali.

Il punto importante e che ogni dataset vive in uno schema PostgreSQL dedicato. Puoi rigenerare, per esempio, `sales_dw` senza intaccare `support_ops` o `commerce_ops`.

## Come funziona

Lo stack e composto da tre servizi:

| Servizio | Tecnologia | Porta host | Responsabilita |
| --- | --- | ---: | --- |
| `db` | PostgreSQL 16 | `55432` | Database locale e volume persistente |
| `backend` | FastAPI + psycopg | `18000` | API, introspezione schema, seed dataset, guardrail SQL, LLM SQL |
| `frontend` | React + Vite | `15173` | Interfaccia operativa, query editor, dashboard, chat LLM |

### Dataset disponibili

| ID | Schema | Contenuto |
| --- | --- | --- |
| `sales_dw` | `sales_dw` | Data warehouse vendite con dimensioni clienti, prodotti, canali, date, vendite e resi |
| `saas_billing` | `saas_billing` | Account, piani, sottoscrizioni, fatture, line item e usage events |
| `support_ops` | `support_ops` | Help desk con clienti, agenti, ticket, eventi e survey CSAT |
| `commerce_ops` | `commerce_ops` | Schema OLTP omnichannel con ordini, pagamenti, spedizioni, resi, procurement e inventario |

Ogni dataset espone tre query starter. La UI le carica nell'editor SQL e le usa anche come base per i widget della dashboard.

### Modalita della UI

- `SQL diretto`: editor Monaco, autocomplete su schema/tabelle/colonne, formattazione SQL, `EXPLAIN`, cronologia sessione e invio query alla dashboard.
- `Low code`: query builder per selezioni, filtri, aggregazioni, group by, ordinamenti, limit/offset e join basati sulle relazioni.
- `Dashboard`: griglia di widget persistita in `localStorage`, con grafici Recharts, refresh automatico e modifica delle query.
- `Tabelle complete`: browser tabellare per ispezionare struttura, colonne e righe con paginazione.
- `Chat LLM`: pannello per generare SQL da prompt naturale quando un provider LLM e configurato.

### Guardrail SQL

Il backend classifica le query prima dell'esecuzione. Le query potenzialmente distruttive richiedono conferma esplicita quando passano dall'endpoint SQL diretto.

Sono considerate rischiose, tra le altre:

- `DROP`
- `TRUNCATE`
- `ALTER SYSTEM`
- `REINDEX`
- `VACUUM FULL`
- `GRANT` / `REVOKE`
- `DELETE` senza `WHERE`
- `UPDATE` senza `WHERE`

La dashboard accetta solo query read-only.

## Setup locale con Docker

Prerequisiti:

- Docker Desktop o Docker Engine con Docker Compose;
- porte `15173`, `18000` e `55432` libere, oppure personalizzate in `.env`.

Avvio rapido:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Servizi disponibili:

- Frontend: http://localhost:15173
- Backend API: http://localhost:18000
- PostgreSQL: `localhost:55432`
- Credenziali database di default: `sandbox` / `sandbox`
- Database di default: `sandbox`

Al primo avvio PostgreSQL parte senza dataset applicativi. La cartella `db/init` contiene solo un bootstrap vuoto: gli schemi vengono creati on-demand dalla UI o via API.

Flusso consigliato:

1. Apri http://localhost:15173.
2. Scegli una raccolta dati nella sidebar.
3. Premi `Inizializza` se il dataset e vuoto.
4. Usa `SQL diretto`, `Low code`, `Dashboard` o `Tabelle complete`.
5. Usa `Rigenera` per ricreare da zero solo lo schema del dataset selezionato.

## Setup locale senza Docker completo

Puoi anche usare solo PostgreSQL in Docker e avviare backend/frontend dall'host.

Avvia il database:

```powershell
docker compose up -d db
```

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://sandbox:sandbox@localhost:55432/sandbox"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL = "http://localhost:8000"
npm run dev
```

In questo scenario il frontend Vite usera la porta proposta da Vite, di solito http://localhost:5173.

## Configurazione

Le variabili principali sono in `.env.example`.

| Variabile | Default | Descrizione |
| --- | --- | --- |
| `POSTGRES_USER` | `sandbox` | Utente PostgreSQL |
| `POSTGRES_PASSWORD` | `sandbox` | Password PostgreSQL |
| `POSTGRES_DB` | `sandbox` | Database applicativo |
| `POSTGRES_HOST_PORT` | `55432` | Porta host del database |
| `BACKEND_HOST_PORT` | `18000` | Porta host del backend |
| `FRONTEND_HOST_PORT` | `15173` | Porta host del frontend |
| `DATABASE_URL` | `postgresql://sandbox:sandbox@db:5432/sandbox` | Connessione usata dal backend nel network Docker |
| `FRONTEND_ORIGIN` | `http://localhost:15173` | Origin ammesso dal CORS backend |
| `VITE_API_BASE_URL` | `http://localhost:18000` | Base URL API usata dal frontend |

### Provider LLM

La generazione SQL via chat e opzionale. Senza chiavi configurate, la UI mostra lo stato del provider e il backend restituisce un messaggio esplicito.

Provider supportati dalla configurazione:

- `openai`
- `azure`
- `anthropic`
- `openrouter`
- `lm_studio`

Esempio OpenRouter:

```powershell
DEFAULT_PROVIDER=openrouter
OPENROUTER__API_KEY=...
OPENROUTER__DEFAULT_MODEL=openai/gpt-4o-mini
```

Esempio LM Studio con backend in Docker:

```powershell
DEFAULT_PROVIDER=lm_studio
LM_STUDIO__BASE_URL=http://host.docker.internal:1234/v1
LM_STUDIO__DEFAULT_MODEL=local-model
```

## API principali

| Metodo | Endpoint | Descrizione |
| --- | --- | --- |
| `GET` | `/health` | Stato del backend |
| `GET` | `/db/status` | Versione PostgreSQL, database, schema e server time |
| `GET` | `/db/schema` | Introspezione schemi, tabelle, colonne e relazioni |
| `GET` | `/datasets` | Catalogo dataset e stato di inizializzazione |
| `POST` | `/datasets/{dataset_id}/initialize` | Drop e ricreazione dello schema del dataset |
| `GET` | `/db/tables/{schema}/{table}/rows` | Righe tabellari paginate |
| `POST` | `/sql/execute` | Esecuzione SQL con guardrail |
| `POST` | `/sql/explain` | `EXPLAIN` solo per query read-only |
| `POST` | `/dashboard/query` | Query read-only per widget dashboard |
| `POST` | `/query-builder/compile` | Compilazione query builder in SQL parametrizzato |
| `POST` | `/query-builder/execute` | Esecuzione query builder |
| `GET` | `/llm/status` | Stato provider LLM |
| `POST` | `/llm/generate-sql` | Generazione SQL via agente LLM |
| `POST` | `/llm/generate-sql/stream` | Generazione SQL in streaming SSE |

## Test

Con lo stack Docker attivo:

```powershell
docker compose run --rm --no-deps backend python -m pytest tests
```

Da host:

```powershell
cd backend
python -m pytest tests
```

I test che richiedono PostgreSQL usano di default:

```text
postgresql://sandbox:sandbox@localhost:55432/sandbox
```

Puoi sovrascriverlo con `TEST_DATABASE_URL`.

## Reset completo

Per eliminare il volume PostgreSQL e ripartire da zero:

```powershell
docker compose down -v
docker compose up --build
```

Questo cancella tutti gli schemi e i dati presenti nel volume Docker.
