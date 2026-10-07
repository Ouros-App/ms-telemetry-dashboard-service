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

Microserviço FastAPI com dashboards operacionais de negócio servidos pelo PostgreSQL Analytics e dashboards técnicos via Prometheus. Databricks continua disponível como provider administrativo opcional para dashboards legados e análises, mas não é dependência dos dashboards de negócio. O fluxo admin mantém HTML Chart.js/PNG; o fluxo de usuário retorna HTML Plotly.js filtrado pelo escopo assinado no JWT.

## Status e escopo

O serviço possui:

- consulta de dashboards administrativos via registry de providers, com Databricks e Prometheus;
- dashboards de observabilidade do Prometheus para saúde dos targets, tráfego, latência, Midas AI e dependências do telemetry;
- dashboards de negócio derivados de views do PostgreSQL Analytics com isolamento por `farm_id` ou `enterprise_id` do JWT;
- listagem de dashboards e gráficos;
- renderização de gráficos administrativos em PNG;
- retorno de páginas HTML individuais com Chart.js no fluxo admin e Plotly.js no fluxo de usuário;
- catálogo JSON local opcional para metadados;
- autenticação JWT do Keycloak nas rotas de negócio, sem fallback de shared bearer;
- métricas Prometheus, logs JSON, cache de gráficos e tentativas de repetição para chamadas externas.

O arquivo `data/dashboards.json` existe no repositório e atualmente contém uma lista vazia. O fluxo de dashboards de negócio usa PostgreSQL Analytics; Databricks e Prometheus são providers administrativos independentes.

## Principais componentes

```text
admin routes
  -> DashboardService
      -> DashboardProviderRegistry
          -> DatabricksDashboardProvider (opcional)
              -> DatabricksHttpClient / DatabricksAuthClient
          -> PrometheusDashboardProvider
              -> PrometheusHttpClient
              -> SOCKS5 relay
                  -> tailscale-proxy:1055
                      -> Prometheus no homelab

user routes
  -> UserDashboardService
      -> AnalyticsDashboardProvider
          -> AnalyticsRepository
              -> PostgreSQL Analytics (views dashboard_*, analytics_ro)
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
| `PROMETHEUS_URL` | URL privada do Prometheus; no homelab atual, `http://192.168.15.11:9090`. |
| `PROMETHEUS_SOCKS_HOST` / `PROMETHEUS_SOCKS_PORT` | Proxy SOCKS5 usado pela Discloud para alcançar a rede do homelab; normalmente `tailscale-proxy:1055`. |
| `PROMETHEUS_SOCKS_CONNECT_TIMEOUT_SECONDS` | Timeout da conexão TCP até o proxy SOCKS5. |
| `PROMETHEUS_RANGE_SECONDS` / `PROMETHEUS_STEP_SECONDS` | Janela e resolução dos gráficos temporais Prometheus. |
| `ANALYTICS_DATABASE_URL` | DSN PostgreSQL do banco Analytics, usando o role read-only `analytics_ro`. |
| `ANALYTICS_EXPECTED_ROLE` | Role PostgreSQL exigido pelo serviço; padrão `analytics_ro`. A conexão é recusada se `current_user` for diferente. |
| `ANALYTICS_POOL_MIN_SIZE` / `ANALYTICS_POOL_MAX_SIZE` | Limites do pool de conexões do fluxo de usuário. |
| `ANALYTICS_COMMAND_TIMEOUT_SECONDS` | Timeout das queries do Analytics. |
| `ANALYTICS_CONNECT_TIMEOUT_SECONDS` | Timeout curto para abrir uma conexão PostgreSQL; padrão `5`. |
| `ANALYTICS_RETRY_BACKOFF_SECONDS` | Janela de backoff após falha de conexão para evitar tempestade de reconexões; padrão `5`. |
| `ANALYTICS_STALE_AFTER_SECONDS` | Limite para classificar os dados como desatualizados; padrão `900` (15 min). |
| `HTTP_TIMEOUT_SECONDS` / `HTTP_MAX_RETRIES` | Timeout e tentativas adicionais das chamadas externas. |
| `CHART_CACHE_TTL_SECONDS` | Tempo de vida do cache de gráficos. |
| `SQL_WAIT_TIMEOUT_SECONDS` | Limite de espera de consultas SQL. |
| `HTTP_RETRY_BACKOFF_SECONDS` | Intervalo de backoff entre tentativas. |
| `TOKEN_REFRESH_MARGIN_SECONDS` | Margem para renovar o token OAuth. |
| `CORS_ORIGINS` | Lista JSON de origens permitidas, por exemplo `["https://frontend.example.com"]`. |

