# Bot Telegram — PC2YOU

Interface pessoal para cadastrar peças, definir filtros e receber ofertas
coletadas. O [README principal](../../README.md) é o ponto de entrada do projeto.
A autenticação da conta coletora continua no [guia do coletor](../telegram_collector/README.md).

## Estrutura e fluxo

```text
Telethon → telegram_promotions no MongoDB
                         ↓
            worker no processo do bot
                         ↓
           matcher determinístico + price_alerts
                         ↓
           notification_history + Bot API
```

O coletor não importa módulos do bot nem envia notificações. O worker usa polling
controlado, sem fila externa ou container adicional. O bot inicia e encerra o
worker junto com seu ciclo de vida. Consultas PyMongo rodam fora do event loop.

## Instalar e configurar

Execute na raiz **PC2YOU**, duas pastas acima desta pasta. Reutilize o ambiente
existente; em uma instalação nova, crie-o com `python -m venv services/.venv`.

```powershell
& services/.venv/Scripts/python.exe -m pip install -r services/requirements-dev.txt
```

As dependências da primeira etapa continuam suficientes. Para execução sem
testes, basta `services/requirements.txt`. No `.env` existente, acrescente ou preencha:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHATS=
MONGO_DB=orcapc_catalog
TELEGRAM_ALLOWED_USERS=
TELEGRAM_ALERT_DEDUP_HOURS=6
TELEGRAM_NOTIFICATION_POLL_SECONDS=10
```

| Variável | Uso |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token do BotFather; nunca versionar |
| `TELEGRAM_ALLOWED_USERS` | IDs positivos separados por vírgula; vazio permite qualquer usuário em conversa privada |
| `TELEGRAM_ALERT_DEDUP_HOURS` | Horas de supressão de ofertas equivalentes por usuário/alerta; inteiro positivo |
| `TELEGRAM_NOTIFICATION_POLL_SECONDS` | Intervalo entre ciclos do worker; inteiro positivo |
| `MONGO_URI` / `MONGO_DB` | Mesmo servidor/banco do catálogo e do coletor |

Para uso pessoal, preencha a lista de usuários. Autorização usa exclusivamente
`telegram_user_id`; username não concede acesso. Operações de alertas e callbacks
funcionam somente em conversa privada. Cada operação também filtra pelo dono do
alerta/histórico, mesmo quando o ID do documento vem de um botão.

## Iniciar e descobrir seu ID

Obtenha o token com BotFather e inicie o bot com MongoDB disponível. Fora do Docker:

```powershell
$env:MONGO_URI = 'mongodb://localhost:27017'
& services/.venv/Scripts/python.exe -m services.telegram_bot.bot
```

Envie **`/meuid`** ao seu bot. Ele responde, por exemplo:

```text
Seu telegram_user_id: 123456789
```

Use seu número real em `TELEGRAM_ALLOWED_USERS=123456789` e reinicie o bot.
`/meuid`, `/ajuda`, `/start` e `/status` continuam acessíveis para facilitar a configuração.

## Primeiro alerta

```text
/acompanhar RTX 5070
```

O bot pergunta o preço máximo. Responda `3800`, `3.800`, `3800,00` ou
`R$ 3.800,00`. Também aceita `sem limite`. O resumo só vira um alerta persistido
quando você clica em **✅ Ativar** (ou **Salvar**, se estiver pausado/editando).
`/acompanhar` sem argumento pergunta primeiro qual é a peça.

O tipo é detectado quando possível: RTX/RX → gpu, Ryzen/Core i7 → cpu, B650 →
motherboard, DDR5 → ram, NVMe → storage, 750W → psu. Termos ambíguos permanecem
com tipo `null`, e o acompanhamento por texto continua disponível.

Em **⚙️ Mais filtros**, edite produto, preço, tipo, marcas permitidas/ignoradas,
lojas permitidas/ignoradas e desconto mínimo. Listas aceitam texto livre separado
por vírgulas; por exemplo `ASUS, GALAX, MSI` ou `KaBuM, Pichau`. No campo de marcas
ignoradas, `ignorar: Biostar` também funciona. `-` limpa uma lista, tipo ou desconto.
Pode alternar o estado ativo/pausado antes de salvar.

O desconto é um percentual de 0 a 100. Conforme a regra desta etapa, o filtro
percentual só é aplicado quando há preço original e atual confiáveis; sem preço
original ele não é aplicado. Já uma promoção sem preço atual confiável nunca
gera notificação, mesmo se o limite do alerta for `null`.

## Comandos

| Comando | Comportamento |
|---|---|
| `/start` | Apresentação do PC2YOU |
| `/status` | Banco, contagem de promoções, fontes e sinal do coletor |
| `/meuid` | Seu ID numérico; responder em conversa privada |
| `/acompanhar [modelo]` | Cadastro guiado com confirmação |
| `/alertas` | Listagem paginada, até 10 por página, com Editar/Pausar/Ativar/Remover |
| `/pausar` ou `/pausar 2` | Exibir botões ou pausar o alerta de número 2; não apagar |
| `/remover` ou `/remover 2` | Exibir botões ou solicitar confirmação antes de remover |
| `/ofertas` | Até 10 promoções relevantes para seus alertas ativos |
| `/cancelar` | Descartar o cadastro/edição em andamento |
| `/ajuda` | Lista de comandos e explicações curtas |

Marcas não diferenciam maiúsculas/minúsculas. Filtros de exclusão prevalecem
sobre os de inclusão. Lista de lojas permitidas vazia aceita qualquer loja;
uma lista preenchida exige loja conhecida e correspondente. Listas suportam
até 20 entradas de 40 caracteres; consultas têm até 120 caracteres.

Cadastros em andamento expiram após 15 minutos e ficam somente em memória.
Reiniciar o bot descarta rascunhos, preservando alertas já confirmados. Botões
de resumos antigos não ativam um cadastro diferente. A confirmação possui ID
estável para evitar cadastro duplicado após timeout da escrita no MongoDB.

## Notificações e persistência

- `price_alerts`: consulta, tipo, termos normalizados, `Decimal128` para preço e
  desconto, listas de filtros, estado, ID Telegram e datas UTC. Índices por dono
  e por estado/data. `user_id` do PC2YOU é opcional, sem integração ao catálogo.
- `notification_history`: índice único em usuário + alerta + promoção; guarda
  estados de entrega e identificação da mensagem enviada.
- `notification_dedup`: reserva da oferta equivalente, por usuário/alerta, com
  expiração. Usa `equivalent_offer_key()` e TTL, além de comparar a data na consulta.
- `telegram_notification_state`: marco inicial persistido e prazo de espera
  quando a Bot API aplica limitação de frequência.
- `telegram_promotions`: preserva texto, status e identidade originais; recebe
  somente os campos de controle de processamento/reagendamento de notificações.

Normalização trata acentos, hífens, espaços, unidades como `12 GB`/`12GB` e termos
irrelevantes como GeForce. Variantes Ti, SUPER, XT, XTX e X3D são preservadas.
RTX 5070 não corresponde a RTX 5070 Ti; RX 9070 não corresponde a RX 9070 XT;
7800X3D não corresponde a 7900X3D. Textos com modelos GPU conflitantes são recusados.

Na primeira inicialização, o worker registra um marco e não dispara todo o acervo
anterior. Após reinícios, utiliza o mesmo marco e considera pendências/novas
promoções. Um alerta só recebe automaticamente promoções armazenadas após sua
criação. `/ofertas` também permite consultar o acervo anterior: examina as 1000
mensagens mais recentes e retorna até 10 correspondentes.

A notificação mostra título disponível, preço, loja, cupom, limite, diferença e
desconto quando conhecidos. Botões: **Abrir oferta**, **Ignorar** e **Pausar alerta**.
O botão **🛒 Abrir oferta** usa exclusivamente `offer.url`. Sem URL HTTP/HTTPS
válida nesse campo, ele é omitido; o link do post Telegram não é usado como
fallback de compra. Isso também se aplica a `/ofertas`. Veja o roteiro de
[validação de links reais](../../docs/TELEGRAM_OFFER_LINKS.md).
Ignorar marca a notificação como dispensada e oculta essa promoção no `/ofertas`
daquele usuário; pausar conserva o alerta para reativação posterior.

Uma mensagem já notificada nunca é reenviada para o mesmo usuário/alerta.
Republicações equivalentes são suprimidas pela janela configurada, sem apagar
as mensagens coletadas. Para GPUs, a chave combina modelo/variante, marca e
capacidades quando reconhecidas; sem identidade ou loja suficientes, permanece
apenas a deduplicação por mensagem. Alertas distintos podem gerar uma notificação
para cada alerta, mesmo pertencendo ao mesmo usuário.

Falhas de MongoDB conservam pendências. `RetryAfter` agenda nova tentativa e pausa
o lote de envios até o prazo indicado. Bot bloqueado/pedido inválido é registrado
como `rejected`. Timeout/falha de rede, ou queda depois do envio e antes de gravar
a confirmação, pode deixar a entrega **`uncertain`**. Para evitar duplicatas,
esses casos não são reenviados automaticamente. A Bot API não permite garantir
entrega exatamente uma vez; `/ofertas` continua disponível para consulta manual.

## Testar sem grupo real

Simulação **totalmente offline**, sem credenciais nem MongoDB:

```powershell
& services/.venv/Scripts/python.exe scripts/telegram_demo.py
```

Ela imprime o matching e uma notificação fictícia de RTX 5070 GALAX por R$ 3.599,90.
Para testar o envio real sem depender de um grupo:

1. Inicie MongoDB e o bot, envie `/start` e confirme o alerta RTX 5070 até R$ 3.800.
2. Em outro terminal na raiz, execute:

```powershell
$env:MONGO_URI = 'mongodb://localhost:27017'
& services/.venv/Scripts/python.exe scripts/telegram_demo.py --enqueue
```

`--enqueue` grava uma promoção marcada `is_demo=true`, com origem fictícia
`SIMULAÇÃO LOCAL PC2YOU`. O worker pode enviar uma mensagem real a todos os alertas
ativos correspondentes. Ele não consulta grupos nem usa a conta Telethon. Repetir
a simulação verifica a supressão da oferta equivalente. Você pode alterar dados:

```powershell
& services/.venv/Scripts/python.exe scripts/telegram_demo.py --query 'RTX 5070 Ti' --price '3599,90'
```

Sem `--enqueue`, nenhuma gravação/envio acontece. A URL de demonstração aponta
apenas para a página inicial da loja; a promoção e seus preços são fictícios.

## Testes automatizados

```powershell
& services/.venv/Scripts/python.exe -m pytest services/tests -q
& services/.venv/Scripts/python.exe -m pip check
```

Resultado desta etapa: **195 testes passaram**, incluindo os 88 originais sem
alterar seus testes existentes. Foram adicionados casos de cadastro, edição,
propriedade/autorização, parsing, variantes, filtros, múltiplos usuários/alertas,
deduplicação, reprocessamento, reinícios, falhas MongoDB e falhas da Bot API.
Tudo utiliza mocks/mongomock, sem rede real. As dependências de teste emitem avisos
de depreciação que não afetam o resultado. Docker e envio real dependem do ambiente
e das credenciais do usuário; não foram executados na validação automatizada.

Após a correção de links de ofertas (27/10/2026), a suíte Telegram tem **253 testes
passando**, com **58 novos casos** de captura, seleção, reimportação e botões de
compra. Matching, filtros e deduplicação de notificações permanecem com o mesmo
comportamento. Somando as três APIs, foram validados **376 testes** no projeto.

## Docker

Na raiz do projeto, após configurar o `.env`:

```powershell
docker compose --profile telegram up -d --build telegram-bot
```

O serviço já existente `telegram-bot` recebe as três novas variáveis do Compose;
nenhuma porta ou serviço extra foi acrescentado. Reinicie/recrie o bot ao mudar
a lista de usuários. O coletor e sua sessão persistente continuam independentes.

## Limitações restantes

- Sem IA, scraping, matching com catálogo, frontend de promoções ou integração
  nova com Mercado Livre/histórico de preços.
- Regras textuais podem ter falsos positivos/negativos; não verificam estoque,
  autenticidade, validade de cupom ou se a oferta ainda está disponível.
- Modelos sem identidade confiável não têm supressão entre fontes. A identidade
  determinística não cobre todas as variantes comerciais de cada fabricante.
- Cadastros sem confirmação não sobrevivem a reinício. Promoções importadas
  agora contam como recém-armazenadas, mesmo se o texto original for antigo.
- Uma instância do bot por token é o modo de operação recomendado. O polling
  processa lotes de até 100 promoções, com envios sequenciais; não é uma fila de alto volume.
- Entregas `uncertain` e `rejected` ficam no histórico sem reenvio automático.
- Mensagens privadas brutas, tokens, hashes, telefone e códigos de login não são
  registrados. Filtros e IDs definidos pelo usuário são persistidos para o acompanhamento.

## Arquivos desta etapa

Criados, relativos à raiz PC2YOU:

```text
services/telegram_collector/matcher.py
services/telegram_bot/alerts.py
services/telegram_bot/handlers.py
services/telegram_bot/notifier.py
services/tests/test_alerts.py
services/tests/test_matcher.py
services/tests/test_notifier.py
services/tests/test_alert_handlers.py
scripts/telegram_demo.py
```

Alterados:

```text
README.md
.env.example
docker-compose.yml
scripts/README.md
services/README.md
services/telegram_collector/config.py
services/telegram_collector/models.py
services/telegram_collector/deduplication.py
services/telegram_collector/README.md
services/telegram_bot/bot.py
services/telegram_bot/README.md
services/tests/conftest.py
```

O `.env` existente, `collector.py`, parser/filtros de coleta, APIs e frontend não
foram alterados. O projeto usa exclusivamente a raiz `PC2YOU` reorganizada.
