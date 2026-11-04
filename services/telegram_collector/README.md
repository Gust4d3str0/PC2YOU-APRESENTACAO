# Coletor Telegram do PC2YOU

Coletor MTProto (conta de usuário) e bot Bot API são processos separados. Nenhuma
rota das APIs nem tela do frontend foi alterada. Não há IA, scraping ou matching
com o catálogo. Alertas pessoais e notificações são responsabilidade do bot,
documentados no [guia do bot](../telegram_bot/README.md).

## Arquitetura inspecionada e integração

- `frontend/`: React 18 + Vite, Axios, React Router; portas 5173 e APIs 8001/8002/8003.
- `api-usuarios/`: FastAPI, autenticação JWT, usuários/favoritos no PostgreSQL,
  SQLAlchemy e migrações Alembic.
- `api-orcamentos/`: FastAPI, compatibilidade, desempenho e orçamentos no mesmo
  PostgreSQL; consulta o catálogo por HTTP, com timeout/retries.
- `api-catalogo/`: FastAPI e PyMongo, coleção `components`. A conexão usa
  `MONGO_URI` e `MONGO_DB` (padrão `orcapc_catalog`), com índices e injeção da coleção.
  Integração opcional com Mercado Livre e proxy de imagens já existentes.
- Docker Compose: MongoDB 7, PostgreSQL 15, três APIs e frontend, healthchecks,
  rede `orcapc-network`, volumes `mongo_data` e `postgres_data`.
- Configuração: `.env.example`, `.env` local, JWT, CORS e variáveis dos bancos;
  frontend usa variáveis `VITE_*`. Scripts de sincronização/imagens permanecem intactos.
- A raiz ativa chama-se `PC2YOU`. A cópia antiga aninhada foi retirada para a
  pasta irmã `PC2YOU-arquivo-2026-10-23`; veja `docs/ORGANIZACAO.md`.

Os novos processos reutilizam o servidor MongoDB, o banco e a rede atuais.
Usam uma conexão PyMongo própria, pois são processos independentes; importar
`api-catalogo/database.py` acoplaria os serviços à configuração/JWT e aos imports
locais daquela API. Não se conectam ao PostgreSQL nem alteram `components`.

Fluxo: whitelist → mensagem de grupo/canal → filtro → parser → upsert no MongoDB.
O evento e a importação usam o mesmo caminho, com nova checagem da whitelist.
Mensagens privadas, mensagens enviadas pela própria conta, eventos de serviço e
textos sem palavras-chave são descartados. Nenhum remetente/telefone é armazenado.

## Instalação local (PowerShell, Python 3.12)

Execute na raiz atual do projeto:

```powershell
python -m venv services/.venv
& services/.venv/Scripts/python.exe -m pip install -r services/requirements.txt
```

Para desenvolvimento/testes:

```powershell
& services/.venv/Scripts/python.exe -m pip install -r services/requirements-dev.txt
```

O ambiente é separado das APIs: a biblioteca do bot usa uma versão de HTTPX
diferente daquela fixada pelos testes atuais das APIs. Em Linux/macOS, use
`services/.venv/bin/python` no lugar de `services/.venv/Scripts/python.exe`.

## Configurar `.env`

Se o arquivo já existe, acrescente as variáveis abaixo sem sobrescrever seu conteúdo.
Em uma instalação nova, copie `.env.example` para `.env` e configure também os
segredos das APIs conforme o README principal.

```dotenv
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=
TELEGRAM_ALLOWED_CHATS=
TELEGRAM_HISTORY_LIMIT=100
TELEGRAM_SESSION_PATH=services/telegram_collector/data/pc2you
TELEGRAM_BOT_TOKEN=
```

