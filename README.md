# ms-telemetry-dashboard-service

<!-- REPO-METADATA:START -->
<div align="center">

[![Repo Size](https://img.shields.io/github/repo-size/Ouros-App/ms-telemetry-dashboard-service?style=flat-square&label=REPO%20SIZE)](https://github.com/Ouros-App/ms-telemetry-dashboard-service)
[![Languages](https://img.shields.io/github/languages/count/Ouros-App/ms-telemetry-dashboard-service?style=flat-square&label=LANGUAGES)](https://github.com/Ouros-App/ms-telemetry-dashboard-service/languages)
[![Forks](https://img.shields.io/github/forks/Ouros-App/ms-telemetry-dashboard-service?style=flat-square&label=FORKS)](https://github.com/Ouros-App/ms-telemetry-dashboard-service/network/members)
[![Issues](https://img.shields.io/github/issues/Ouros-App/ms-telemetry-dashboard-service?style=flat-square&label=ISSUES)](https://github.com/Ouros-App/ms-telemetry-dashboard-service/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/Ouros-App/ms-telemetry-dashboard-service?style=flat-square&label=PULL%20REQUESTS)](https://github.com/Ouros-App/ms-telemetry-dashboard-service/pulls)

</div>
<!-- REPO-METADATA:END -->

Microserviço FastAPI que consulta dashboards de telemetria no Databricks e disponibiliza seus gráficos em dados, HTML com Chart.js ou imagens PNG.

## Status e escopo

O serviço possui:

- consulta de dashboards ativos visíveis para as credenciais Databricks configuradas;
- listagem de dashboards e gráficos;
- renderização de gráficos em PNG;
- retorno de uma página HTML individual com Chart.js;
- catálogo JSON local opcional para metadados;
- autenticação Bearer nas rotas de negócio;
- métricas Prometheus, logs JSON, cache de gráficos e tentativas de repetição para chamadas externas.

O arquivo `data/dashboards.json` existe no repositório e atualmente contém uma lista vazia. A fonte principal dos dashboards é o workspace Databricks.

## Principais componentes

```text
router
  -> DashboardService
      -> DatabricksDashboardProvider
          -> DatabricksHttpClient
          -> DatabricksAuthClient
```

- `app/main.py`: inicialização da aplicação, clientes Databricks, catálogo, middleware, CORS e métricas.
- `app/api/routes.py`: rotas de saúde, prontidão, métricas, dashboards e gráficos.
- `app/services/`: regras de consulta e cache dos dashboards e gráficos.
- `app/providers/`: integração com a API do Databricks.
- `app/clients/`: cliente HTTP e autenticação OAuth do Databricks.
- `app/repositories/catalog.py`: leitura do catálogo local.
- `tests/`: testes de API, autenticação, gráficos, configuração, logs, serviço, provider e rotas.

## Pré-requisitos

- Python 3.12 para execução local.
- Acesso a um workspace Databricks por service principal OAuth.
- Permissão do service principal para acessar o workspace, os dashboards e o SQL Warehouse usado por eles.
- Docker é opcional; o repositório inclui um `Dockerfile`.

## Instalação e configuração

Copie `.env.example` para `.env`. As variáveis disponíveis são:

| Variável | Uso |
| --- | --- |
| `APP_PORT` | Porta configurada no ambiente de execução; o valor de exemplo é `8000`. |
| `PROJECT_NAME` | Nome exibido pela aplicação. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` ou `CRITICAL`. |
| `API_BEARER_TOKEN` | Token usado nas rotas de negócio. |
| `DASHBOARD_CATALOG_PATH` | Caminho do catálogo JSON; o padrão é `data/dashboards.json`. |
| `DATABRICKS_HOST` | URL HTTPS do workspace Databricks. |
| `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` | Credenciais OAuth do service principal. |
| `DATABRICKS_TOKEN_URL` | URL OAuth opcional; por padrão é derivada do host. |
| `HTTP_TIMEOUT_SECONDS` / `HTTP_MAX_RETRIES` | Timeout e tentativas adicionais das chamadas externas. |
| `CHART_CACHE_TTL_SECONDS` | Tempo de vida do cache de gráficos. |
| `SQL_WAIT_TIMEOUT_SECONDS` | Limite de espera de consultas SQL. |
| `HTTP_RETRY_BACKOFF_SECONDS` | Intervalo de backoff entre tentativas. |
| `TOKEN_REFRESH_MARGIN_SECONDS` | Margem para renovar o token OAuth. |
| `CORS_ORIGINS` | Lista JSON de origens permitidas, por exemplo `["https://frontend.example.com"]`. |

`/ready` considera obrigatórios `API_BEARER_TOKEN`, `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` e `DATABRICKS_CLIENT_SECRET`, além de validar os parâmetros de configuração.

## Execução

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

A aplicação fica disponível por padrão em [http://localhost:8000](http://localhost:8000).

O Dockerfile também inicia `uvicorn app.main:app` e usa a porta `8000` por padrão.

## Uso da API

Rotas públicas:

- `GET /health`: saúde do processo, sem chamada ao Databricks.
- `GET /ready`: verifica a configuração necessária para acessar o Databricks.
- `GET /metrics`: métricas Prometheus.
- `GET /docs`: documentação gerada pelo FastAPI.

Rotas de negócio, protegidas por Bearer:

- `GET /v1/dashboards`: lista dashboards ativos.
- `GET /v1/dashboards/{id}`: busca um dashboard.
- `GET /v1/dashboards/{id}/charts`: lista os gráficos do dashboard.
- `GET /v1/dashboards/{id}/charts/{chart_id}/png`: retorna PNG.
- `GET /v1/dashboards/{id}/charts/{chart_id}/chartjs`: retorna HTML com Chart.js.

Use um `id` retornado por `/v1/dashboards` nas chamadas seguintes:

```bash
curl -H "Authorization: Bearer $API_BEARER_TOKEN" \
  http://localhost:8000/v1/dashboards

curl -H "Authorization: Bearer $API_BEARER_TOKEN" \
  http://localhost:8000/v1/dashboards/PUBLIC_ID/charts

curl -H "Authorization: Bearer $API_BEARER_TOKEN" \
  http://localhost:8000/v1/dashboards/PUBLIC_ID/charts/CHART_ID/chartjs

curl -H "Authorization: Bearer $API_BEARER_TOKEN" \
  http://localhost:8000/v1/dashboards/PUBLIC_ID/charts/CHART_ID/png \
  --output chart.png
```

Os logs são emitidos em JSON e incluem evento, request ID, rota, status, duração e tentativas do Databricks, sem registrar tokens, secrets ou payloads de consultas.

## Testes e qualidade

```bash
pytest -q
ruff check .
pytest --cov=app --cov-report=xml:coverage.xml
python -m compileall .
```

O CI também executa SonarCloud e CodeQL.

## Licença

Este projeto está sob a licença MIT, conforme o arquivo [LICENSE](LICENSE).


## Principais contribuidores

<!-- CONTRIBUTORS:START -->
- [@Nicolas25vlad](https://github.com/Nicolas25vlad) — 3 contribuições
<!-- CONTRIBUTORS:END -->

> Atualizado automaticamente semanalmente pelo workflow de metadados do README.
