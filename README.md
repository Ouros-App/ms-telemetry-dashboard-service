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

Microserviço FastAPI com três responsabilidades desacopladas: telemetria operacional do Ouros, dashboards administrativos via Databricks e dashboards do app via PostgreSQL Analytics. A telemetria agrega sinais Prometheus do Midas e do Knowledge MCP, estima custo de tokens por tabela versionada e produz um baseline técnico para estudos futuros de escalabilidade.

## Status e escopo

O serviço possui:

- agregação on-demand de endpoints Prometheus configurados;
- uptime de processo, CPU, RAM, latência HTTP, falhas e concorrência por serviço;
- métricas do Midas para tempo ponta a ponta, chamadas LLM, tokens e round-trip do MCP;
- métricas internas do Knowledge MCP por tool;
- estimativa de custo de lista por token, sem confundir estimativa com fatura real;
- baseline para alimentar um simulador futuro de usuários, hardware, réplicas e custos;
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
Midas /metrics ---------┐
                       ├─> PrometheusScrapeClient -> TelemetryService
Knowledge MCP /metrics -┘              |                  |
                                      cost          capacity baseline

admin routes
  -> DashboardService
      -> DatabricksDashboardProvider

user routes
  -> UserDashboardService
      -> AnalyticsDashboardProvider
          -> AnalyticsRepository
              -> PostgreSQL Analytics (analytics_ro)
      -> Plotly renderer
