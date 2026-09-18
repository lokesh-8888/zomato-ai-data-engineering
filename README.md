# Zomato AI Data Engineering

An end-to-end data engineering and AI project for analyzing Zomato-style food delivery data. The project loads raw data into Snowflake, transforms it with dbt, orchestrates batch processing with Airflow, and provides AI-powered review analysis and natural-language SQL interfaces.

The intended data journey is:

```text
Zomato-style CSV data -> object storage / Snowflake RAW -> dbt STAGING -> dbt MARTS -> AI applications
```

The project follows a medallion-style layout: RAW is the ingestion layer, STAGING contains cleaned and typed views, and MARTS contains business-ready dimensions, facts, and aggregates. The AI layer enriches review text and makes the warehouse and reviews accessible through Streamlit applications.

## Technology Stack

Python, Pandas, Snowflake, dbt with `dbt-snowflake`, Apache Airflow 3 with Docker, OpenRouter through the OpenAI-compatible SDK, NumPy, and Streamlit.

## Architecture

```text
Raw files / Snowflake RAW
          |
          v
   Airflow batch DAG
          |
          +--> Reload Snowflake RAW tables
          +--> dbt staging models
          +--> dbt mart models
          +--> AI review enrichment
          +--> dbt AI models
          |
          v
 Snowflake STAGING, MARTS, and AI schemas
          |
          +--> Streamlit text-to-SQL app
          +--> Streamlit review RAG assistant
```

The scheduled Airflow workflow is:

```text
reload_raw -> dbt_build_core -> enrich_reviews -> dbt_build_ai
```

`reload_raw` copies staged source files into Snowflake RAW tables. Core dbt models then create the cleaned staging views and marts. New reviews are classified into structured sentiment, topic, and issue fields before the AI-tagged dbt models are built.

## Repository Layout

```text
ai/
  enrich_reviews.py       Classifies reviews with an OpenRouter model
  rag_chat.py             Streamlit review-search assistant
  text_to_sql.py          Streamlit natural-language SQL assistant
  .env                    Local Snowflake and OpenRouter configuration

airflow/
  docker-compose.yaml     Local Airflow and PostgreSQL services
  Dockerfile              Airflow image with Snowflake and dbt dependencies
  dags/zomato_batch.py   Batch pipeline definition
  logs/                   Local Airflow logs

zomato/
  dbt_project.yml         dbt project configuration
  profiles.yml            Snowflake dbt profile
  models/staging/         Staging views
  models/marts/           Analytics tables
  models/marts/*_yml      Model sources and documentation
  tests/                  dbt tests

review_embeddings.parquet Cached review embeddings used by the RAG app
```

## Data Model

The dbt project separates warehouse objects into these layers:

| Layer | Snowflake schema | Purpose |
| --- | --- | --- |
| RAW | `ZOMATO.RAW` | Source tables loaded from the external stage |
| STAGING | `ZOMATO.STAGING` | Cleaned, typed, and standardized views |
| MARTS | `ZOMATO.MARTS` | Dimensions, facts, and business metrics |
| AI | `ZOMATO.AI` | Enriched review data and AI-specific models |

The marts support questions such as daily city revenue, restaurant performance, delivery SLA, customer and food dimensions, and review insights. Incremental fact models are used where appropriate so repeat builds can process new data without rebuilding the full history.

## AI Capabilities

- **Review enrichment:** `enrich_reviews.py` sends new review text to an OpenRouter model and stores sentiment, sentiment score, topic, and key issue fields in `ZOMATO.AI.REVIEW_ENRICHED`.
- **Retrieval-augmented generation:** `rag_chat.py` embeds up to 500 reviews, retrieves the five most similar reviews for a question, and generates an answer grounded in those reviews.
- **Text-to-SQL:** `text_to_sql.py` turns an English question into a Snowflake query over the documented marts, displays the generated SQL, and runs it through a read-only validation check.

## Prerequisites

Install or have available:

- Python 3.10+
- Docker Desktop with Docker Compose
- A Snowflake account with the required database, schemas, warehouse, and role
- An OpenRouter API key
- dbt with the Snowflake adapter if running dbt outside Docker

