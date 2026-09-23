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

Microserviço FastAPI com dois fluxos independentes de dashboards: administração via Databricks e dashboards do app via PostgreSQL Analytics. O fluxo admin mantém dados/HTML Chart.js/PNG; o fluxo de usuário retorna HTML Plotly.js já filtrado pelo escopo assinado no JWT.

## Status e escopo

O serviço possui:

- consulta de dashboards administrativos ativos visíveis para as credenciais Databricks configuradas;
- dashboards de usuário derivados do PostgreSQL Analytics com isolamento por `farm_id` ou `enterprise_id` do JWT;
- listagem de dashboards e gráficos;
- renderização de gráficos administrativos em PNG;
- retorno de páginas HTML individuais com Chart.js no fluxo admin e Plotly.js no fluxo de usuário;
- catálogo JSON local opcional para metadados;
- autenticação JWT do Keycloak nas rotas de negócio, sem fallback de shared bearer;
- métricas Prometheus, logs JSON, cache de gráficos e tentativas de repetição para chamadas externas.

O arquivo `data/dashboards.json` existe no repositório e atualmente contém uma lista vazia. A fonte principal dos dashboards é o workspace Databricks.

## Principais componentes

```text
admin routes
  -> DashboardService
      -> DatabricksDashboardProvider
          -> DatabricksHttpClient
          -> DatabricksAuthClient

user routes
  -> UserDashboardService
      -> AnalyticsDashboardProvider
          -> AnalyticsRepository
              -> PostgreSQL Analytics (analytics_ro)
      -> Plotly renderer
```

- `app/main.py`: inicialização da aplicação, clientes Databricks, catálogo, middleware, CORS e métricas.
- `app/api/routes.py`: rotas de saúde, prontidão, métricas, dashboards e gráficos.
- `app/services/`: regras de consulta e cache dos dashboards e gráficos.
- `app/providers/`: providers independentes para Databricks e PostgreSQL Analytics.
- `app/repositories/analytics.py`: acesso read-only ao banco Analytics com queries parametrizadas.
- `app/services/plotly_renderer.py`: geração do HTML Plotly.js do fluxo de usuário.
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
| `INFISICAL_TOKEN` / `INFISICAL_PROJECT_ID` / `INFISICAL_ENV` / `INFISICAL_PATH` | Bootstrap opcional do Infisical. Configure as quatro juntas; `INFISICAL_ENV` aceita `prod` ou `dev`. |
| `INFISICAL_HOST` | Host do Infisical; padrão `https://app.infisical.com`. |
| `PROJECT_NAME` | Nome exibido pela aplicação. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` ou `CRITICAL`. |
| `KEYCLOAK_ISSUER_URL` / `KEYCLOAK_AUDIENCE` / `KEYCLOAK_JWKS_URL` | Contrato do resource server; valida assinatura RS256, issuer, audience e expiração. |
| `KEYCLOAK_REQUIRED_ROLE` | Realm role obrigatória nas rotas de dashboards; padrão `admin`. |
| `DASHBOARD_CATALOG_PATH` | Caminho do catálogo JSON; o padrão é `data/dashboards.json`. |
| `DATABRICKS_HOST` | URL HTTPS do workspace Databricks. |
| `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` | Credenciais OAuth do service principal. |
| `DATABRICKS_TOKEN_URL` | URL OAuth opcional; por padrão é derivada do host. |
| `ANALYTICS_DATABASE_URL` | DSN PostgreSQL do banco Analytics, usando o role read-only `analytics_ro`. |
| `ANALYTICS_POOL_MIN_SIZE` / `ANALYTICS_POOL_MAX_SIZE` | Limites do pool de conexões do fluxo de usuário. |
| `ANALYTICS_COMMAND_TIMEOUT_SECONDS` | Timeout das queries do Analytics. |
| `HTTP_TIMEOUT_SECONDS` / `HTTP_MAX_RETRIES` | Timeout e tentativas adicionais das chamadas externas. |
| `CHART_CACHE_TTL_SECONDS` | Tempo de vida do cache de gráficos. |
| `SQL_WAIT_TIMEOUT_SECONDS` | Limite de espera de consultas SQL. |
| `HTTP_RETRY_BACKOFF_SECONDS` | Intervalo de backoff entre tentativas. |
| `TOKEN_REFRESH_MARGIN_SECONDS` | Margem para renovar o token OAuth. |
| `CORS_ORIGINS` | Lista JSON de origens permitidas, por exemplo `["https://frontend.example.com"]`. |

`/ready` considera obrigatórios `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` e `DATABRICKS_CLIENT_SECRET`, além de validar os parâmetros de configuração. O JWT é validado por request contra o JWKS do Keycloak.

### Infisical

O serviço carrega os secrets do Infisical antes da criação de `Settings`. Para desenvolvimento local, deixe todas as variáveis de bootstrap vazias e use valores locais no `.env`. Em deploy, configure as quatro variáveis de bootstrap juntas; configuração parcial ou `INFISICAL_ENV` diferente de `prod`/`dev` interrompe o startup para evitar fallback silencioso.

Secrets de aplicação esperados no path `/ms-telemetry-dashboard-service`:

- `DATABRICKS_CLIENT_SECRET`;
- `ANALYTICS_DATABASE_URL`.

`DATABRICKS_CLIENT_ID` e `DATABRICKS_HOST` são configuração e podem permanecer no ambiente de deploy, embora o client ID também possa ser centralizado no Infisical se desejado. `ANALYTICS_DATABASE_URL` deve apontar para a rota privada/Tailnet do homelab e usar exclusivamente `analytics_ro`; não use o writer do sincronizador. `INFISICAL_TOKEN` é o único bootstrap secreto necessário fora do cofre; project ID, environment, path e host são configuração.

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

### Fluxo administrativo

As rotas administrativas continuam protegidas por access token do Keycloak com audience `ms-telemetry-dashboard-service` e realm role `admin`:

- `GET /v1/dashboards`: lista dashboards ativos.
- `GET /v1/dashboards/{id}`: busca um dashboard.
- `GET /v1/dashboards/{id}/charts`: lista os gráficos do dashboard.
- `GET /v1/dashboards/{id}/charts/{chart_id}/png`: retorna PNG.
- `GET /v1/dashboards/{id}/charts/{chart_id}/chartjs`: retorna HTML com Chart.js.

Use um `id` retornado por `/v1/dashboards` nas chamadas seguintes:

```bash
curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/dashboards

curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/dashboards/PUBLIC_ID/charts

curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/dashboards/PUBLIC_ID/charts/CHART_ID/chartjs

curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/dashboards/PUBLIC_ID/charts/CHART_ID/png \
  --output chart.png
```

### Fluxo de dashboards do usuário

O fluxo do app usa o mesmo access token validado, mas não exige role `admin`. São aceitos:

- `farm_owner`, obrigatoriamente com `database_id`, role `farm_owner` e claim assinado `farm_id`;
- `company_employee`, obrigatoriamente com `database_id`, role `company_employee` e claim assinado `enterprise_id`.

O cliente **não envia farm/enterprise ID** nas rotas. O serviço deriva o escopo somente dos claims assinados pelo Keycloak e injeta esse escopo como parâmetros PostgreSQL. Isso impede trocar IDs na request para consultar dados de outra fazenda ou empresa.

Rotas:

- `GET /v1/user/dashboards`;
- `GET /v1/user/dashboards/{dashboard_id}`;
- `GET /v1/user/dashboards/{dashboard_id}/charts`;
- `GET /v1/user/dashboards/{dashboard_id}/charts/{chart_id}/plotly`.

Exemplo:

```bash
curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/user/dashboards

curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/user/dashboards/overview/charts/current-flock/plotly
```

O último endpoint retorna `text/html` com Plotly.js e pode ser carregado pelo front. O HTML recebe CSP, `nosniff`, cache privado curto e serialização segura dos valores vindos do banco.

O pool PostgreSQL força transações read-only. Se o Analytics estiver indisponível, o fluxo admin continua funcionando e as rotas de usuário que precisam consultar dados retornam `503`.

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