```

- `app/main.py`: inicialização da aplicação, coletor Prometheus, Databricks, Analytics, middleware e CORS.
- `app/api/routes.py`: rotas de saúde, telemetria, baseline, dashboards e gráficos.
- `app/services/telemetry.py`: agregação dos sinais técnicos.
- `app/services/pricing.py`: catálogo e cálculo de custo estimado.
- `app/services/capacity.py`: normalização das métricas para estudos de escala.
- `data/model_pricing.json`: preços e modo de cobrança versionados por modelo.
- `app/services/`: regras de consulta e cache dos dashboards e gráficos.
- `app/providers/`: providers independentes para Databricks e PostgreSQL Analytics.
- `app/repositories/analytics.py`: acesso read-only ao banco Analytics com queries parametrizadas.
- `app/services/plotly_renderer.py`: geração do HTML Plotly.js do fluxo de usuário.
- `app/clients/`: cliente HTTP e autenticação OAuth do Databricks.
- `app/repositories/catalog.py`: leitura do catálogo local.
- `tests/`: testes de API, autenticação, gráficos, configuração, logs, serviço, provider e rotas.

## Pré-requisitos

- Python 3.12 para execução local e acesso aos endpoints Prometheus que você quiser agregar.
- Databricks é opcional e só é necessário para o fluxo administrativo de dashboards.
- PostgreSQL Analytics é opcional e só é necessário para dashboards de usuário.
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
| `METRICS_TOKEN` | Bearer dedicado ao scrape de `/metrics` deste serviço. |
| `TELEMETRY_TARGETS` | Lista JSON de endpoints Prometheus; cada target define `name`, `kind`, `url` e token opcional. |
| `TELEMETRY_SCRAPE_TIMEOUT_SECONDS` | Timeout individual de scrape; padrão `5`. |
| `MODEL_PRICING_PATH` | Catálogo versionado de preços; padrão `data/model_pricing.json`. |
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
| `ANALYTICS_SOCKS_HOST` / `ANALYTICS_SOCKS_PORT` | Proxy SOCKS5 opcional para alcançar um PostgreSQL em rede privada. |
| `ANALYTICS_SOCKS_CONNECT_TIMEOUT_SECONDS` | Timeout do handshake/conexão SOCKS5. |
| `HTTP_TIMEOUT_SECONDS` / `HTTP_MAX_RETRIES` | Timeout e tentativas adicionais das chamadas externas. |
| `CHART_CACHE_TTL_SECONDS` | Tempo de vida do cache de gráficos. |
| `SQL_WAIT_TIMEOUT_SECONDS` | Limite de espera de consultas SQL. |
| `HTTP_RETRY_BACKOFF_SECONDS` | Intervalo de backoff entre tentativas. |
| `TOKEN_REFRESH_MARGIN_SECONDS` | Margem para renovar o token OAuth. |
| `CORS_ORIGINS` | Lista JSON de origens permitidas, por exemplo `["https://frontend.example.com"]`. |

`/ready` valida o núcleo operacional e o contrato Keycloak. Databricks e PostgreSQL Analytics são integrações opcionais e têm readiness/falhas independentes; a telemetria continua funcional sem credenciais Databricks. O JWT é validado por request contra o JWKS do Keycloak.

### Infisical

O serviço carrega os secrets do Infisical antes da criação de `Settings`. Para desenvolvimento local, deixe todas as variáveis de bootstrap vazias e use valores locais no `.env`. Em deploy, configure as quatro variáveis de bootstrap juntas; configuração parcial ou `INFISICAL_ENV` diferente de `prod`/`dev` interrompe o startup para evitar fallback silencioso.

Secrets de aplicação esperados no path `/ms-telemetry-dashboard-service` podem incluir:

- `METRICS_TOKEN`;
- tokens dos targets definidos em `TELEMETRY_TARGETS`;
- `DATABRICKS_CLIENT_SECRET`, quando o fluxo admin estiver habilitado;
- `ANALYTICS_DATABASE_URL`, quando o fluxo de usuário estiver habilitado.

`DATABRICKS_CLIENT_ID` e `DATABRICKS_HOST` são configuração e podem permanecer no ambiente de deploy, embora o client ID também possa ser centralizado no Infisical se desejado. `ANALYTICS_DATABASE_URL` deve usar exclusivamente `analytics_ro` e apontar para o endereço privado do PostgreSQL em rede privada; não use o writer do sincronizador. Quando o banco Analytics só estiver acessível por uma rede privada, configure o proxy SOCKS5 pelas variáveis `ANALYTICS_SOCKS_HOST` e `ANALYTICS_SOCKS_PORT`. O serviço abre um relay apenas em `127.0.0.1` e deixa o proxy encaminhar o TCP até o destino, sem acoplar a aplicação a um provedor de deploy específico. `INFISICAL_TOKEN` é o único bootstrap secreto necessário fora do cofre; project ID, environment, path e host são configuração.

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

- `GET /health`: liveness do processo.
- `GET /ready`: readiness do núcleo operacional.
- `GET /docs`: documentação gerada pelo FastAPI.

`GET /metrics` usa o `METRICS_TOKEN` dedicado ao coletor, separado do JWT administrativo.

### Telemetria operacional

As rotas abaixo exigem o JWT administrativo do serviço:

- `GET /v1/telemetry/summary`: disponibilidade dos targets, uptime, CPU/RAM, HTTP, latências, LLM/tokens, MCP e custo estimado;
- `GET /v1/telemetry/capacity-baseline`: métricas normalizadas por chat e sinais de CPU/RAM/concorrência para um simulador posterior.

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

A camada visual evita a aparência padrão do Plotly e foi tratada como parte do próprio app, não como um mini-dashboard embutido. No desktop, os charts reproduzem a geometria do Figma com cards de até 419 × 484 px, borda `#CACACA`, raio de 15 px, títulos Poppins 22 px e espaçamento de 41 px entre cards de consumo. Em viewport mobile, a moldura desaparece, o conteúdo respeita o gutter de 25 px da tela de 402 px e os gráficos usam a tipografia/legenda compacta do layout Segundo, incluindo swatches de ~7,65 px e labels em ~14,35 px. As séries mensais são alinhadas por mês e, quando há histórico, são comparadas como **Este ano** em ouro `#D8A23A` e **Ano passado** em azul `#110B95`; meses sem leitura continuam `null`/gap em vez de virar zero. Barras usam largura estreita e cantos de 2 px, linhas usam spline discreta com pontos responsivos e os eixos mantêm grid horizontal sólido e rótulos reduzidos como no board. Gráficos de consumo com unidades incompatíveis, como m³ e kWh, continuam separados em cards irmãos no desktop e seções empilhadas no mobile.