The Python applications use these packages:

```powershell
pip install streamlit numpy pandas pyarrow snowflake-connector-python openai python-dotenv
```

## Configuration

Keep credentials in local `.env` files and never commit them.

### `ai/.env`

```dotenv
SNOWFLAKE_ACCOUNT=<account>
SNOWFLAKE_USER=<user>
SNOWFLAKE_PASSWORD=<password>
SNOWFLAKE_WAREHOUSE=ZOMATO_WH
SNOWFLAKE_DATABASE=ZOMATO
SNOWFLAKE_SCHEMA=AI
OPENROUTER_API_KEY=<openrouter-key>
```

### `airflow/.env`

Airflow Compose reads the Snowflake credentials and AI key from `airflow/.env`. Define the same Snowflake values and the key expected by the Airflow environment in that file before starting the services.

The dbt profile is in `zomato/profiles.yml`. For local development, verify the account, user, password, warehouse, database, role, and target schema before running dbt.

## Run the Streamlit Apps

Run commands from the repository root:

### Review assistant

```powershell
python -m streamlit run ai/rag_chat.py
```

This app uses up to 500 reviews, creates embeddings, and sends the five most similar reviews as context for each answer. It uses `ai/review_embeddings.parquet` when that cache is available.

### Text-to-SQL assistant

```powershell
python -m streamlit run ai/text_to_sql.py
```

The app asks an OpenRouter model to generate a read-only Snowflake SQL query, displays the SQL, executes it, and presents the result as a table. Review generated SQL before using it in a production environment.

## Run Airflow with Docker

The Compose file is inside the `airflow` directory. From the repository root, run:

```powershell
docker compose -f airflow/docker-compose.yaml config --quiet
docker compose -f airflow/docker-compose.yaml up --build -d
```

Or change into the directory first:

```powershell
cd airflow
docker compose up --build -d
```

Open the Airflow UI at <http://localhost:8080>.

The local Compose configuration creates an Airflow admin user with:

```text
Username: admin
Password: admin
```

Change the password before using this setup beyond local development. Useful commands:

```powershell
docker compose ps
docker compose logs -f apiserver
docker compose logs -f scheduler
docker compose down
```

## Run dbt Locally

From the `zomato` directory, verify the Snowflake profile and run:

```powershell
cd zomato
dbt debug --profiles-dir .
dbt build --profiles-dir .
```

To build only the analytics marts:

```powershell
dbt build --select marts --profiles-dir .
```

The project uses:

- `models/staging`: views in the `STAGING` schema
- `models/marts`: tables in the `MARTS` schema
- `snapshots`: snapshot models
- `tests`: dbt tests

## Airflow Pipeline

The `zomato_batch` DAG performs these steps:

1. Reloads raw Snowflake tables from the configured stage.
2. Builds core dbt models while excluding AI-tagged models.
3. Enriches new reviews with sentiment, topic, and key-issue labels.
4. Builds AI-tagged dbt models.

The DAG is scheduled daily and can also be triggered manually from the Airflow UI.

## Security Notes

- Do not commit `.env` files, API keys, Snowflake passwords, or generated data caches.
- Rotate any credential that has been exposed in a terminal, screenshot, repository, or chat.
- Replace the default Airflow `admin/admin` credentials for any shared environment.
- Use a Snowflake role with only the permissions required by the pipeline.
- Treat generated SQL as untrusted input and keep the read-only validation in place.

## Troubleshooting

### `no configuration file provided`

Run Compose from `airflow`, or provide the file explicitly:

```powershell
docker compose -f airflow/docker-compose.yaml up --build -d
```

### OpenRouter authentication error

The AI apps require an OpenRouter key and use the OpenRouter-compatible endpoint. Confirm that `OPENROUTER_API_KEY` is set in the relevant `.env` file and restart Streamlit after changing it.

### Snowflake connection errors

Check the account identifier, credentials, warehouse, database, schema, role, and network access. For dbt, run `dbt debug --profiles-dir .` from the `zomato` directory.
