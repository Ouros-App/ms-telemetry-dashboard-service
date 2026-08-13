# ms-telemetry-dashboard-service

Microserviço FastAPI que funciona como control plane para dashboards de telemetria publicados no Databricks. Ele mantém o catálogo lógico, troca credenciais OAuth no backend e entrega ao frontend somente um token temporário reduzido para o embedding oficial. Não renderiza gráficos, consulta dados brutos nem expõe o client secret.

## Arquitetura

```text
router -> DashboardService -> DatabricksDashboardProvider
                         -> DatabricksAuthClient -> Databricks OAuth/API
```

O catálogo fica em `data/dashboards.json`. `id` é público; `dashboard_id` é interno e nunca é aceito diretamente do consumidor.

## Configuração

Copie `.env.example` para `.env` e preencha:

| Variável | Obrigatória para `/ready` | Descrição |
| --- | --- | --- |
| `DATABRICKS_HOST` | sim | URL HTTPS do workspace |
| `DATABRICKS_CLIENT_ID` | sim | Application ID do service principal |
| `DATABRICKS_CLIENT_SECRET` | sim | Secret OAuth do service principal |
| `DATABRICKS_WORKSPACE_ID` | sim | ID do workspace usado pelo client frontend |
| `DATABRICKS_TOKEN_URL` | não | Sobrescreve `/oidc/v1/token` derivado do host |
| `DASHBOARD_CATALOG_PATH` | sim | Caminho do catálogo JSON |
| `HTTP_TIMEOUT_SECONDS` | não | Timeout das chamadas externas |
| `HTTP_MAX_RETRIES` | não | Tentativas adicionais para timeout, conexão, 429 e 5xx |
| `CORS_ORIGINS` | não | Lista JSON de origins permitidos |

O registro do catálogo de exemplo fica desabilitado enquanto usa `replace-with-databricks-dashboard-id`; substitua pelo ID de um dashboard publicado e habilite-o antes de chamar `/embed`.

## Endpoints

- `GET /health`: saúde do processo, sem chamada ao Databricks.
- `GET /ready`: valida configuração e disponibilidade do catálogo local.
- `GET /metrics`: métricas Prometheus.
- `GET /v1/dashboards`: lista dashboards habilitados.
- `GET /v1/dashboards/{dashboard_id}`: busca pelo ID lógico.
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
curl -X POST http://localhost:8000/v1/dashboards/api-latency/embed
```

O segundo comando exige credenciais Databricks válidas e um `dashboard_id` real no catálogo.

## Testes

```bash
pytest -q
```
