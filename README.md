> **Versão independente de apresentação:** comece por [README-DEMO.md](README-DEMO.md). Acesse `/apresentacao` na porta 5174.

# PC2YOU-APRESENTACAO

[Apresentação em PDF — 18 páginas](docs/demo/PC2YOU-Apresentacao.pdf)

> **Telegram:** coleta de promoções e alertas pessoais, usando o MongoDB atual.
> Consulte o [guia do coletor](services/telegram_collector/README.md) e o
> [cadastro de alertas, notificações e testes](services/telegram_bot/README.md).

**Comece por aqui:** [serviços e Telegram](services/README.md) ·
[AI v1 — Analisar meu PC](docs/AI.md) ·
[bot do Telegram](services/telegram_bot/README.md) ·
[scripts de manutenção](scripts/README.md) ·
[documentação complementar](docs/README_PC2YOU_ATUALIZADO.md) ·
[organização das pastas](docs/ORGANIZACAO.md).

![Status](https://img.shields.io/badge/status-funcional-blue)
![Docker](https://img.shields.io/badge/docker-compose-blue)
![Python](https://img.shields.io/badge/backend-FastAPI-blue)
![React](https://img.shields.io/badge/frontend-React%20%2B%20Vite-2563EB)
![Banco](https://img.shields.io/badge/database-PostgreSQL%20%2B%20MongoDB-orange)

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Explicação simples: o que é o PC2YOU?](#2-explicação-simples-o-que-é-o-pc2you)
3. [Objetivo acadêmico](#3-objetivo-acadêmico)
4. [Integrantes](#4-integrantes)
5. [Funcionalidades principais](#5-funcionalidades-principais)
6. [Arquitetura geral](#6-arquitetura-geral)
7. [Arquitetura explicada para leigos](#7-arquitetura-explicada-para-leigos)
8. [Tecnologias utilizadas](#8-tecnologias-utilizadas)
9. [Estrutura de pastas](#9-estrutura-de-pastas)
10. [Como rodar o projeto](#10-como-rodar-o-projeto)
11. [Como testar se está funcionando](#11-como-testar-se-está-funcionando)
12. [Documentação técnica das APIs](#12-documentação-técnica-das-apis)
13. [Documentação técnica do frontend](#13-documentação-técnica-do-frontend)
14. [Documentação técnica dos bancos de dados](#14-documentação-técnica-dos-bancos-de-dados)
15. [Regras de compatibilidade](#15-regras-de-compatibilidade)
16. [Fluxo completo do sistema](#16-fluxo-completo-do-sistema)
17. [Roteiro de apresentação](#17-roteiro-de-apresentação)
18. [Comandos úteis](#18-comandos-úteis)
19. [Problemas comuns e soluções](#19-problemas-comuns-e-soluções)
20. [Segurança, persistência e operação atuais](#20-segurança-persistência-e-operação-atuais)
21. [Limitações reais e melhorias futuras](#21-limitações-reais-e-melhorias-futuras)
22. [Resumo final para o professor](#22-resumo-final-para-o-professor)

---

# 1. Visão geral

O **PC2YOU** é uma aplicação distribuída para **orçamento e montagem guiada de computadores**.

A proposta do sistema é ajudar o usuário a escolher peças de computador de forma mais segura, evitando combinações incompatíveis e facilitando a visualização de preços, lojas e desempenho estimado.

O usuário consegue:

- criar uma conta;
- fazer login;
- navegar por um catálogo de peças;
- pesquisar componentes como processadores, placas de vídeo, fontes, memórias e gabinetes;
- ver ficha técnica de cada peça;
- visualizar preços por loja;
- favoritar componentes;
- montar um computador por etapas;
- receber apenas opções compatíveis com a montagem;
- gerar um orçamento final;
- visualizar preço total, links de compra e desempenho estimado.

---

# 2. Explicação simples: o que é o PC2YOU?

> **Fala, viajante da tecnologia. Imagina que você entrou numa loja para montar um computador, mas cada peça fala uma língua diferente.**
>
> O processador pergunta: “qual é meu socket?”
>
> A placa-mãe responde: “depende, eu aceito AM4, AM5 ou LGA1700.”
>
> A memória RAM grita lá do fundo: “eu sou DDR4, não me coloca numa placa DDR5!”
>
> E a fonte olha para a placa de vídeo e pergunta: “você consome quanta energia mesmo?”
>
> O **PC2YOU** entra como o organizador da bancada. Ele segura sua mão e diz:
>
> “Escolhe primeiro o processador. Agora eu só vou te mostrar placas-mãe que combinam com ele. Escolheu a placa-mãe? Então agora só aparecem memórias compatíveis. No final, eu junto tudo, calculo o preço e te mostro um orçamento organizado.”
>
> Em outras palavras: o PC2YOU é um sistema que ajuda uma pessoa a montar um computador sem se perder em termos técnicos, preços e compatibilidade.

---

# 3. Objetivo acadêmico

Este projeto foi desenvolvido para a disciplina de **Sistemas Operacionais**, com foco em **Docker, containers e aplicações distribuídas**.

A atividade exige uma aplicação com:

| Requisito | Como o PC2YOU atende |
|---|---|
| Uso de Docker | Cada serviço possui container próprio |
| Uso de Docker Compose | O projeto possui `docker-compose.yml` na raiz |
| No mínimo 5 containers | O projeto possui 6 containers |
| 2 bancos de dados | PostgreSQL e MongoDB |
| 3 aplicações Python | `api-usuarios`, `api-catalogo`, `api-orcamentos` |
| APIs com CRUD | Usuários, catálogo e orçamentos possuem endpoints de cadastro, consulta, atualização e remoção |
| Comunicação entre containers | `api-orcamentos` consulta `api-catalogo` via rede Docker |
| Persistência de dados | Volumes `postgres_data` e `mongo_data` |
| Frontend funcional | React + Vite em container próprio |

---

# 4. Integrantes

- **Vinicius Gussoni Vellosa**
- **Gustavo Henrique Femiano**
- **Jean Domiciano de Menezes**
- **Yasmim Fernandes de Paula**
- **João Pedro de Jesus Miranda**

---

# 5. Funcionalidades principais

## 5.1 Cadastro e login

O sistema permite que o usuário crie uma conta e faça login.

A senha não é salva diretamente no banco. Ela passa por um processo de **hash**, usando `passlib[bcrypt]`.

### Explicação simples

> Guardar senha pura no banco é como deixar a chave da casa em cima do tapete.  
> O hash é como transformar essa chave em uma forma embaralhada. O sistema consegue conferir se você digitou a senha certa, mas não precisa guardar a senha original.

---

## 5.2 Catálogo de peças

O catálogo lista componentes de computador, como:

- processadores;
- placas-mãe;
- memórias RAM;
- SSDs;
- placas de vídeo;
- fontes;
- gabinetes.

Cada peça possui:

- `id`;
- `name`;
- `category`;
- `brand`;
- `image`;
- `description`;
- `technical_specs`;
- `compatibility`;
- `prices`;
- `benchmark`.

---

## 5.3 Busca e filtros

O usuário pode buscar uma peça por nome ou filtrar por categoria.

Exemplos:

```text
RTX
Intel
Ryzen
DDR5
Fonte
```

Também existe filtro por categoria:

```text
gpu
cpu
motherboard
ram
storage
psu
case
```

---

## 5.4 Detalhes da peça

Ao abrir uma peça, o usuário vê:

- nome;
- marca;
- categoria;
- imagem;
- descrição;
- ficha técnica;
- informações de compatibilidade;
- preços por loja;
- melhor preço;
- benchmark.

---

## 5.5 Favoritos

O usuário pode salvar peças favoritas.

Isso permite guardar componentes interessantes para comparar depois.

Tecnicamente, os favoritos são salvos no PostgreSQL na tabela `favorites`.

---

## 5.6 Monte seu PC

Esta é a funcionalidade mais importante do projeto.

O sistema guia o usuário por etapas:

1. Processador;
2. Placa-mãe;
3. Memória RAM;
4. Armazenamento;
5. Placa de vídeo;
6. Fonte;
7. Gabinete.

A cada etapa, o sistema consulta as peças já escolhidas e mostra apenas opções compatíveis.

---

## 5.7 Orçamento final

Depois de selecionar as peças, o sistema gera um orçamento com:

- lista de componentes;
- melhor preço de cada item;
- loja recomendada;
- link de compra;
- preço total;
- desempenho estimado.

---

# 6. Arquitetura geral

A aplicação foi dividida em múltiplos serviços. Cada serviço roda em um container separado.

```text
                         ┌──────────────────────┐
                         │      Frontend        │
                         │    React + Vite      │
                         │ localhost:5173       │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
│    api-usuarios      │ │    api-catalogo      │ │   api-orcamentos     │
│ FastAPI + SQLAlchemy │ │ FastAPI + MongoDB    │ │ FastAPI + SQLAlchemy │
│ localhost:8001       │ │ localhost:8002       │ │ localhost:8003       │
└──────────┬───────────┘ └──────────┬───────────┘ └──────────┬───────────┘
           │                        │                        │
           ▼                        ▼                        │
┌──────────────────────┐ ┌──────────────────────┐            │
│    PostgreSQL        │ │       MongoDB        │            │
│ usuários/favoritos   │ │ catálogo de peças    │◄───────────┘
│ orçamentos           │ │ ficha técnica/preços │
└──────────────────────┘ └──────────────────────┘
```

---

# 7. Arquitetura explicada para leigos

> Pense no sistema como uma loja grande, mas bem organizada.
>
> O **frontend** é a vitrine. É onde o usuário clica, pesquisa, vê peças e monta o PC.
>
> A **API de usuários** é o balcão de atendimento. Ela cuida de cadastro, login e favoritos.
>
> A **API de catálogo** é o estoque técnico. Ela guarda as peças, marcas, preços e especificações.
>
> A **API de orçamentos** é o consultor especialista. Ela olha para as peças escolhidas e diz:
>
> “Isso combina.”
>
> ou
>
> “Essa memória não serve nessa placa-mãe.”
>
> O **PostgreSQL** é o arquivo de documentos da loja: usuários, favoritos e orçamentos.
>
> O **MongoDB** é a prateleira flexível de peças, porque cada peça tem ficha técnica diferente.
>
> O **Docker Compose** é o gerente que liga tudo de uma vez.

---

# 8. Tecnologias utilizadas

## 8.1 Backend

| Tecnologia | Uso |
|---|---|
| Python | Linguagem das APIs |
| FastAPI | Framework para criação das APIs |
| Uvicorn | Servidor ASGI que executa as APIs |
| SQLAlchemy | Comunicação com PostgreSQL |
| Pydantic | Validação de dados de entrada e saída |
| Passlib + bcrypt | Hash de senha |
| PyMongo | Comunicação com MongoDB |
| Requests | Comunicação entre APIs |

---

## 8.2 Frontend

| Tecnologia | Uso |
|---|---|
| React | Construção da interface |
| Vite | Servidor de desenvolvimento e build |
| Axios | Requisições HTTP para as APIs |
| React Router DOM | Navegação entre páginas |
| Lucide React | Ícones |
| CSS moderno | Layout, animações e responsividade |

---

## 8.3 Banco de dados

| Banco | Uso |
|---|---|
| PostgreSQL | Usuários, favoritos e orçamentos |
| MongoDB | Catálogo de peças |

---

## 8.4 Infraestrutura

| Tecnologia | Uso |
|---|---|
| Docker | Containerização dos serviços |
| Docker Compose | Orquestração dos containers |
| Volumes Docker | Persistência dos dados |

---

# 9. Estrutura de pastas

A estrutura principal do projeto é:

```text
PC2YOU/
│
├── api-usuarios/
│   ├── main.py
│   ├── crud.py
│   ├── models.py
│   ├── schemas.py
│   ├── database.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── api-catalogo/
│   ├── main.py
│   ├── services.py
│   ├── schemas.py
│   ├── seed.py
│   ├── database.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── api-orcamentos/
│   ├── main.py
│   ├── services.py
│   ├── compatibility.py
│   ├── performance.py
│   ├── models.py
│   ├── schemas.py
│   ├── database.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
│
├── docker-compose.yml
├── .env.example
├── .gitignore
├── services/           # Coletor, bot e testes Telegram
├── scripts/            # Manutenção e diagnósticos
├── reports/            # Relatórios locais gerados
├── docs/               # Documentação complementar
└── README.md
```

---

# 10. Como rodar o projeto

## 10.1 Pré-requisitos

Antes de rodar, instale:

- Docker Desktop;
- Git, se for clonar pelo GitHub;
- navegador moderno, como Chrome, Edge ou Firefox.

Confirme se o Docker está funcionando:

```bash
docker --version
```

Depois:

```bash
docker compose version
```

---

## 10.2 Clonar o projeto

Se estiver no GitHub:

```bash
git clone <URL_DO_REPOSITORIO>
cd PC2YOU
```

Se estiver em arquivo `.zip`, extraia e entre na pasta onde está o `docker-compose.yml`.

---

## 10.3 Rodar com Docker Compose

Na raiz do projeto, crie o arquivo local de configuração se ele ainda não existir:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie o valor gerado para `JWT_SECRET` e gere outro valor para `ADMIN_API_KEY`. O `.env` é
local, está no `.gitignore` e não deve ser enviado em ZIP, commit ou imagem Docker. Tokens do
Mercado Livre são opcionais; sem eles o catálogo preserva e utiliza os preços seedados. Se um
token real já foi compartilhado, revogue-o no provedor e gere outro.

Variáveis essenciais:

| Variável | Obrigatória | Uso |
|---|---:|---|
| `JWT_SECRET` | Sim | Assinatura e validação dos JWTs entre as três APIs |
| `JWT_ALGORITHM` | Sim | Algoritmo HMAC (`HS256`, `HS384` ou `HS512`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Sim | Expiração do token de acesso |
| `ADMIN_API_KEY` | Para administração | Protege escrita, seed e sync total do catálogo |
| `CORS_ORIGINS` | Sim | Lista explícita de origens permitidas |
| `MERCADO_LIVRE_ACCESS_TOKEN` | Não | Atualização opcional de ofertas reais |

Valide e suba os serviços:

```bash
docker compose config --quiet
docker compose up --build
```

Esse comando:

1. baixa as imagens do PostgreSQL e MongoDB;
2. constrói as três APIs Python;
3. constrói o frontend;
4. cria a rede Docker;
5. cria os volumes de persistência;
6. sobe todos os serviços.

---

## 10.4 Acessar o sistema

Depois que os containers subirem:

| Serviço | URL |
|---|---|
| Frontend | `http://localhost:5173` |
| Swagger API Usuários | `http://localhost:8001/docs` |
| Swagger API Catálogo | `http://localhost:8002/docs` |
| Swagger API Orçamentos | `http://localhost:8003/docs` |

---

## 10.5 Parar o projeto

Para parar os containers:

```bash
docker compose down
```

Para parar e apagar também os dados salvos nos volumes:

```bash
docker compose down -v
```

> Atenção: `docker compose down -v` apaga os dados do PostgreSQL e MongoDB.

---

## Ambientes Python locais

O ambiente principal para rodar as suítes de teste é `.venv-ai/` (na raiz). Ele cobre
`api-usuarios`, `api-catalogo`, `api-orcamentos` e `services`. `services/.venv/` é opcional e
documentado apenas para executar o coletor/bot Telegram localmente. Nenhum ambiente é versionado.
Veja [docs/CLEANUP_AUDIT.md](docs/CLEANUP_AUDIT.md).

# 11. Como testar se está funcionando

## 11.1 Testar health checks

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

Resposta esperada:

```json
{"status":"ok","service":"api-usuarios"}
```

```json
{"status":"ok","service":"api-catalogo"}
```

```json
{"status":"ok","service":"api-orcamentos"}
```

---

## 11.2 Testar catálogo

```bash
curl "http://localhost:8002/components?category=gpu&q=rtx"
```

Esse comando deve retornar placas de vídeo RTX, como:

- RTX 4060;
- RTX 4070 Super;
- RTX 4080 Super;
- RTX 5090.

Detalhe de uma peça:

```bash
curl http://localhost:8002/components/rtx-4070-super
```

Melhor preço:

```bash
curl http://localhost:8002/components/rtx-4070-super/best-price
```

---

## 11.3 Testar cadastro com PowerShell

No PowerShell, prefira `Invoke-RestMethod`:

```powershell
$body = @{
  name = "Gustavo"
  email = "gustavo@email.com"
  password = "123456"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://localhost:8001/auth/register" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

---

## 11.4 Testar login com PowerShell

```powershell
$login = @{
  email = "gustavo@email.com"
  password = "123456"
} | ConvertTo-Json

$session = Invoke-RestMethod `
  -Uri "http://localhost:8001/auth/login" `
  -Method POST `
  -ContentType "application/json" `
  -Body $login

$headers = @{ Authorization = "Bearer $($session.access_token)" }
```

---

## 11.5 Testar favoritos

```powershell
$fav = @{
  user_id = 1
  component_id = "rtx-4070-super"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://localhost:8001/favorites" `
  -Method POST `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $fav
```

Listar favoritos:

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/favorites/1" -Headers $headers
```

---

## 11.6 Testar compatibilidade

```powershell
$compat = @{
  cpu_id = "intel-i5-14600k"
  motherboard_id = "b760-lga1700-ddr5"
  ram_id = "ram-32gb-ddr5"
  gpu_id = "rtx-4070-super"
  psu_id = "fonte-750w"
  case_id = "gabinete-atx"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://localhost:8003/compatibility/check" `
  -Method POST `
  -ContentType "application/json" `
  -Body $compat
```

Resposta esperada:

```json
{
  "compatible": true,
  "errors": [],
  "selected_categories": [
    "cpu",
    "motherboard",
    "ram",
    "gpu",
    "psu",
    "case"
  ]
}
```

---

## 11.7 Testar orçamento final

```powershell
$budget = @{
  user_id = 1
  components = @(
    "intel-i5-14600k",
    "cooler-deepcool-ak400",
    "b760-lga1700-ddr5",
    "ram-32gb-ddr5",
    "ssd-nvme-1tb",
    "rtx-4070-super",
    "fonte-750w",
    "gabinete-atx"
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "http://localhost:8003/build/finalize" `
  -Method POST `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $budget
```

A resposta deve conter:

- `budget_id`;
- `user_id`;
- `items`;
- `total_price`;
- `performance`.

---

# 12. Documentação técnica das APIs

---

## 12.1 API de usuários

Pasta:

```text
api-usuarios/
```

Porta externa:

```text
localhost:8001
```

Porta interna no Docker:

```text
8000
```

Banco usado:

```text
PostgreSQL
```

Responsabilidades:

- cadastro;
- login;
- CRUD de usuários;
- favoritos.

---

### 12.1.1 `api-usuarios/main.py`

Arquivo principal da API.

Ele:

- cria a aplicação FastAPI;
- configura CORS;
- cria as tabelas no startup;
- define endpoints de usuário;
- define endpoints de favoritos.

Principais endpoints:

```text
GET    /health
POST   /auth/register
POST   /auth/login
GET    /users
GET    /users/{user_id}
PUT    /users/{user_id}
DELETE /users/{user_id}
POST   /favorites
GET    /favorites/{user_id}
DELETE /favorites/{user_id}/{component_id}
```

### Explicação simples

> Esse arquivo é como a porta principal do balcão de atendimento.  
> Quando alguém quer criar conta, entrar no sistema ou favoritar uma peça, ele passa por aqui.

---

### 12.1.2 `api-usuarios/database.py`

Responsável pela conexão com o PostgreSQL.

Ele monta a URL do banco usando variáveis de ambiente:

```text
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB
POSTGRES_HOST
POSTGRES_PORT
```

Se existir uma variável `DATABASE_URL`, ela tem prioridade.

Também cria:

- `engine`;
- `SessionLocal`;
- `Base`;
- função `get_db()`.

### Termos técnicos

| Termo | Significado |
|---|---|
| Engine | Objeto que sabe se conectar ao banco |
| Session | Uma conversa temporária com o banco |
| Base | Classe base usada pelos models |
| get_db | Função usada pelo FastAPI para abrir e fechar conexão por requisição |

### Explicação simples

> Esse arquivo é o telefone que a API usa para falar com o banco.  
> Ele sabe o endereço, usuário e senha do PostgreSQL.

---

### 12.1.3 `api-usuarios/models.py`

Define as tabelas do PostgreSQL.

Tabelas:

```text
users
favorites
```

Modelo `User`:

```text
id
name
email
password_hash
```

Modelo `Favorite`:

```text
id
user_id
component_id
```

Existe uma regra de unicidade:

```text
user_id + component_id
```

Isso impede que o mesmo usuário favorite a mesma peça várias vezes.

### Explicação simples

> Esse arquivo desenha as fichas que serão guardadas no arquivo da loja.
>
> A ficha do usuário guarda nome, e-mail e senha protegida.
>
> A ficha de favoritos guarda quais peças aquele usuário salvou.

---

### 12.1.4 `api-usuarios/schemas.py`

Define os formatos de entrada e saída da API usando Pydantic.

Exemplos:

- `UserCreate`;
- `UserUpdate`;
- `UserResponse`;
- `LoginRequest`;
- `LoginResponse`;
- `FavoriteCreate`;
- `FavoriteResponse`.

Ele também valida dados.

Exemplo:

```text
password precisa ter pelo menos 6 caracteres
email precisa ter formato válido
name precisa ter pelo menos 2 caracteres
```

### Explicação simples

> Esse arquivo é o fiscal da entrada.  
> Se alguém tenta cadastrar senha curta demais ou e-mail errado, ele barra antes de chegar no banco.

---

### 12.1.5 `api-usuarios/crud.py`

Contém a lógica de banco da API de usuários.

Funções importantes:

```text
hash_password
verify_password
get_user
get_user_by_email
get_users
create_user
update_user
delete_user
create_favorite
list_favorites
delete_favorite
```

O arquivo usa:

```python
CryptContext(schemes=["bcrypt"], deprecated="auto")
```

para gerar e verificar hash de senha.

### Explicação simples

> Esse arquivo é o funcionário que realmente mexe nas gavetas do banco.
>
> O `main.py` recebe o pedido.  
> O `crud.py` executa a ação no banco.

---

## 12.2 API de catálogo

Pasta:

```text
api-catalogo/
```

Porta externa:

```text
localhost:8002
```

Banco usado:

```text
MongoDB
```

Responsabilidades:

- cadastrar peças;
- listar peças;
- pesquisar peças;
- filtrar por categoria e marca;
- consultar detalhes;
- atualizar peça;
- remover peça;
- retornar preços;
- retornar melhor preço;
- popular o catálogo inicial.

---

### 12.2.1 `api-catalogo/main.py`

Arquivo principal da API de catálogo.

No startup, ele:

1. tenta conectar ao MongoDB;
2. executa `ping`;
3. verifica se a coleção está vazia;
4. se estiver vazia, roda o seed automático.

Endpoints:

```text
GET    /health
POST   /components
GET    /components
GET    /components/{component_id}
PUT    /components/{component_id}
DELETE /components/{component_id}
GET    /components/{component_id}/prices
GET    /components/{component_id}/best-price
POST   /seed
```

### Explicação simples

> Esse arquivo é o atendente do estoque.  
> Ele sabe responder: “tem RTX 4070?”, “qual o melhor preço?”, “quais peças são GPU?”, “me mostra a ficha técnica”.

---

### 12.2.2 `api-catalogo/database.py`

Conecta a API ao MongoDB.

Variáveis usadas:

```text
MONGO_URI
MONGO_DB
```

A coleção principal é:

```text
components
```

### Explicação simples

> Esse arquivo aponta para a prateleira onde ficam as peças.

---

### 12.2.3 `api-catalogo/schemas.py`

Define o formato das peças.

Uma peça possui:

```text
id
name
category
brand
image
description
technical_specs
compatibility
prices
benchmark
```

`technical_specs` e `compatibility` são dicionários flexíveis.

Isso é importante porque cada peça tem informações diferentes.

Exemplo:

- CPU tem `cores`, `threads`, `tdp_watts`;
- GPU tem `memory`, `power_consumption_watts`, `length_mm`;
- gabinete tem `supported_form_factors`, `max_gpu_length_mm`.

### Explicação simples

> Peças de PC não são todas iguais.
>
> Uma fonte fala em watts.  
> Uma memória fala em DDR4 ou DDR5.  
> Uma placa de vídeo fala em tamanho e consumo.
>
> Por isso o MongoDB e os campos flexíveis ajudam bastante.

---

### 12.2.4 `api-catalogo/services.py`

Contém a lógica do catálogo.

Funções principais:

```text
create_component
list_components
get_component
update_component
delete_component
best_price
```

A busca usa filtros do MongoDB, incluindo regex para pesquisar texto.

Exemplo:

```text
q=rtx
```

busca em:

```text
name
brand
description
```

### Explicação simples

> Esse arquivo é a pessoa que anda pelo estoque procurando a peça certa.

---

### 12.2.5 `api-catalogo/seed.py`

Cria os dados iniciais do catálogo.

Ele insere peças como:

- Intel Core i5-14600K;
- AMD Ryzen 7 5700X;
- RTX 4070 Super;
- RTX 5090;
- placas-mãe AM4, AM5 e LGA1700;
- RAM DDR4 e DDR5;
- SSDs;
- fontes;
- gabinetes.

Cada peça possui preços simulados em lojas como:

- Kabum;
- Pichau;
- Terabyte.

### Observação importante

Os preços e links são usados para demonstração acadêmica. Eles não representam consulta em tempo real.

### Explicação simples

> O seed é o caminhão que chega antes da loja abrir e coloca produtos nas prateleiras.
>
> Sem ele, o catálogo começaria vazio.

---

## 12.3 API de orçamentos

Pasta:

```text
api-orcamentos/
```

Porta externa:

```text
localhost:8003
```

Banco usado:

```text
PostgreSQL
```

Também consome:

```text
api-catalogo
```

Responsabilidades:

- criar orçamento;
- salvar orçamento;
- listar orçamento;
- atualizar orçamento;
- remover orçamento;
- validar compatibilidade;
- guiar montagem por etapas;
- finalizar build;
- calcular desempenho.

---

### 12.3.1 `api-orcamentos/main.py`

Arquivo principal da API de orçamentos.

Endpoints:

```text
GET    /health
POST   /budgets
GET    /budgets/{budget_id}
GET    /budgets/user/{user_id}
PUT    /budgets/{budget_id}
DELETE /budgets/{budget_id}
POST   /compatibility/check
POST   /build/next-options
POST   /build/finalize
GET    /performance/{budget_id}
```

### Comunicação com outra API

A `api-orcamentos` consulta a `api-catalogo` usando:

```text
http://api-catalogo:8000
```

Esse endereço só funciona dentro da rede Docker.

### Explicação simples

> Essa API é o especialista da bancada.  
> Ela olha para as peças escolhidas e fala:
>
> “Isso encaixa.”
>
> ou
>
> “Essa fonte não aguenta essa placa de vídeo.”

---

### 12.3.2 `api-orcamentos/models.py`

Define as tabelas de orçamento no PostgreSQL.

Tabelas:

```text
budgets
budget_items
```

Tabela `budgets`:

```text
id
user_id
name
total_price
performance
created_at
```

Tabela `budget_items`:

```text
id
budget_id
component_id
name
category
best_price
store
url
```

Existe relacionamento entre `Budget` e `BudgetItem`.

### Explicação simples

> O orçamento é como uma nota organizada.
>
> A tabela `budgets` guarda o cabeçalho: de quem é, nome, total e desempenho.
>
> A tabela `budget_items` guarda as linhas: processador, placa-mãe, memória, GPU, etc.

---

### 12.3.3 `api-orcamentos/schemas.py`

Define os formatos de entrada e saída.

Principais schemas:

```text
BudgetCreate
BudgetUpdate
BudgetItemResponse
BudgetResponse
CompatibilityCheck
NextOptionsRequest
BuildFinalize
```

### Explicação simples

> Esse arquivo define como os pedidos devem chegar e como as respostas devem sair.

---

### 12.3.4 `api-orcamentos/compatibility.py`

Contém as regras de compatibilidade.

Ordem das etapas:

```python
STEP_CATEGORIES = ["cpu", "motherboard", "ram", "storage", "gpu", "psu", "case"]
```

Regras implementadas:

1. CPU e placa-mãe precisam ter o mesmo socket.
2. Placa-mãe e RAM precisam usar o mesmo tipo de memória.
3. Fonte precisa atender a potência mínima da GPU.
4. Gabinete precisa suportar o formato da placa-mãe.
5. Gabinete precisa ter espaço para o tamanho da GPU.

### Explicação simples

> Esse arquivo é o juiz de encaixe.
>
> Ele verifica se as peças conversam entre si antes de deixar o orçamento passar.

---

### 12.3.5 `api-orcamentos/performance.py`

Calcula desempenho estimado.

O cálculo usa três notas cadastradas em cada peça:

```text
gaming_score
workstation_score
ai_score
```

Peso usado:

```text
gaming: 50%
workstation: 30%
ai: 20%
```

Depois o sistema gera frases como:

```text
Excelente para 1440p
Muito bom
Básico
```

### Explicação simples

> Esse arquivo não roda benchmark real.  
> Ele usa pontuações cadastradas para criar uma estimativa simples de desempenho.

---

### 12.3.6 `api-orcamentos/services.py`

É o centro da lógica de orçamento.

Ele:

- consulta componentes na `api-catalogo`;
- busca melhor preço;
- valida orçamento;
- verifica compatibilidade;
- calcula total;
- calcula desempenho;
- salva o orçamento no PostgreSQL;
- transforma o orçamento em resposta JSON.

Funções importantes:

```text
fetch_component
fetch_components
list_catalog_components
get_best_price
quote_component
validate_budget_components
create_or_update_budget
budget_to_response
get_budget
get_user_budgets
delete_budget
```

### Explicação simples

> Esse arquivo é o gerente da montagem.
>
> Ele pega as peças, pergunta para o catálogo quanto custam, verifica se tudo combina, soma o preço e salva o orçamento.

---

# 13. Documentação técnica do frontend

Pasta:

```text
frontend/
```

Tecnologias:

```text
React
Vite
Axios
React Router DOM
Lucide React
CSS
```

Porta:

```text
localhost:5173
```

---

## 13.1 `frontend/src/api.js`

Centraliza a comunicação com as APIs.

Cria três clientes Axios:

```text
usersApi
catalogApi
budgetsApi
```

Também possui funções auxiliares:

```text
getStoredUser
formatCurrency
getBestPrice
```

### Explicação simples

> Esse arquivo é a central telefônica do frontend.  
> Toda vez que a tela precisa falar com uma API, ela usa uma dessas linhas.

---

## 13.2 `frontend/src/App.jsx`

Define as rotas do frontend.

Rotas principais:

```text
/
 /login
 /register
 /components/:id
 /favorites
 /build
 /budget/:id
```

### Explicação simples

> Esse arquivo é o mapa do site.  
> Ele decide qual página aparece quando o usuário muda de endereço.

---

## 13.3 `frontend/src/components/Header.jsx`

Cabeçalho do sistema.

Mostra:

- logo PC2YOU;
- barra de busca;
- botão Montar PC;
- favoritos;
- alternância de modo claro/escuro;
- usuário logado ou botões de login/cadastro.

### Explicação simples

> É a barra de navegação que acompanha o usuário pelo sistema.

---

## 13.4 `frontend/src/components/ComponentCard.jsx`

Card visual de cada peça.

Mostra:

- imagem;
- botão de favorito;
- categoria;
- marca;
- nome;
- descrição;
- principais especificações;
- menor preço;
- loja;
- botão de detalhes.

### Explicação simples

> É a “vitrine pequena” de uma peça.

---

## 13.5 `frontend/src/components/FavoriteButton.jsx`

Botão de favoritar peça.

Se o usuário não estiver logado, ele é redirecionado para login.

Se estiver logado:

- adiciona favorito;
- remove favorito;
- atualiza o estado visual.

---

## 13.6 `frontend/src/components/PriceTable.jsx`

Mostra tabela de preços.

Colunas:

- loja;
- preço;
- data de atualização;
- link para abrir a loja.

---

## 13.7 `frontend/src/components/PerformanceBox.jsx`

Mostra o desempenho estimado do orçamento ou da build.

---

## 13.8 `frontend/src/components/LoadingState.jsx`

Mostra carregamento com skeleton ou painel de loading.

---

## 13.9 `frontend/src/components/EmptyState.jsx`

Mostra estados vazios bonitos.

Exemplo:

```text
Você ainda não favoritou nenhuma peça.
```

---

## 13.10 `frontend/src/pages/Home.jsx`

Página inicial e catálogo.

Responsável por:

- hero principal;
- busca;
- filtros por categoria;
- listagem de peças;
- favoritos no catálogo;
- cards de componentes.

---

## 13.11 `frontend/src/pages/ComponentDetails.jsx`

Página de detalhes de uma peça.

Mostra:

- imagem;
- nome;
- marca;
- categoria;
- descrição;
- ficha técnica;
- compatibilidade;
- tabela de preços;
- desempenho.

---

## 13.12 `frontend/src/pages/Favorites.jsx`

Página de favoritos do usuário.

Ela busca favoritos da API de usuários e cruza com dados do catálogo para mostrar os cards completos.

---

## 13.13 `frontend/src/pages/Build.jsx`

Página de montagem guiada.

É uma das páginas mais importantes.

Ela:

1. guarda as peças selecionadas;
2. chama `/build/next-options`;
3. recebe a próxima categoria;
4. mostra opções compatíveis;
5. atualiza o resumo;
6. finaliza em `/build/finalize`.

### Explicação simples

> Essa página é o guia passo a passo.  
> Ela mostra uma peça por vez e só deixa o usuário continuar com opções compatíveis.

---

## 13.14 `frontend/src/pages/BudgetResult.jsx`

Mostra o orçamento final.

Exibe:

- lista de peças;
- preço de cada peça;
- loja;
- link;
- total;
- desempenho estimado.

---

# 14. Documentação técnica dos bancos de dados

---

## 14.1 PostgreSQL

Usado em:

```text
api-usuarios
api-orcamentos
```

Tabelas:

```text
users
favorites
budgets
budget_items
```

### Por que PostgreSQL?

Porque ele é ideal para dados relacionais.

Exemplo:

- usuário tem favoritos;
- orçamento tem itens;
- item pertence a um orçamento.

Essas relações ficam bem modeladas em banco relacional.

---

## 14.2 MongoDB

Usado em:

```text
api-catalogo
```

Coleção:

```text
components
```

### Por que MongoDB?

Porque peças de computador têm fichas técnicas diferentes.

Uma CPU não tem os mesmos campos de uma fonte.

O MongoDB permite guardar documentos flexíveis sem precisar criar uma tabela enorme cheia de campos vazios.

---

## 14.3 Exemplo de componente no MongoDB

```json
{
  "id": "rtx-4070-super",
  "name": "GeForce RTX 4070 Super",
  "category": "gpu",
  "brand": "NVIDIA",
  "image": "https://placehold.co/800x520/0f172a/f8fafc.png?text=rtx+4070+super",
  "description": "GeForce RTX 4070 Super para montagem de PCs com foco em compatibilidade e custo-beneficio.",
  "technical_specs": {
    "memory": "12GB GDDR6X",
    "interface": "PCIe 4.0",
    "power_consumption_watts": 220,
    "length_mm": 305
  },
  "compatibility": {
    "min_psu_watts": 650,
    "interface": "PCIe"
  },
  "prices": [
    {
      "store": "Kabum",
      "price": 4283.90,
      "url": "https://www.kabum.com.br/busca/rtx+4070+super",
      "last_update": "2026-05-11"
    }
  ],
  "benchmark": {
    "gaming_score": 87,
    "workstation_score": 78,
    "ai_score": 72
  }
}
```

---

# 15. Regras de compatibilidade

As regras estão no arquivo:

```text
api-orcamentos/compatibility.py
```

---

## 15.1 CPU + placa-mãe

Regra:

```text
socket da CPU == socket da placa-mãe
```

Exemplo compatível:

```text
Intel Core i5-14600K → LGA1700
B760 LGA1700 DDR5 → LGA1700
```

Exemplo incompatível:

```text
Intel Core i5-14600K → LGA1700
B550 AM4 DDR4 → AM4
```

---

## 15.2 Placa-mãe + RAM

Regra:

```text
tipo de memória da placa-mãe == tipo de memória da RAM
```

Exemplo:

```text
Placa-mãe DDR5 → RAM DDR5
Placa-mãe DDR4 → RAM DDR4
```

---

## 15.3 GPU + fonte

Regra:

```text
potência da fonte >= potência mínima recomendada da GPU
```

Exemplo:

```text
RTX 4070 Super exige 650W
Fonte 750W atende
```

---

## 15.4 Placa-mãe + gabinete

Regra:

```text
formato da placa-mãe precisa estar nos formatos suportados pelo gabinete
```

Exemplo:

```text
Gabinete ATX suporta ATX, Micro-ATX e Mini-ITX
```

---

## 15.5 GPU + gabinete

Regra:

```text
comprimento da GPU <= comprimento máximo suportado pelo gabinete
```

Exemplo:

```text
GPU de 305mm
Gabinete suporta 380mm
Compatível
```

---

# 16. Fluxo completo do sistema

## 16.1 Fluxo do catálogo

```text
Usuário abre o frontend
        ↓
Frontend chama api-catalogo
        ↓
api-catalogo consulta MongoDB
        ↓
MongoDB retorna components
        ↓
Frontend renderiza cards
```

---

## 16.2 Fluxo de login

```text
Usuário envia e-mail e senha
        ↓
Frontend chama api-usuarios
        ↓
api-usuarios busca usuário no PostgreSQL
        ↓
api-usuarios verifica senha com bcrypt
        ↓
retorna usuário + token acadêmico
        ↓
frontend salva usuário no localStorage
```

---

## 16.3 Fluxo de favorito

```text
Usuário clica no coração
        ↓
Frontend verifica usuário logado
        ↓
Frontend chama api-usuarios
        ↓
api-usuarios salva component_id na tabela favorites
        ↓
Frontend atualiza o botão visualmente
```

---

## 16.4 Fluxo de montagem

```text
Usuário entra em Montar PC
        ↓
Frontend pede próxima etapa para api-orcamentos
        ↓
api-orcamentos consulta api-catalogo
        ↓
api-orcamentos filtra opções compatíveis
        ↓
frontend mostra opções
        ↓
usuário seleciona peça
        ↓
processo repete até completar
```

---

## 16.5 Fluxo de orçamento final

```text
Usuário finaliza montagem
        ↓
Frontend envia lista de componentes
        ↓
api-orcamentos busca detalhes na api-catalogo
        ↓
api-orcamentos valida compatibilidade
        ↓
api-orcamentos calcula melhor preço por peça
        ↓
api-orcamentos soma total
        ↓
api-orcamentos estima desempenho
        ↓
api-orcamentos salva no PostgreSQL
        ↓
Frontend mostra orçamento final
```

---

# 17. Roteiro de apresentação

## Antes de apresentar

```bash
docker compose down -v
docker compose up --build
```

Depois conferir:

```bash
docker compose ps
```

Testar:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

---

## Demonstração no navegador

Acessar:

```text
http://localhost:5173
```

Roteiro:

1. Mostrar a página inicial PC2YOU.
2. Explicar que o frontend está em React.
3. Pesquisar `RTX`.
4. Abrir a RTX 4070 Super.
5. Mostrar ficha técnica, preços e melhor preço.
6. Criar usuário ou fazer login.
7. Favoritar a peça.
8. Abrir favoritos.
9. Ir para “Montar PC”.
10. Escolher:
    - Intel Core i5-14600K;
    - B760 LGA1700 DDR5;
    - RAM 32GB DDR5;
    - SSD NVMe 1TB;
    - RTX 4070 Super;
    - Fonte 750W;
    - Gabinete ATX.
11. Gerar orçamento final.
12. Mostrar preço total, links e desempenho.
13. Explicar PostgreSQL e MongoDB.
14. Explicar que `api-orcamentos` consulta `api-catalogo`.

---

# 18. Comandos úteis

## Subir tudo

```bash
docker compose up --build
```

## Subir em segundo plano

```bash
docker compose up --build -d
```

## Parar containers

```bash
docker compose down
```

## Parar e apagar volumes

```bash
docker compose down -v
```

## Ver containers

```bash
docker compose ps
```

## Ver logs de uma API

```bash
docker compose logs api-usuarios --tail=100
docker compose logs api-catalogo --tail=100
docker compose logs api-orcamentos --tail=100
```

## Rebuildar só uma API

```bash
docker compose build --no-cache api-usuarios
docker compose up
```

## Popular catálogo manualmente

```bash
curl -X POST -H "X-Admin-Key: <SUA_CHAVE_ADMIN>" http://localhost:8002/seed
```

---

# 19. Problemas comuns e soluções

## 19.1 `docker` não é reconhecido

Erro:

```text
docker não é reconhecido como nome de cmdlet
```

Solução:

1. abrir Docker Desktop;
2. fechar e abrir o terminal;
3. testar:

```bash
docker --version
```

---

## 19.2 Erro de JSON no PowerShell usando curl

No PowerShell, `curl` pode se comportar diferente.

Prefira:

```powershell
Invoke-RestMethod
```

ou use:

```powershell
curl.exe
```

Para requisições POST com JSON, `Invoke-RestMethod` é mais seguro.

---

## 19.3 Erro de senha menor que 6 caracteres

O sistema exige senha com pelo menos 6 caracteres.

Errado:

```text
1234
```

Certo:

```text
123456
```

---

## 19.4 Erro com bcrypt/passlib

Durante o desenvolvimento, pode ocorrer erro de compatibilidade entre `passlib` e `bcrypt`.

A correção usada é fixar:

```text
bcrypt==4.0.1
```

em:

```text
api-usuarios/requirements.txt
```

Depois rebuildar:

```bash
docker compose build --no-cache api-usuarios
docker compose up
```

---

## 19.5 Catálogo vazio

Se o catálogo estiver vazio:

```bash
curl -X POST -H "X-Admin-Key: <SUA_CHAVE_ADMIN>" http://localhost:8002/seed
```

ou:

```bash
curl -X POST -H "X-Admin-Key: <SUA_CHAVE_ADMIN>" http://localhost:8002/seed
```

---

# 20. Segurança, persistência e operação atuais

A versão atual usa JWT Bearer assinado e com expiração. As APIs de usuários e orçamentos
validam a identidade do token e impedem acesso a dados de outra conta. O catálogo mantém as
consultas públicas, exige JWT nas atualizações individuais de preços e `X-Admin-Key` nas
operações administrativas.

| Método e rota | Serviço | Acesso | Finalidade |
|---|---|---|---|
| `POST /auth/register` | Usuários | Público | Criar conta |
| `POST /auth/login` | Usuários | Público | Emitir JWT Bearer |
| `/users*`, `/favorites*` | Usuários | JWT + proprietário | Perfil e favoritos da própria conta |
| `GET /components*` | Catálogo | Público | Catálogo, filtros, preços e histórico |
| `POST /components/batch` | Catálogo | Público | Consultar vários IDs em uma chamada |
| `POST /components/{id}/refresh-real-prices` | Catálogo | JWT | Atualização individual com cooldown |
| Escrita, `/seed`, sync total | Catálogo | `X-Admin-Key` | Administração |
| `POST /compatibility/check`, `/build/next-options` | Orçamentos | Público | Montagem guiada |
| `/budgets*`, `/build/finalize`, `/performance*` | Orçamentos | JWT + proprietário | Orçamentos privados |
| `/health`, `/health/live`, `/health/ready` | Todas as APIs | Público | Compatibilidade, liveness e readiness |

As migrations são executadas automaticamente antes das APIs PostgreSQL iniciarem. Cada
serviço usa uma tabela de versão própria, evitando disputa no banco compartilhado:

- `alembic_version_users`;
- `alembic_version_budgets`.

Execução manual:

```bash
docker compose run --rm api-usuarios alembic upgrade head
docker compose run --rm api-orcamentos alembic upgrade head
```

Testes isolados, sem usar o banco real nem chamar o Mercado Livre:

```bash
docker compose run --rm --no-deps api-usuarios pytest -q
docker compose run --rm --no-deps api-catalogo pytest -q
docker compose run --rm --no-deps api-orcamentos pytest -q
```

Os logs incluem serviço, método, rota, status, duração e `request_id`. O identificador é
propagado de `api-orcamentos` para `api-catalogo`; senhas, JWTs e tokens externos não são
registrados.

---

# 21. Limitações reais e melhorias futuras

- Não há refresh token nem recuperação de senha; ao expirar, o usuário faz login novamente.
- O cooldown de atualização do Mercado Livre é local a cada processo; múltiplas réplicas
  exigiriam cache/lock compartilhado.
- Regras avançadas como BIOS por geração, conectores elétricos específicos e interfaces de
  armazenamento ainda podem ser ampliadas.
- Alertas de queda de preço, compartilhamento público de builds, CI/CD e deploy em nuvem não
  fazem parte desta versão.
- PostgreSQL e MongoDB continuam expostos nas portas locais para desenvolvimento; em produção,
  remova essas publicações e mantenha apenas a rede interna.

---

# 22. Resumo final para o professor

O **PC2YOU** é uma aplicação distribuída desenvolvida com **React, FastAPI, PostgreSQL, MongoDB e Docker Compose**.

O sistema foi estruturado em múltiplos containers para simular um ambiente real de microsserviços:

- um container para o frontend;
- três containers para APIs Python;
- um container PostgreSQL;
- um container MongoDB.

A aplicação implementa cadastro e login de usuários, catálogo de peças, favoritos, montagem guiada de computador, validação de compatibilidade, orçamento final, cálculo de preço total e estimativa de desempenho.

A comunicação entre containers é demonstrada principalmente na `api-orcamentos`, que consulta a `api-catalogo` via rede interna do Docker Compose para validar peças e montar o orçamento.

O PostgreSQL armazena dados relacionais, como usuários, favoritos e orçamentos. O MongoDB armazena o catálogo flexível de peças, pois cada componente possui ficha técnica diferente.

O projeto cumpre os requisitos principais da atividade:

- uso de Docker;
- uso de Docker Compose;
- no mínimo 5 containers;
- 2 bancos de dados;
- 3 aplicações Python;
- comunicação entre containers;
- CRUD;
- persistência de dados;
- frontend funcional.

---

# Apêndice A — Tradução dos termos técnicos

| Termo | Explicação simples |
|---|---|
| API | Uma porta de comunicação entre sistemas |
| Backend | Parte invisível que processa dados |
| Frontend | Parte visual que o usuário usa |
| Container | Uma caixinha isolada onde um serviço roda |
| Docker | Ferramenta que cria e roda containers |
| Docker Compose | Arquivo que liga vários containers juntos |
| Banco de dados | Lugar onde as informações ficam salvas |
| PostgreSQL | Banco organizado em tabelas |
| MongoDB | Banco flexível, baseado em documentos |
| CRUD | Criar, consultar, atualizar e remover |
| Endpoint | Endereço de uma função da API |
| JSON | Formato de troca de dados |
| Seed | Dados iniciais colocados no banco |
| Hash | Senha embaralhada e protegida |
| CORS | Regra que permite frontend conversar com backend |
| Volume | Espaço persistente para dados do Docker |
| Socket | Encaixe entre processador e placa-mãe |
| TDP | Consumo/calor estimado de um componente |
| PSU | Fonte de alimentação |
| GPU | Placa de vídeo |
| CPU | Processador |
| RAM | Memória temporária do computador |

---

# Apêndice B — Explicação humanizada final

> Imagine que o PC2YOU é uma oficina de computadores futurista.
>
> Na entrada, o usuário vê uma vitrine bonita com várias peças.
>
> Quando ele escolhe um processador, o sistema chama o especialista da oficina:
>
> “Ei, quais placas-mãe combinam com esse processador?”
>
> O especialista consulta o estoque, olha os encaixes, compara os dados e responde:
>
> “Essas aqui servem. Aquelas ali não.”
>
> Depois o usuário escolhe a memória. O sistema pergunta de novo:
>
> “Essa memória fala a mesma língua da placa-mãe?”
>
> Se sim, continua. Se não, bloqueia.
>
> No final, o PC2YOU monta uma espécie de ficha técnica da máquina: peças escolhidas, lojas, preços, links e desempenho estimado.
>
> Assim, o usuário não precisa decorar socket, DDR4, DDR5, watts, tamanho de GPU ou formato de gabinete. O sistema faz esse trabalho pesado e mostra tudo de forma organizada.

---

# Apêndice C — Build recomendada para demonstração

Use esta combinação porque ela foi testada e é compatível:

```text
CPU:          intel-i5-14600k
Placa-mãe:   b760-lga1700-ddr5
RAM:          ram-32gb-ddr5
SSD:          ssd-nvme-1tb
GPU:          rtx-4070-super
Fonte:        fonte-750w
Gabinete:     gabinete-atx
```

---

# Apêndice D — Checklist rápido para entrega

- [ ] `docker compose up --build` funciona.
- [ ] Frontend abre em `http://localhost:5173`.
- [ ] `api-usuarios` responde `/health`.
- [ ] `api-catalogo` responde `/health`.
- [ ] `api-orcamentos` responde `/health`.
- [ ] Catálogo carrega.
- [ ] Busca por `RTX` funciona.
- [ ] Cadastro funciona.
- [ ] Login funciona.
- [ ] Favoritos funcionam.
- [ ] Montagem guiada funciona.
- [ ] Orçamento final funciona.
- [ ] README está no GitHub.
- [ ] Não existem `node_modules`, `dist`, `__pycache__` ou `.pyc` no zip final.
