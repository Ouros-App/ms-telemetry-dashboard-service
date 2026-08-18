# ms-telemetry-dashboard-service

Microserviço FastAPI para dashboards de telemetria publicados no Databricks. Ele lista dashboards e gráficos e oferece dois formatos de visualização: PNG e Chart.js.

O serviço também lista os gráficos de cada dashboard e mantém a execução de consultas no SQL Warehouse para os endpoints legados de imagem.

## Arquitetura

```text
router -> DashboardService -> DatabricksDashboardProvider
                         -> DatabricksAuthClient -> Databricks OAuth/API
```

`GET /v1/dashboards` consulta diretamente os dashboards ativos visíveis para as credenciais configuradas no Databricks. O `id` retornado é o próprio `dashboard_id` do Databricks, portanto pode ser usado nos demais endpoints. O catálogo local é opcional e serve apenas para substituir título, descrição ou ID público de um dashboard específico.

## Configuração

Copie `.env.example` para `.env` e preencha:

| Variável | Obrigatória para `/ready` | Descrição |
| --- | --- | --- |
| `API_BEARER_TOKEN` | sim | Token usado no header `Authorization: Bearer ...` |
| `LOG_LEVEL` | não | Nível de log: `DEBUG`, `INFO`, `WARNING`, `ERROR` ou `CRITICAL` |
| `DASHBOARD_CATALOG_PATH` | não | Catálogo JSON opcional para metadados e aliases públicos |
| `DATABRICKS_HOST` | sim | URL HTTPS do workspace |
| `DATABRICKS_CLIENT_ID` | sim | Application ID do service principal |
| `DATABRICKS_CLIENT_SECRET` | sim | Secret OAuth do service principal |
| `DATABRICKS_TOKEN_URL` | não | Sobrescreve `/oidc/v1/token` derivado do host |
| `HTTP_TIMEOUT_SECONDS` | não | Timeout das chamadas externas |
| `HTTP_MAX_RETRIES` | não | Tentativas adicionais para timeout, conexão, 429 e 5xx |
| `CORS_ORIGINS` | não | Lista JSON de origins permitidos |

O catálogo local não é obrigatório para listar dashboards. Se usado, ele pode conter metadados para dashboards específicos; entradas com `enabled: false` não removem dashboards da API. O Service Principal precisa acessar o workspace, os dashboards e o SQL Warehouse usado por eles.

Os endpoints de negócio exigem `Authorization: Bearer $API_BEARER_TOKEN`. `/health`, `/ready` e `/docs` permanecem públicos para monitoramento e documentação.

## Endpoints

- `GET /health`: saúde do processo, sem chamada ao Databricks.
- `GET /ready`: valida a configuração necessária para acessar o Databricks.
- `GET /metrics`: métricas Prometheus.
- `GET /v1/dashboards`: lista todos os dashboards ativos visíveis para o token do Databricks.
- `GET /v1/dashboards/{id}`: busca pelo ID público retornado na listagem.
- `GET /v1/dashboards/{id}/charts`: lista os gráficos do dashboard.
- `GET /v1/dashboards/{id}/charts/{chart_id}/png`: renderiza um gráfico como imagem PNG.
- `GET /v1/dashboards/{id}/charts/{chart_id}/chartjs`: retorna HTML pronto para usar como `src` de um iframe individual, renderizado com Chart.js.

## Execução

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
curl http://localhost:8000/v1/dashboards
curl http://localhost:8000/v1/dashboards/PUBLIC_ID/charts
curl http://localhost:8000/v1/dashboards/PUBLIC_ID/charts/CHART_ID/chartjs
curl http://localhost:8000/v1/dashboards/PUBLIC_ID/charts/CHART_ID/png --output chart.png
```

Exemplo de header:

```bash
curl -H "Authorization: Bearer $API_BEARER_TOKEN" http://localhost:8000/v1/dashboards
```

O segundo comando usa um `id` público retornado pelo primeiro e exige credenciais Databricks válidas.

Para depuração, defina `LOG_LEVEL=DEBUG`. Os logs são emitidos em JSON no stdout e incluem evento, request ID, rota, status, duração e tentativas do Databricks, sem registrar tokens, secrets ou payloads de consultas.

## Testes

```bash
pytest -q
```
