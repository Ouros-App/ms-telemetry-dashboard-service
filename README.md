# ms-telemetry-dashboard-service

Microserviço FastAPI para dashboards de telemetria publicados no Databricks. Ele lista dashboards e gráficos, consulta os dados no SQL Warehouse, gera PNGs com cache e entrega ao frontend somente tokens temporários reduzidos para embedding. Nunca expõe o client secret.

O serviço também lista os gráficos de cada dashboard, executa suas consultas no SQL Warehouse e retorna PNGs com cache configurável.

## Arquitetura

```text
router -> DashboardService -> DatabricksDashboardProvider
                         -> DatabricksAuthClient -> Databricks OAuth/API
```

`GET /v1/dashboards` consulta os dashboards ativos do Databricks. O frontend usa o `id` retornado para buscar detalhes ou gerar o embed.

## Configuração

Copie `.env.example` para `.env` e preencha:

| Variável | Obrigatória para `/ready` | Descrição |
| --- | --- | --- |
| `DATABRICKS_HOST` | sim | URL HTTPS do workspace |
| `DATABRICKS_CLIENT_ID` | sim | Application ID do service principal |
| `DATABRICKS_CLIENT_SECRET` | sim | Secret OAuth do service principal |
| `DATABRICKS_WORKSPACE_ID` | sim | ID do workspace usado pelo client frontend |
| `DATABRICKS_TOKEN_URL` | não | Sobrescreve `/oidc/v1/token` derivado do host |
| `HTTP_TIMEOUT_SECONDS` | não | Timeout das chamadas externas |
| `HTTP_MAX_RETRIES` | não | Tentativas adicionais para timeout, conexão, 429 e 5xx |
| `CORS_ORIGINS` | não | Lista JSON de origins permitidos |

O Service Principal precisa acessar o workspace, os dashboards e o SQL Warehouse usado por eles. Para embedding, o dashboard precisa estar publicado.

## Endpoints

- `GET /health`: saúde do processo, sem chamada ao Databricks.
- `GET /ready`: valida a configuração necessária para acessar o Databricks.
- `GET /metrics`: métricas Prometheus.
- `GET /v1/dashboards`: lista dashboards ativos do Databricks.
- `GET /v1/dashboards/{dashboard_id}`: busca pelo ID retornado na listagem.
- `GET /v1/dashboards/{dashboard_id}/charts`: lista os gráficos do dashboard.
- `GET /v1/dashboards/{dashboard_id}/charts/{chart_id}/png`: executa a consulta do gráfico e retorna PNG com cache.
- `POST /v1/dashboards/{dashboard_id}/embed`: gera a configuração temporária de embedding.

O corpo opcional de `/embed` aceita `external_viewer_id` e `external_value`. A implementação segue o embedding para usuários externos documentado pelo Databricks: token OAuth amplo para o backend, `published/tokeninfo` e uma segunda troca OAuth para o token reduzido entregue ao `@databricks/aibi-client`. O frontend deve inicializar `DatabricksDashboard` com `instance_url`, `workspace_id`, `dashboard_id` e `token`; nunca recebe `DATABRICKS_CLIENT_SECRET`.

## Execução

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
curl http://localhost:8000/v1/dashboards
curl http://localhost:8000/v1/dashboards/DASHBOARD_ID/charts
curl http://localhost:8000/v1/dashboards/DASHBOARD_ID/charts/CHART_ID/png --output chart.png
curl -X POST http://localhost:8000/v1/dashboards/DASHBOARD_ID/embed
```

O segundo comando usa um `dashboard_id` retornado pelo primeiro e exige credenciais Databricks válidas.

## Testes

```bash
pytest -q
```