`/ready` valida a configuração do serviço e do Keycloak sem depender das credenciais ou disponibilidade do Databricks. O provider Databricks só é registrado quando host, client ID e secret estão configurados; uma configuração parcial o desativa sem impedir os fluxos Analytics e Prometheus. O JWT é validado por request contra o JWKS do Keycloak.

### Infisical

O serviço carrega os secrets do Infisical antes da criação de `Settings`. Para desenvolvimento local, deixe todas as variáveis de bootstrap vazias e use valores locais no `.env`. Em deploy, configure as quatro variáveis de bootstrap juntas; configuração parcial ou `INFISICAL_ENV` diferente de `prod`/`dev` interrompe o startup para evitar fallback silencioso.

Secrets de aplicação esperados no path `/ms-telemetry-dashboard-service`:

- `ANALYTICS_DATABASE_URL`.

`DATABRICKS_CLIENT_SECRET` só é necessário quando o provider Databricks legado está habilitado. `DATABRICKS_CLIENT_ID` e `DATABRICKS_HOST` são configuração opcional do provider e podem permanecer no ambiente de deploy. `ANALYTICS_DATABASE_URL` deve usar exclusivamente `analytics_ro` e apontar para o endereço privado do PostgreSQL no homelab; não use o writer do sincronizador. Em Discloud, configure `ANALYTICS_SOCKS_HOST=tailscale-proxy` e `ANALYTICS_SOCKS_PORT=1055`: o serviço abre um relay apenas em `127.0.0.1`, alcança o proxy pela VLAN da Discloud e deixa o proxy encaminhar o TCP até a subnet do homelab. O telemetry não precisa participar diretamente da Tailnet. `INFISICAL_TOKEN` é o único bootstrap secreto necessário fora do cofre; project ID, environment, path e host são configuração.

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
- `GET /ready`: verifica a configuração do serviço e do Keycloak; não depende do Databricks.
- `GET /metrics`: métricas Prometheus.
- `GET /docs`: documentação gerada pelo FastAPI.

### Fluxo administrativo

O fluxo administrativo agrega dashboards de todos os providers registrados. Os dashboards retornados incluem o campo `provider`: `analytics`, `prometheus` ou `databricks` quando o provider legado está habilitado. O provider Analytics publica `analytics-overview` com fazendas monitoradas, aves atuais, uso da capacidade e histórico mensal de água, por meio das mesmas views usadas pelo fluxo de usuário. O provider Prometheus consulta a HTTP API privada do homelab; na Discloud, a conexão TCP passa pelo `tailscale-proxy:1055` usando o mesmo relay local já empregado pelo PostgreSQL Analytics.

As rotas administrativas continuam protegidas por access token do Keycloak com audience `ms-telemetry-dashboard-service` e realm role `admin`:

- `GET /v1/dashboards`: lista dashboards ativos.
- `GET /v1/dashboards/{id}`: busca um dashboard.
- `GET /v1/dashboards/{id}/charts`: lista os gráficos do dashboard.
- `GET /v1/dashboards/{id}/charts/{chart_id}/png`: retorna PNG.
- `GET /v1/dashboards/{id}/charts/{chart_id}/chartjs`: retorna HTML com Chart.js.

Para testar o provider Analytics pelo fluxo de ADM, use um access token com role `admin`:

```bash
curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/dashboards/analytics-overview/charts

curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/dashboards/analytics-overview/charts/current-flock/chartjs
```

Se o Analytics estiver indisponível, os endpoints de charts desse provider retornam `503`; não há fallback silencioso para Databricks.

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
- `GET /v1/user/dashboards/status` informa `fresh`, `stale` ou `unknown`, o sync bem-sucedido mais antigo entre datasets e sua idade. Falha do Analytics retorna `503`; não há fallback para Databricks.
- `GET /v1/user/dashboards/{dashboard_id}`;
- `GET /v1/user/dashboards/{dashboard_id}/charts`;
- `GET /v1/user/dashboards/{dashboard_id}/charts/{chart_id}/plotly`.
- `POST /v1/user/dashboards/custom` compõe um painel temporário com até quatro gráficos do catálogo permitido e retorna HTML Plotly por gráfico.

