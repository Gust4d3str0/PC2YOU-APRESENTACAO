# Serviços do PC2YOU

Esta pasta contém os processos de Telegram, separados das APIs e do frontend.

- **[Coletor e guia completo](telegram_collector/README.md):** credenciais MTProto,
  autenticação, IDs dos grupos/canais, importação, filtros, parser, MongoDB e Docker.
- **[Bot do Telegram](telegram_bot/README.md):** configuração, `/acompanhar`,
  filtros, gerenciamento de alertas, notificações e simulação de promoções.
- **[Projeto principal](../README.md):** como iniciar APIs, bancos e frontend.

## Começar pelo Telegram

Abra um terminal na raiz `PC2YOU`, onde está o `docker-compose.yml`:

```powershell
python -m venv services/.venv
& services/.venv/Scripts/python.exe -m pip install -r services/requirements-dev.txt
```

Acrescente suas variáveis Telegram ao `.env`, conforme `.env.example`.
Se executar fora do Docker, use o endereço publicado do MongoDB:

```powershell
$env:MONGO_URI = 'mongodb://localhost:27017'
& services/.venv/Scripts/python.exe -m services.telegram_collector.collector auth
& services/.venv/Scripts/python.exe -m services.telegram_collector.collector list-chats
```

Preencha `TELEGRAM_ALLOWED_CHATS` no `.env` antes de iniciar a coleta:

```powershell
& services/.venv/Scripts/python.exe -m services.telegram_collector.collector listen --import-history
```

Em outro terminal, com o mesmo `MONGO_URI`:

```powershell
& services/.venv/Scripts/python.exe -m services.telegram_bot.bot
```

No bot, envie `/meuid` e coloque o ID obtido em `TELEGRAM_ALLOWED_USERS` para
uso pessoal. Reinicie o bot, envie `/acompanhar RTX 5070`, informe `3800` e
confirme em **Ativar**. O worker de notificações inicia junto com o bot;
o coletor continua apenas coletando e salvando no MongoDB.

Sem Telegram real, simule o matching e a mensagem de notificação localmente:

```powershell
& services/.venv/Scripts/python.exe scripts/telegram_demo.py
```

O [guia do bot](telegram_bot/README.md) explica como inserir a promoção fictícia
no MongoDB para testar também o envio, sem usar um grupo real.

## Testes

```powershell
& services/.venv/Scripts/python.exe -m pytest services/tests -q
```

Nenhuma credencial ou conexão real com Telegram é necessária para os testes.
