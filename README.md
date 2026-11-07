# NOVA — triagem automática de e-mails de suporte

[![tests](https://github.com/AndrewMBarros/nova/actions/workflows/tests.yml/badge.svg)](https://github.com/AndrewMBarros/nova/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

NOVA é uma "secretária virtual" em Python que lê a caixa de e-mail do suporte, identifica **qual cliente
está escrevendo** (pelo e-mail, pelo CNPJ/CPF citado ou pelo nome da empresa) e monta um
**pré-atendimento** pronto para ser cadastrado como chamado em um sistema ERP. Quando falta
informação, ela mesma responde ao cliente pedindo o CNPJ/CPF, confere os dígitos e avisa a equipe
quando algo precisa de uma pessoa.

> **Todos os dados deste repositório são fictícios.** Clientes, CNPJs, nomes e endereços de e-mail
> existem apenas para os testes e os exemplos. Os CNPJs/CPFs de exemplo passam na validação dos
> dígitos verificadores, mas não correspondem a cadastros reais usados pelo projeto.

## Sobre a base de clientes

Em uso real, a base de clientes fica no **ERP**: é lá que a NOVA deve consultar se um CNPJ/CPF é
cliente e onde o chamado é aberto. Para o projeto rodar sem nenhum ERP, a base é simulada por
**arquivos de texto** em `data/`, editáveis no Bloco de Notas:

| Arquivo | O que é | Formato |
|---|---|---|
| `data/clientes.txt` | clientes cadastrados (substitui a consulta ao ERP) | `CNPJ_ou_CPF;Nome;contatos_opcionais;apelidos_opcionais` |
| `data/grupos.txt` | pessoas que, no De ou no Cc, mandam o e-mail direto para um cliente | `CNPJ;email1,email2,@dominio` |
| `data/bloqueados.txt` | remetentes/domínios que a NOVA nunca responde | um por linha |

Os arquivos são relidos automaticamente quando você salva (cache por data de modificação), sem reiniciar.
Para integrar um ERP de verdade, só `find_customer()` em `app/customers/service.py` precisa mudar
(veja [Integração com um ERP](#integração-com-um-erp)).

## Como funciona

```
e-mail chega ─► filtros ─► identifica o cliente ─────────────► pré-atendimento salvo + confirmação ao cliente
                  │          1. regra de grupo (De/Cc)              (Cliente, Contato, Tipo, Canal,
                  │          2. e-mail/domínio já vinculado          Tipo de Acesso, Observações)
                  │          3. CNPJ/CPF no texto (valida dígitos)
                  │          4. nome da empresa na assinatura  ──► marcado [CONFIRMAR CLIENTE]
                  │          5. não achou ──► pede o CNPJ/CPF (até N vezes) ──► escala para a equipe
                  │
                  └─► ignora: noreply, respostas automáticas, duplicados, assuntos/remetentes
                      bloqueados, e-mails da própria equipe, conversas anteriores ao go-live
```

Principais recursos:

- **Leitura por data**, nunca por "não lido": um corte (`PROCESS_FROM` ou `--go-live`) garante que
  a NOVA nunca responde ao histórico da caixa.
- **Validação de CNPJ/CPF** (dígitos verificadores, quantidade de dígitos, CNPJ alfanumérico) sem
  confundir telefone, data ou protocolo com documento.
- **Vínculo contato ↔ cliente:** depois de validado uma vez, o mesmo endereço não precisa informar o
  CNPJ de novo. Domínios inteiros só quando cadastrados explicitamente; provedores públicos
  (Gmail, Outlook...) nunca são vinculados por domínio.
- **Identificação pelo nome** citado na assinatura, com regras contra falso positivo (nome mais
  específico vence, empate = pede o CNPJ, palavras genéricas não contam).
- **Conversas:** mensagens seguintes de um atendimento já validado não geram novo chamado; se alguém
  da equipe responde, a NOVA sai da conversa; cabeçalho `References` acumulado para o Gmail não
  quebrar a thread.
- **Robustez:** retry automático de falhas de envio, escalonamento por tempo sem resposta
  (`STALE_WAITING_HOURS`), pré-atendimento idempotente e datas sempre em UTC.
- **Três modos de e-mail:** simulador (`console`), IMAP/SMTP (Gmail, grátis) e Microsoft Graph
  (Microsoft 365), cada um com uma variante `*_readonly` que só registra o que seria respondido.

## Começando

Requisitos: Python 3.10+ (ou Docker).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
uvicorn app.main:app --reload
```

O `.env.example` já vem com `ENVIRONMENT=dev`, que liga o simulador. Abra http://localhost:8000/docs
e use `POST /dev/simulate-email`:

| Cenário | from_email | body |
|---|---|---|
| Sem CNPJ (NOVA pede o documento) | cliente@empresa.com | Estamos sem internet |
| CNPJ cadastrado (valida e vincula o e-mail) | cliente@empresa.com | CNPJ: 12.345.678/0001-95 |
| Mesmo remetente, conversa nova, sem CNPJ | cliente@empresa.com | Estamos sem telefone (outro `conversation_id`) |
| CNPJ válido, mas não cadastrado (recusa + avisa a equipe) | cliente@empresa.com | CNPJ: 11.222.333/0001-81 |
| Identificação pelo nome | qualquer@gmail.com | Ramal mudo.<br>Omega Vila Nova |
| noreply (ignorado) | noreply@sistema.com | qualquer |

Outras rotas de desenvolvimento: `GET /dev/outbox` (o que a NOVA responderia), `GET /dev/emails`
(memória/estados), `GET /dev/pre-atendimentos`, `GET /dev/customers`, `GET /dev/links`.

> ⚠️ As rotas `/dev/*` não têm autenticação e mostram a base de clientes. Elas só existem com
> `ENVIRONMENT=dev`; o padrão, sem `.env`, é `prod`. Nunca publique um servidor com `ENVIRONMENT=dev`.

### Com Docker

```bash
cp .env.example .env
docker compose up --build                    # API + PostgreSQL em http://localhost:8000
docker compose --profile worker up --build   # também sobe o worker que lê a caixa de e-mail
```

A pasta `data/` é montada no container: editar `data/clientes.txt` vale sem reconstruir a imagem.

### Testes e lint

```bash
pytest
ruff check .
```

Os dois rodam automaticamente no GitHub Actions a cada push (`.github/workflows/tests.yml`).

### Usando uma caixa de e-mail real (Gmail, gratuito)

Passo a passo completo em [`docs/guia-gmail.md`](docs/guia-gmail.md). Resumo:

1. Crie um Gmail só para a NOVA, ative a verificação em duas etapas e gere uma **senha de aplicativo**.
2. No `.env`: `NOVA_EMAIL`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_MODE=imap_readonly`.
3. `python -m app.imap_check` — testa a conexão (só lê).
4. `python -m app.worker --once` — um ciclo: lê, decide e só registra a resposta no log.
5. `python -m app.worker --go-live` — marca "agora" como início (nada do histórico é respondido).
6. `MAIL_MODE=imap` quando quiser que ela responda de verdade.

### Microsoft 365 (Graph)

`MAIL_MODE=graph_readonly` / `graph`, com `MICROSOFT_CLIENT_ID` (e `MICROSOFT_CLIENT_SECRET` no modo
aplicativo) de um app registrado no Entra ID. Teste com `python -m app.graph_check`.
Os módulos de `app/microsoft/` ainda não foram testados contra uma caixa real.

## Configuração

Tudo é lido do `.env` (veja `.env.example`). As principais opções:

| Variável | Padrão | Para quê |
|---|---|---|
| `COMPANY_NAME` | `Sua Empresa` | nome exibido nas mensagens e na assinatura |
| `ENVIRONMENT` | `prod` | `dev` liga as rotas `/dev/*` (só localmente) |
| `MAIL_MODE` | `console` | `console`, `imap_readonly`, `imap`, `graph_readonly`, `graph` |
| `NOVA_EMAIL` / `TEAM_EMAIL` | — | caixa da NOVA / e-mail que recebe os avisos internos |
| `PROCESS_FROM` | 1ª execução | corte por data (ISO 8601) |
| `ONLY_SENDERS` | — | piloto: processa só estes remetentes |
| `TEAM_SENDERS` | — | endereços/@domínios da equipe (a NOVA sai da conversa) |
| `BLOCKED_SENDERS` / `BLOCKED_SUBJECTS` | — | bloqueios rápidos (vírgula) |
| `MAX_DOCUMENT_REQUESTS` | `2` | quantas vezes pede o CNPJ/CPF antes de escalar |
| `STALE_WAITING_HOURS` | `48` | escala se o cliente não responder (0 = desliga) |
| `CONTACT_LINKS_ENABLED` | `true` | lembrar contatos já validados |
| `LINK_DOMAIN_AUTO` | `false` | aprender o domínio inteiro (não só o e-mail) |
| `NAME_MATCH_ENABLED` | `true` | identificar o cliente pelo nome |
| `IGNORE_UNKNOWN_REPLIES` | `true` | ignorar respostas a conversas anteriores ao go-live |
| `TICKET_TYPE` / `TICKET_CHANNEL` / `TICKET_ACCESS_TYPE` | `Suporte Técnico` / `E-mail` / `Remoto` | valores fixos de cada pré-atendimento |
| `DATABASE_URL` | `sqlite:///./nova.db` | banco (SQLite ou `postgresql+psycopg://...`) |

Utilitários de linha de comando:

```bash
python -m app.manage_customers listar | adicionar "<CNPJ>" "<Nome>" | remover "<CNPJ>"
python -m app.manage_links     listar | adicionar "<CNPJ>" "<email ou @dominio>" | remover ...
python -m app.manage_blocklist listar | adicionar "@dominio.com" | remover ...
```

## Integração com um ERP

O ponto de integração está marcado em `app/processor.py` (`# >>> INTEGRAÇÃO ERP`):

1. **Consulta de clientes:** trocar o corpo de `find_customer()` (`app/customers/service.py`) por uma
   chamada à API do ERP. O resto do fluxo (vínculos, nomes, grupos) usa essa mesma função.
2. **Abertura do chamado:** enviar o registro de `PreAtendimento` (`app/database/models.py`) ao ERP e
   guardar o número do chamado retornado.
3. **Confirmação ao cliente:** mandar a confirmação só depois que o chamado for criado.

## Privacidade (LGPD)

A NOVA processa dados pessoais: endereço, nome e texto dos e-mails, além do CNPJ/CPF dos clientes.
Se você for usá-la com e-mails reais:

- **Banco:** o corpo das mensagens, os remetentes, os vínculos contato ↔ cliente e o log de eventos
  ficam no banco (`DATABASE_URL`). Proteja o acesso a ele e defina por quanto tempo guardar esses dados.
- **Respostas:** o CPF aparece mascarado nas respostas aos clientes. Clientes reconhecidos pelo e-mail
  nunca recebem o próprio documento de volta.
- **Avisos à equipe:** incluem um trecho da mensagem do cliente, então `TEAM_EMAIL` deve ser uma
  caixa interna.
- **Acesso:** as rotas `/dev/*` expõem esses dados e só devem existir em ambiente local (`ENVIRONMENT=dev`).
- **Base legal:** você é responsável pela base legal do tratamento e pelos direitos dos titulares
  (acesso, correção e exclusão) no seu ambiente.

## Estrutura

```
app/
  processor.py          fluxo principal (filtros -> identifica cliente -> pré-atendimento)
  worker.py             laço que lê a caixa (IMAP ou Graph)
  config.py             configurações (.env)
  customers/            base de clientes (service), vínculos (contacts), nomes (names), grupos (groups)
  documents/            extração e validação de CNPJ/CPF
  email/                parser, templates, envio (SMTP/Graph) e leitura (IMAP/Graph)
  microsoft/            autenticação MSAL e cliente Graph
  rules/                noreply, automáticos, bloqueios e estados
  database/             SQLAlchemy: e-mails, eventos, vínculos, pré-atendimentos
  api/                  /health e rotas /dev (simulador)
data/                   base de clientes simulada (arquivos de texto)
docs/                   guias (ex.: Gmail por IMAP)
tests/                  testes automatizados (pytest)
.github/workflows/      CI: ruff + pytest a cada push
Dockerfile, docker-compose.yml   API/worker + PostgreSQL
```

## Roadmap

- Integração real com um ERP (consulta de clientes e abertura de chamados).
- Migrações de banco com Alembic (hoje as tabelas são criadas na inicialização).
- Autenticação nas rotas de administração.
- Classificação do tipo de atendimento a partir do texto do e-mail.

As novidades de cada versão estão em [`CHANGELOG.md`](CHANGELOG.md).

## Licença

[MIT](LICENSE).
