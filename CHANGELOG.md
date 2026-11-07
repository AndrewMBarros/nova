# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e em
[Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.0.0] — primeira versão pública

### Leitura da caixa de e-mail
- Três modos: simulador (`console`), IMAP/SMTP (Gmail) e Microsoft Graph (Microsoft 365), cada um com
  uma variante `*_readonly` que só registra o que seria respondido.
- Leitura por **data**, nunca por "não lido", a partir de um corte (`PROCESS_FROM`). O comando
  `python -m app.worker --go-live` define o corte como "agora", e nada do histórico da caixa é respondido.
- No IMAP, os e-mails mais antigos são lidos primeiro (`BATCH_SIZE` por ciclo), drenando o backlog sem
  deixar mensagens para trás.
- Datas sempre gravadas em UTC, independentemente do fuso do remetente.

### Filtros
- Ignora noreply, respostas automáticas (`Auto-Submitted`), duplicados e mensagens da própria caixa.
- Bloqueio de remetentes/domínios (`data/bloqueados.txt` ou `BLOCKED_SENDERS`) e de assuntos
  (`BLOCKED_SUBJECTS`, ex.: alertas de sistemas).
- Modo piloto (`ONLY_SENDERS`): processa só os remetentes listados.
- Respostas a conversas anteriores ao go-live são ignoradas (`IGNORE_UNKNOWN_REPLIES`), com recuperação
  de pedidos pendentes quando o provedor muda a identificação da thread.
- E-mails da equipe (`TEAM_SENDERS`) nunca recebem resposta; a partir daí a conversa é da equipe.

### Identificação do cliente
Ordem de prioridade:
1. **Regra de grupo** (`data/grupos.txt`): pessoas que, no De ou no Cc, mandam o e-mail direto para um cliente.
2. **Vínculo de contato:** o endereço completo de quem já foi validado uma vez é lembrado (tabela
   `contact_links`). Domínios inteiros só quando cadastrados explicitamente ou com `LINK_DOMAIN_AUTO=true`;
   provedores públicos (Gmail, Outlook etc.) nunca são vinculados por domínio. Ambiguidades e vínculos
   de clientes removidos são tratados sem adivinhar.
3. **CNPJ/CPF no texto:** validação dos dígitos verificadores e da quantidade de dígitos (inclui CNPJ
   alfanumérico); com vários documentos na mensagem, prefere o que estiver cadastrado. Telefones, datas e
   protocolos não são confundidos com documento.
4. **Nome da empresa** na assinatura ou em frases de apresentação: o nome mais específico vence, empate é
   tratado como ambíguo, palavras genéricas não contam. O pré-atendimento nasce marcado
   `[CONFIRMAR CLIENTE]` e nenhum vínculo é gravado.
5. Se nada funcionar, pede o CNPJ/CPF (até `MAX_DOCUMENT_REQUESTS` vezes) e depois escala para a equipe.

### Respostas ao cliente e à equipe
- Mensagens claras para cada caso: pedido do documento, número incorreto (com o motivo), documento válido
  mas sem cadastro, cadastro confirmado e limite de tentativas. Todas avisam que são automáticas.
- CPF exibido com dígitos ocultos; quando o cliente é reconhecido pelo vínculo, o documento não é exposto.
- Nome da empresa nas mensagens configurável (`COMPANY_NAME`), assim como os campos fixos do
  pré-atendimento (`TICKET_TYPE`, `TICKET_CHANNEL`, `TICKET_ACCESS_TYPE`).
- Avisos à equipe com limite de repetição (`MAX_NOT_FOUND_NOTIFICATIONS`).
- Cabeçalho `References` acumulado (RFC 5322), para a conversa não se partir no Gmail.

### Pré-atendimento e robustez
- Cada atendimento validado gera um **pré-atendimento** (Cliente, Contato, Tipo de Atendimento, Canal,
  Tipo de Acesso, Observações), pronto para ser enviado a um ERP. Mensagens seguintes da mesma conversa
  não duplicam o chamado.
- Escalonamento por tempo sem resposta do cliente (`STALE_WAITING_HOURS`).
- Retry automático de falhas, com status próprio para falha de envio (`REPLY_ERROR`), e pré-atendimento
  idempotente.
- Log de eventos por e-mail no banco (SQLite por padrão, PostgreSQL suportado).

### Ferramentas
- Base de clientes simulada em arquivos de texto (`data/`), relidos automaticamente ao salvar.
- Utilitários de linha de comando: `manage_customers`, `manage_links`, `manage_blocklist`.
- API de desenvolvimento (FastAPI) com simulador de e-mails e consulta do estado interno, desligada por
  padrão (`ENVIRONMENT=prod`).
- Testes automatizados com pytest e lint com ruff, rodando no GitHub Actions (Python 3.10 e 3.12).
- Dockerfile e docker-compose com PostgreSQL (API e worker).