Exemplo:

```bash
curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/user/dashboards

curl -H "Authorization: Bearer $KEYCLOAK_ACCESS_TOKEN" \
  http://localhost:8000/v1/user/dashboards/overview/charts/current-flock/plotly
```

O último endpoint retorna `text/html` com Plotly.js e pode ser carregado pelo front. O HTML recebe CSP, `nosniff`, cache privado curto e serialização segura dos valores vindos do banco.

O endpoint de painel customizado recebe `title`, uma lista de `chart_id`/`render_as` e `period_days` (1 a 366, padrão 30). O catálogo expõe os tipos de trace Plotly compatíveis com os dados de cada gráfico: barras, linhas, áreas, dispersão, histogramas, box/violin, waterfall/funnel, heatmap/contour, pizza/donut e indicadores. Consumo de água e energia tem opções separadas e também um gráfico combinado para pedidos que mencionem ambos. Para períodos curtos, `water-consumption-by-reading` apresenta somente água usando as datas reais das leituras do hidrômetro; `monthly-water-consumption` continua disponível para análises mensais. O endpoint de listagem informa as opções válidas por gráfico; não há uma lista própria de estilos no cliente. O endpoint nunca aceita SQL, `farm_id`, `enterprise_id` ou configuração Plotly arbitrária; o escopo vem do mesmo JWT Keycloak validado nas rotas de usuário. O resultado é `Cache-Control: private, no-store` e não persiste a configuração do painel.

```http
POST /v1/user/dashboards/custom
Authorization: Bearer <JWT do usuário com audience ms-telemetry-dashboard-service>
Content-Type: application/json

{"title":"Consumo de água da minha fazenda","period_days":30,"charts":[{"chart_id":"water-consumption-by-reading","render_as":"auto"}]}
```

A resposta contém `title` e `charts`; cada item traz `id`, `title`, `render_as` e o HTML Plotly independente para WebView/iframe.

#### Integração visual mobile/web

Os gráficos de usuário seguem os tokens do board **2️⃣ | Segundo** do Figma: Poppins, fundo `#F2F5F7`, texto `#010B13`, ouro `#D8A23A`, azul `#110B95`, bordas suaves e cards de raio 15 px. O renderer é responsivo, remove a modebar do Plotly, possui estado vazio próprio e envia a altura renderizada para hosts embutidos.

A camada visual evita a aparência padrão do Plotly e foi tratada como parte do próprio app, não como um mini-dashboard embutido. No desktop, os charts reproduzem a geometria do Figma com cards de até 419 × 484 px, borda `#CACACA`, raio de 15 px, títulos Poppins 22 px e espaçamento de 41 px entre cards de consumo. Em viewport mobile, a moldura desaparece, o conteúdo respeita o gutter de 25 px da tela de 402 px e os gráficos usam a tipografia/legenda compacta do layout Segundo, incluindo swatches de ~7,65 px e labels em ~14,35 px. As séries mensais são alinhadas por mês e, quando há histórico, são comparadas como **Este ano** em ouro `#D8A23A` e **Ano passado** em azul `#110B95`; meses sem leitura continuam `null`/gap em vez de virar zero. Barras usam largura estreita e cantos de 2 px, linhas usam spline discreta com pontos responsivos e os eixos mantêm grid horizontal sólido e rótulos reduzidos como no board. Gráficos de consumo com unidades incompatíveis, como m³ e kWh, continuam separados em cards irmãos no desktop e seções empilhadas no mobile.

Os presets visuais também foram derivados dos gráficos desenhados pelos designers: **KPI/indicator**, **donut de progresso**, **linha comparativa com pontos** e **barras agrupadas**. A definição do gráfico continua escolhendo um padrão coerente, mas o frontend pode selecionar outra visualização compatível com o mesmo conjunto de dados usando `render_as`:

```text
GET /v1/user/dashboards/consumption/charts/monthly-water-consumption/plotly?render_as=line
GET /v1/user/dashboards/consumption/charts/monthly-energy-consumption/plotly?render_as=bar
GET /v1/user/dashboards/overview/charts/capacity-utilization/plotly?render_as=donut
GET /v1/user/dashboards/overview/charts/capacity-utilization/plotly?render_as=indicator
```