Os presets visuais também foram derivados dos gráficos desenhados pelos designers: **KPI/indicator**, **donut de progresso**, **linha comparativa com pontos** e **barras agrupadas**. A definição do gráfico continua escolhendo um padrão coerente, mas o frontend pode selecionar outra visualização compatível com o mesmo conjunto de dados usando `render_as`:

```text
GET /v1/user/dashboards/consumption/charts/monthly-consumption/plotly?render_as=line
GET /v1/user/dashboards/consumption/charts/monthly-consumption/plotly?render_as=bar
GET /v1/user/dashboards/overview/charts/capacity-utilization/plotly?render_as=donut
GET /v1/user/dashboards/overview/charts/capacity-utilization/plotly?render_as=indicator
```

Valores disponíveis no contrato: `auto`, `indicator`, `donut`, `line` e `bar`. `auto` usa o preset padrão do gráfico. Nem toda combinação é semanticamente válida; por exemplo, `current-flock` só aceita `indicator`. O endpoint de listagem de charts informa `default_render_as` e `render_options`, então mobile e web não precisam manter uma tabela própria de compatibilidade.

Exemplo de item retornado por `GET /v1/user/dashboards/consumption/charts`:

```json
{
  "id": "monthly-consumption",
  "title": "Consumo mensal",
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

O pool PostgreSQL força transações read-only e valida `current_user = analytics_ro`. Quando `ANALYTICS_SOCKS_HOST` está configurado, cada conexão do `asyncpg` entra em um listener efêmero em `127.0.0.1`, que executa o handshake SOCKS5 e encaminha bytes ao host/porta definidos no próprio `ANALYTICS_DATABASE_URL`. O listener não é exposto externamente. Se o Analytics ou o proxy estiver indisponível, o fluxo admin continua funcionando e as rotas de usuário que precisam consultar dados retornam `503`. O connect usa timeout curto e backoff entre novas tentativas para evitar filas de reconexão durante uma queda. O pool é recriado de forma lazy após falhas, então uma indisponibilidade temporária da rede privada não exige restart do telemetry.

Os logs são emitidos em JSON e incluem evento, request ID, rota, status, duração e tentativas do Databricks, sem registrar tokens, secrets ou payloads de consultas.

## Custos e baseline de escalabilidade

O AI Server publica somente contadores técnicos. A conversão para dólares acontece aqui,
usando `data/model_pricing.json`, para que uma mudança de preço não exija redeploy do
Midas. `input_tokens` inclui tokens de cache; o cálculo separa
`input_tokens - cached_input_tokens` na tarifa normal e o subconjunto em cache na
tarifa específica, evitando dupla contagem.

Modelos com preço público por token entram em `estimated_token_cost_usd`. Modelos
sem preço público por token, inclusive ofertas cobradas por infraestrutura, permanecem em
`unpriced_tokens` em vez de receber um preço artificial. O valor é uma estimativa de
lista, nunca uma fatura real.

O endpoint de capacity baseline fornece chamadas LLM/chat, tokens/chat, chamadas MCP/chat,
latências, RSS, CPU média aproximada e concorrência atual. Ele deliberadamente não escolhe
hardware, número de réplicas ou margem de pico. Essas hipóteses ficam para um simulador
separado capaz de projetar cenários como 100, 1.000 ou 100.000 usuários.

Os contadores são acumulados desde o último restart de cada processo. Para disponibilidade
percentual, tendências históricas e capacity planning estatisticamente robusto, os mesmos
sinais devem ser armazenados em Prometheus/Grafana ou backend equivalente.

### Privacidade e cardinalidade

As métricas distribuídas usam apenas dimensões técnicas limitadas, como serviço, modelo,
perfil e nome de tool. IDs de usuário, fazenda, empresa, thread, request e conteúdo de
prompt não viram labels.


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