- Obtenha API ID/hash em [Telegram API Development Tools](https://my.telegram.org/apps).
- Telefone deve incluir país e DDD. Código de login e senha 2FA são informados
  somente no terminal durante `auth`; não os coloque no `.env`.
- Crie o bot no [BotFather](https://t.me/BotFather) e coloque seu token em
  `TELEGRAM_BOT_TOKEN`. O bot não precisa das credenciais da conta coletora.
- Inicialmente deixe `TELEGRAM_ALLOWED_CHATS` vazio para listar as fontes. Coleta
  e importação recusam iniciar com whitelist vazia. Somente IDs negativos são aceitos.
- `TELEGRAM_HISTORY_LIMIT` controla quantas mensagens recentes são examinadas
  por fonte, incluindo as que serão descartadas pelo filtro.
- O caminho da sessão é relativo à raiz do projeto ou absoluto. Sem extensão,
  o Telethon acrescenta `.session`. A sessão equivale a acesso à conta: preserve-a
  em armazenamento privado. `.env`, sessões, journals e diretório de dados estão
  ignorados pelo Git e excluídos da nova imagem Docker.

Reutilize `MONGO_DB` do catálogo. Fora do Docker, o hostname `mongo-db` do exemplo
não resolve: configure o endereço publicado, sem mudar o Compose:

```powershell
$env:MONGO_URI = 'mongodb://localhost:27017'
```

Esta variável do processo tem prioridade sobre `.env`. O Compose continua usando
`mongodb://mongo-db:27017` internamente. MongoDB precisa estar disponível para
coletar; autenticar e listar chats não dependem dele.

## Autenticar pela primeira vez

```powershell
& services/.venv/Scripts/python.exe -m services.telegram_collector.collector auth
```

Digite o código recebido pelo Telegram e, se solicitado, sua senha de duas etapas.
Após a autenticação a sessão é reutilizada; `listen` e `import-history` nunca
solicitam login interativo. Se a sessão expirar, pare o coletor e execute `auth`
novamente. Use apenas uma instância do coletor por arquivo de sessão.

## Descobrir IDs e escolher fontes

```powershell
& services/.venv/Scripts/python.exe -m services.telegram_collector.collector list-chats
```

A saída contém `ID`, `TIPO` (grupo/canal) e `NOME`. Conversas privadas são omitidas.
A conta precisa participar das fontes. Escolha IDs exatamente como aparecem e
atualize o `.env`, por exemplo:

```dotenv
TELEGRAM_ALLOWED_CHATS=-1001234567890,-1009876543210
```

Reinicie coletor e bot após alterar a configuração. A lista de diálogos é usada
somente para descobrir fontes e resolver seus access hashes; o conteúdo de chats
fora da whitelist não é importado nem processado.

## Importar e ouvir mensagens

Importar até 100 mensagens por fonte e encerrar:

```powershell
& services/.venv/Scripts/python.exe -m services.telegram_collector.collector import-history --limit 100
```

Importar mensagens recentes e continuar ouvindo:

```powershell
& services/.venv/Scripts/python.exe -m services.telegram_collector.collector listen --import-history
```

Somente novas mensagens:

```powershell
& services/.venv/Scripts/python.exe -m services.telegram_collector.collector listen
```

`--limit N` sobrescreve o limite do `.env` tanto em `import-history` quanto em
`listen --import-history`. O handler de eventos é registrado antes da importação;
sobreposições são deduplicadas. IDs configurados que não estiverem acessíveis
impedem o início, com orientação para conferir `list-chats`.

## Iniciar o bot

Em outro terminal, com o mesmo ambiente MongoDB:

```powershell
& services/.venv/Scripts/python.exe -m services.telegram_bot.bot
```

Abra seu bot no Telegram e envie `/start` e `/status`.

- `/start`: apresenta o PC2YOU e o objetivo de acompanhar hardware.
- `/status`: informa disponibilidade do MongoDB, total de promoções, número de
  IDs configurados no bot e situação do coletor pelo último sinal recebido.
- Coletor emite sinal a cada 30 segundos em `telegram_service_status`. Após
  120 segundos sem sinal conectado, o bot indica offline/sem sinal recente.
  Durante uma indisponibilidade do MongoDB, as contagens são marcadas indisponíveis.
- O bot não persiste a conversa bruta. Ele salva as preferências de alertas e o ID
  numérico do usuário. `/start` e `/status` permanecem públicos; as operações
  pessoais usam `TELEGRAM_ALLOWED_USERS` e verificação de propriedade por ID.
- `/acompanhar` e `/alertas` estão ativos. O worker inicia no processo do bot,
  consulta o MongoDB e envia as notificações sem dependência direta do coletor.

## Docker Compose (opcional)

Os dois novos serviços usam o perfil `telegram`. O fluxo habitual de
`docker compose up --build` permanece com os serviços originais.

```powershell
docker compose --profile telegram config --quiet
docker compose --profile telegram build telegram-collector telegram-bot
docker compose up -d mongo-db
docker compose --profile telegram run --rm telegram-collector python -m services.telegram_collector.collector auth
docker compose --profile telegram run --rm telegram-collector python -m services.telegram_collector.collector list-chats
```

Configure os IDs no `.env` antes de continuar:

```powershell
docker compose --profile telegram up -d telegram-collector telegram-bot
docker compose --profile telegram logs -f telegram-collector telegram-bot
```

O comando padrão do coletor faz importação inicial e permanece ouvindo. Para
reautenticar ou executar uma importação manual, pare primeiro o processo que usa
a mesma sessão:

```powershell
docker compose --profile telegram stop telegram-collector
docker compose --profile telegram run --rm telegram-collector python -m services.telegram_collector.collector import-history --limit 100
docker compose --profile telegram up -d telegram-collector
```

Sessão persiste em `telegram_sessions:/data/telegram`, com usuário sem privilégios
no container. O bot não recebe esse volume nem credenciais MTProto. Sessões locais
e Docker são independentes: autentique no ambiente em que o coletor vai rodar.
Não execute duas instâncias compartilhando o volume de sessão. `docker compose
down -v` também apagaria sessão e bancos, exigindo autenticação novamente.

## Documentos e deduplicação

`telegram_promotions` contém:

- `telegram`: `chat_id`, `chat_name`, `chat_username`, `message_id`, `message_url`,
  `sent_at` (data original do Telegram).
- `raw_text`: texto original, sem modificações.
- `links`: URLs HTTP/HTTPS visíveis, de entidades do Telegram e de botões,
  sem duplicatas. Links curtos são preservados sem resolver redirects.
- `product`: `name`, `normalized_key`, `component_id` inicialmente `null`;
  `component_type` quando identificável por uma regra inequívoca.
- `offer`: `store`, `price`, `original_price`, `coupon`, `url`. Valores monetários
  usam `Decimal` no parser e BSON `Decimal128` no MongoDB, sem erro de ponto flutuante.
- `status`: `parsed` após o parser, mesmo com campos desconhecidos. Enum preparado
  para `pending`, `parsed`, `matched`, `verified`, `published`, `ignored`.
- `created_at`, `processed_at`: datas UTC. Datas BSON têm precisão de milissegundos.

Índice único `uq_telegram_chat_message` em `telegram.chat_id` +
`telegram.message_id`. Upsert com `$setOnInsert` evita duplicação e preserva
status/dados existentes em reimportações; colisões simultâneas são tratadas.
Reimportações agora unem os links encontrados e completam `offer.url` quando
estiver ausente ou inválida. Uma URL HTTP/HTTPS válida já salva é preservada,
assim como preço, texto, datas, status e estado das notificações. O total
“promoções novas salvas” continua contando apenas inserções, mesmo quando links
de mensagens existentes tenham sido completados.

### Links da oferta e reprocessamento

A seleção considera botões com URL, `MessageEntityTextUrl`, URLs explícitas e
`MessageEntityUrl`, nessa ordem entre destinos comparáveis. Links de produto
ganham de páginas iniciais/ajuda; redes sociais, canais Telegram e arquivos de
imagem ficam em `links`, mas não são escolhidos como destino de compra.
Sem candidato adequado, `offer.url=null`. Nenhum link é aberto pelo coletor.

O bot usa somente `offer.url` em **🛒 Abrir oferta**, inclusive em `/ofertas`.
O roteiro para reimportar mensagens, consultar o MongoDB e conferir o botão
real está em [Links reais de ofertas](../../docs/TELEGRAM_OFFER_LINKS.md).

`equivalent_offer_key()` calcula a chave de produto normalizado + preço + loja
+ cupom. O worker utiliza essa chave para suprimir ofertas equivalentes de fontes
distintas dentro da janela configurada. Mensagens originais continuam salvas.
`models.PriceAlert` é o contrato da coleção ativa `price_alerts`, com listas de
marcas/lojas permitidas e ignoradas; o bot gerencia esses documentos.

## Testes sem Telegram/MongoDB real

```powershell
& services/.venv/Scripts/python.exe -m pytest services/tests -q
```

Fixtures fictícias em `services/tests/fixtures/messages.json`; persistência usa
mongomock. Cobertura: filtro, preço atual/original, parcelamento, cupom, URLs,
lojas, campos ambíguos/vazios, whitelist e chats privados, importação repetida,
índice único, concorrência, sessão ausente, logs, `/start`, `/status` e falhas de banco.
O comando não carrega credenciais reais nem se conecta à rede. Execute as suítes
antigas separadamente nos ambientes de cada API, pois seus imports locais têm
nomes iguais (`main`, `config`, `services`) e versões de dependências distintas.

Verificação original da coleta: **88 testes passaram**, `pip check` sem conflitos e
CLI `--help` funcionando. O YAML do Compose foi verificado estruturalmente
(perfil opcional, dependência do MongoDB, ambiente e volume de sessão). Docker
não está instalado neste ambiente, portanto build/subida dos containers e
autenticação/coleta reais no Telegram não foram executados.

A etapa de alertas preservou esses testes e ampliou a suíte para **195 testes**.
Consulte no guia do bot os cenários de matching, autorização, falhas e reinícios.

A correção de links em 27/10/2026 acrescentou **58 testes**: a suíte Telegram
agora tem **253 testes passando**, incluindo botões reais da versão instalada
do Telethon, histórico, persistência concorrente e ausência de botão de compra
quando não há URL. As três suítes de API também foram preservadas: **376 testes
passando no projeto**, executadas em processos/ambientes separados.

## Limitações desta etapa

- Regex/palavras-chave podem admitir falsos positivos. Não há confirmação de
  produto, validade de cupom, estoque ou disponibilidade real da promoção.
- Preços ambíguos e mensagens com múltiplas ofertas ficam com campos `null`;
  parcelas/frete reconhecíveis são ignorados. Nome/modelo e vínculo com catálogo
  permanecem `null`; preços sem `R$` só são aceitos com vírgula e dois decimais.
- Links curtos não são resolvidos, e conteúdo de imagem/OCR, edições e
  mensagens apagadas não são processados. Link `t.me/c` exige acesso ao canal;
  grupos antigos sem username podem não ter link da mensagem.
- Reimportação complementa apenas links/URL de mensagens já armazenadas;
  não reexecuta notificações já concluídas nem substitui os demais dados.
  Não há fila durável ou
  checkpoint de histórico. Falhas ao salvar eventos são registradas sem conteúdo
  nem credenciais; execute `import-history --limit N` com janela suficiente após
  indisponibilidades. Limites/flood waits do Telegram também podem atrasar a coleta.
- O sinal do coletor indica conectividade recente e acesso ao MongoDB, sem garantir
  que cada fonte publicou mensagens. A contagem considera todos os status salvos.
- Credenciais válidas, autenticação interativa e acesso da conta aos canais são
  necessários para validar o fluxo real. Os testes automatizados não dependem deles.

## Arquivos da primeira etapa

Criados (todos relativos à raiz):

```text
services/__init__.py
services/requirements.txt
services/requirements-dev.txt
services/Dockerfile
services/.dockerignore
services/telegram_collector/__init__.py
services/telegram_collector/collector.py
services/telegram_collector/config.py
services/telegram_collector/filters.py
services/telegram_collector/parser.py
services/telegram_collector/models.py
services/telegram_collector/deduplication.py
services/telegram_collector/repository.py
services/telegram_collector/logging_setup.py
services/telegram_collector/README.md
services/telegram_bot/__init__.py
services/telegram_bot/bot.py
services/tests/conftest.py
services/tests/fixtures/messages.json
services/tests/test_parser.py
services/tests/test_repository.py
services/tests/test_collector.py
services/tests/test_bot.py
```

Alterados: `.env.example`, `.gitignore`, `docker-compose.yml`, `README.md`.
O `.env` existente não foi alterado. `services/.venv/` é um ambiente local gerado
para executar as verificações, ignorado pelo Git e pelo build Docker.

Referências: [sessões/autenticação Telethon](https://docs.telethon.dev/en/stable/basic/signing-in.html),
[eventos Telethon](https://docs.telethon.dev/en/stable/modules/events.html),
[python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/telegram.ext.applicationbuilder.html).