`render_as` recebe o nome do trace Plotly publicado em `render_options` para aquele gráfico; `auto` usa o preset padrão. O campo aceita novos nomes sem atualizar os clientes, enquanto o catálogo da API publica apenas traces que o renderer sabe mapear para os dados daquele gráfico. Nem toda combinação é semanticamente válida: heatmap/contour exigem várias séries e traces 3D exigem dimensões suficientes. O endpoint de listagem informa `default_render_as` e `render_options`, então mobile e web não precisam manter uma tabela própria de compatibilidade.

Exemplo de item retornado por `GET /v1/user/dashboards/consumption/charts`:

```json
{
  "id": "water-consumption-by-reading",
  "title": "Consumo de água por leitura",
  "type": "bar",
  "default_render_as": "bar",
  "render_options": ["bar", "line"]
}
```

Para Android/iOS, carregue a rota `/plotly` em um WebView enviando o mesmo Bearer JWT no request inicial. Quando o gráfico terminar de renderizar, o HTML envia para `ReactNativeWebView.postMessage`:

```json
{"type":"ouros-chart-resize","chartId":"lot-throughput","height":320}
```

No React web, prefira buscar o HTML autenticado e colocá-lo em um `iframe srcDoc`. Isso evita expor token na URL e mantém o CSS/Plotly isolados do restante da aplicação. O HTML carrega sua própria CSP por meta tag para que a proteção continue ativa dentro de `srcDoc`.

```tsx
const iframeRef = useRef<HTMLIFrameElement>(null);
const [chartHeight, setChartHeight] = useState(360);

useEffect(() => {
  const onMessage = (event: MessageEvent) => {
    if (event.source !== iframeRef.current?.contentWindow) return;

    const message = event.data;
    if (
      !message ||
      message.type !== "ouros-chart-resize" ||
      message.chartId !== "lot-throughput" ||
      !Number.isFinite(message.height)
    ) {
      return;
    }

    setChartHeight(Math.max(240, Math.min(message.height, 800)));
  };

  window.addEventListener("message", onMessage);
  return () => window.removeEventListener("message", onMessage);
}, []);

const response = await fetch(
  `${API}/v1/user/dashboards/production/charts/lot-throughput/plotly?render_as=bar`,
  { headers: { Authorization: `Bearer ${accessToken}` } },
);

const html = await response.text();

return (
  <iframe
    ref={iframeRef}
    title="Movimentação dos lotes"
    srcDoc={html}
    sandbox="allow-scripts"
    style={{ width: "100%", height: chartHeight, border: 0 }}
  />
);
```

O listener valida a janela emissora, o tipo do evento, o `chartId` e a altura antes de redimensionar o iframe. Configure `CORS_ORIGINS` para a origem real do frontend que fará o `fetch`.

O pool PostgreSQL força transações read-only e valida `current_user = analytics_ro`. As queries dos dashboards leem somente views `dashboard_*`, nunca tabelas `dim_*`/`fact_*` diretamente. A migration versionada [`001_dashboard_read_models.sql`](migrations/analytics/001_dashboard_read_models.sql) cria views de fazendas, resumo financeiro de lotes, consumo, leituras de água, metas e status do sync, além de ampliar `sync_state` com metadados de execução. A migration deve ser aplicada pelo processo de deploy do Analytics antes de habilitar esta versão do serviço.

O sync writer permanece fora deste repositório: deve continuar executando fora do banco transacional, em timer systemd, com upserts idempotentes, retries e escrita atômica no Analytics. O writer atualiza `sync_state` por dataset, mantendo `last_success_at` somente para execuções completas e gravando tentativa, cursor, quantidade, duração, status e erro. O serviço não dispara sync nem tem credenciais de escrita; ausência de estado retorna `unknown`, atraso acima de `ANALYTICS_STALE_AFTER_SECONDS` ou falha mais recente retorna `stale`. Quando `ANALYTICS_SOCKS_HOST` está configurado, cada conexão do `asyncpg` usa listener efêmero em `127.0.0.1` e o proxy encaminha bytes ao host definido em `ANALYTICS_DATABASE_URL`. Se o Analytics ou proxy estiver indisponível, Prometheus continua funcionando e as rotas de usuário que consultam dados retornam `503`. O pool usa timeout curto e backoff e é recriado de forma lazy após falhas.

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
