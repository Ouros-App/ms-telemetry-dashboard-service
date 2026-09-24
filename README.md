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
| `ANALYTICS_EXPECTED_ROLE` | Role PostgreSQL exigido pelo serviço; padrão `analytics_ro`. A conexão é recusada se `current_user` for diferente. |
| `ANALYTICS_POOL_MIN_SIZE` / `ANALYTICS_POOL_MAX_SIZE` | Limites do pool de conexões do fluxo de usuário. |
| `ANALYTICS_COMMAND_TIMEOUT_SECONDS` | Timeout das queries do Analytics. |
| `ANALYTICS_CONNECT_TIMEOUT_SECONDS` | Timeout curto para abrir uma conexão PostgreSQL; padrão `5`. |
| `ANALYTICS_RETRY_BACKOFF_SECONDS` | Janela de backoff após falha de conexão para evitar tempestade de reconexões; padrão `5`. |
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

`DATABRICKS_CLIENT_ID` e `DATABRICKS_HOST` são configuração e podem permanecer no ambiente de deploy, embora o client ID também possa ser centralizado no Infisical se desejado. `ANALYTICS_DATABASE_URL` deve usar exclusivamente `analytics_ro` e apontar para o endereço privado do PostgreSQL no homelab; não use o writer do sincronizador. Em Discloud, configure `ANALYTICS_SOCKS_HOST=tailscale-proxy` e `ANALYTICS_SOCKS_PORT=1055`: o serviço abre um relay apenas em `127.0.0.1`, alcança o proxy pela VLAN da Discloud e deixa o proxy encaminhar o TCP até a subnet do homelab. O telemetry não precisa participar diretamente da Tailnet. `INFISICAL_TOKEN` é o único bootstrap secreto necessário fora do cofre; project ID, environment, path e host são configuração.

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

#### Integração visual mobile/web

Os gráficos de usuário seguem os tokens do board **2️⃣ | Segundo** do Figma: Poppins, fundo `#F2F5F7`, texto `#010B13`, ouro `#D8A23A`, azul `#110B95`, bordas suaves e cards de raio 15 px. O renderer é responsivo, remove a modebar do Plotly, possui estado vazio próprio e envia a altura renderizada para hosts embutidos.

Para Android/iOS, carregue a rota `/plotly` em um WebView enviando o mesmo Bearer JWT no request inicial. Quando o gráfico terminar de renderizar, o HTML envia para `ReactNativeWebView.postMessage`:

```json
{"type":"ouros-chart-resize","chartId":"lot-throughput","height":320}
```

No React web, prefira buscar o HTML autenticado e colocá-lo em um `iframe srcDoc`. Isso evita expor token na URL e mantém o CSS/Plotly isolados do restante da aplicação:

```tsx
const response = await fetch(
  `${API}/v1/user/dashboards/production/charts/lot-throughput/plotly`,
  { headers: { Authorization: `Bearer ${accessToken}` } },
);

const html = await response.text();

return (
  <iframe
    title="Movimentação dos lotes"
    srcDoc={html}
    sandbox="allow-scripts"
    style={{ width: "100%", height: 360, border: 0 }}
  />
);
```

O HTML também emite `window.parent.postMessage` com o mesmo evento de resize, permitindo que o React ajuste a altura do iframe sem conhecer detalhes internos do Plotly. Configure `CORS_ORIGINS` para a origem real do frontend que fará o `fetch`.

O pool PostgreSQL força transações read-only e valida `current_user = analytics_ro`. Quando `ANALYTICS_SOCKS_HOST` está configurado, cada conexão do `asyncpg` entra em um listener efêmero em `127.0.0.1`, que executa o handshake SOCKS5 e encaminha bytes ao host/porta definidos no próprio `ANALYTICS_DATABASE_URL`. O listener não é exposto externamente. Se o Analytics ou o proxy estiver indisponível, o fluxo admin continua funcionando e as rotas de usuário que precisam consultar dados retornam `503`. O connect usa timeout curto e backoff entre novas tentativas para evitar filas de reconexão durante uma queda. O pool é recriado de forma lazy após falhas, então um reboot do homelab não exige restart do telemetry.

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
