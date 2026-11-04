# Scripts de manutenção

Execute a partir da raiz `PC2YOU`. As APIs precisam estar disponíveis para
sincronizações. Estes scripts não são executados automaticamente pelo Docker.

| Script | Finalidade |
|---|---|
| `sync_ml_prices.py` | Sincronização de preços pelo endpoint existente do catálogo |
| `sync_real_prices_images.py` | Atualização de preços/imagens e relatório de candidatos |
| `sync_safe_real_prices_images.py` | Atualização com filtros e modo de simulação |
| `download_images.py` | Download auxiliar de imagens para `frontend/public/images` |
| `diagnostics/check_catalog_ids.py` | Conferência local dos IDs presentes em `api-catalogo/seed.py` |
| `telegram_demo.py` | Simulação offline de matching/notificação; `--enqueue` insere uma promoção fictícia no MongoDB |

Exemplos:

```powershell
python scripts/sync_real_prices_images.py --help
python scripts/sync_safe_real_prices_images.py --help
python scripts/sync_safe_real_prices_images.py --dry-run
python scripts/diagnostics/check_catalog_ids.py
```

A simulação Telegram usa o ambiente já instalado em `services/.venv`:

```powershell
& services/.venv/Scripts/python.exe scripts/telegram_demo.py
```

Sem flags não acessa rede nem banco. `--enqueue` grava no MongoDB e permite ao
worker enviar uma notificação real para alertas correspondentes; consulte o
[guia do bot](../services/telegram_bot/README.md).

Os relatórios de sincronização são gravados em `reports/`, na raiz, mesmo quando
o script é chamado de outra pasta. O destino das imagens também usa a raiz do projeto.
As chamadas HTTP e regras de sincronização foram preservadas; endpoints protegidos
continuam sujeitos à autenticação atual das APIs.

Dependências auxiliares dos scripts existentes, em ambiente de manutenção separado:

```powershell
python -m pip install requests Pillow duckduckgo_search
```

## Auditoria do seed comercial

`audit_seed_commercial_data.py` — dry-run por padrão: conta preços e histórico sintéticos do seed em `components`.
Com `--apply`, arquiva (não apaga) essas entradas em `legacy_seed_commercial`. Veja `docs/REAL_PRICING_REFACTOR.md`.

## Mercado Livre (Product API)

- `enrich_mercado_livre_products.py` — enriquece componentes com imagens/specs oficiais (`--dry-run` padrão, `--apply`, `--suggest`).
- `check_mercado_livre_price_capability.py` — diagnóstico da API de itens/preço (não altera ofertas).

Veja `docs/MERCADO_LIVRE_INTEGRATION_V2.md`.
