from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da NOVA (lidas do .env; veja .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "NOVA - triagem de e-mails de suporte"
    app_version: str = "1.0.0"
    environment: str = "prod"  # "dev" habilita as rotas /dev/* (simulador, sem autenticação): só use localmente

    # Banco (memória da NOVA). Sem Docker, SQLite já funciona.
    database_url: str = "sqlite:///./nova.db"

    # Nome da empresa exibido nas mensagens ao cliente e na assinatura
    company_name: str = "Sua Empresa"

    # Valores fixos de cada pré-atendimento (campos de abertura de chamado no ERP)
    ticket_type: str = "Suporte Técnico"
    ticket_channel: str = "E-mail"
    ticket_access_type: str = "Remoto"

    # Endereços
    nova_email: str = ""   # caixa da NOVA
    team_email: str = ""   # aviso interno (ex.: cliente não informa CNPJ após N tentativas)

    # Modo de e-mail:
    #   console        -> nada sai de verdade; use o simulador (/dev/simulate-email)
    #   imap_readonly  -> lê a caixa por IMAP (Gmail gratuito), só REGISTRA as respostas
    #   imap           -> lê por IMAP, responde por SMTP e marca como tratado de verdade
    #   graph_readonly / graph -> o mesmo, pelo Microsoft Graph
    mail_mode: str = "console"

    # IMAP/SMTP (Gmail por padrão)
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    mail_username: str = ""
    mail_password: str = ""         # SENHA DE APLICATIVO (não a senha normal)
    from_name: str = ""             # nome exibido nas respostas
    reply_to: str = ""              # para onde o cliente responde, se diferente da caixa da NOVA

    # Microsoft Graph
    microsoft_auth_mode: str = "delegated"
    microsoft_tenant_id: str = "common"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_mailbox: str = ""
    token_cache_path: str = ".token_cache.json"

    # O que a NOVA lê (por DATA, nunca por "não lido")
    process_from: str = ""      # ex.: 2026-09-21T08:00:00 ; vazio = a partir da 1ª execução
    mark_read: bool = False
    mark_category: str = "NOVA"

    # Regras
    poll_interval_seconds: int = 60
    batch_size: int = 25
    max_document_requests: int = 2
    max_not_found_notifications: int = 1  # nº de vezes que a equipe é avisada p/ mesmo remetente+documento
    stale_waiting_hours: int = 48  # sem resposta do cliente por mais que isso, escala pra equipe (0 = desliga)
    max_retries: int = 3  # tentativas automáticas para e-mails que falharam (status ERROR) antes de precisar de ação manual
    blocked_senders: str = ""        # trechos a bloquear, separados por vírgula (.env, uso rápido)
    blocked_senders_file: str = "data/bloqueados.txt"  # lista maior, um por linha (recomendado)
    blocked_subjects: str = ""       # trechos de assunto a ignorar (alertas de sistemas)
    group_rules_file: str = "data/grupos.txt"  # pessoas que, no De ou no Cc, mandam o e-mail direto p/ um cliente/grupo
    customers_file: str = "data/clientes.txt"  # base de clientes de teste (documento;nome por linha)

    # Resposta (Re:/References) a uma conversa que a NOVA nunca viu = conversa anterior ao go-live,
    # possivelmente já atendida por uma pessoa. True = não responde. Conversa nova e limpa segue normal.
    ignore_unknown_replies: bool = True

    # Quem é da equipe de suporte (endereços ou @dominios, separados por vírgula). Se alguém da equipe
    # escreve numa conversa, ela passa a ser da equipe e a NOVA não se intromete mais nela.
    team_senders: str = ""

    # Vínculo contato <-> CNPJ/CPF: quem já foi validado uma vez não precisa informar o CNPJ de novo.
    contact_links_enabled: bool = True   # False = volta a sempre pedir o CNPJ/CPF quando ele não vem no e-mail
    # Por padrão, aprende apenas o endereço completo. Aprender um domínio inteiro
    # pode liberar qualquer funcionário sem conferência; habilite somente se isso
    # for desejado para clientes específicos.
    link_domain_auto: bool = False
    shared_email_domains: str = ""       # domínios públicos extras (vírgula) que NUNCA são vinculados por domínio

    # sem vínculo de e-mail/domínio e sem CNPJ/CPF no texto, tenta reconhecer o cliente pelo
    # NOME citado no e-mail (assinatura/apresentação). Abre o pré-atendimento marcado "confirmar cliente".
    # False = volta a pedir o CNPJ/CPF direto.
    name_match_enabled: bool = True

    only_senders: str = ""           # PILOTO: se preenchido, só processa estes remetentes
    allow_reply_to_on_noreply: bool = False

    @property
    def team_sender_list(self) -> list[str]:
        return [p.strip().lower() for p in self.team_senders.split(",") if p.strip()]

    @property
    def shared_domain_list(self) -> list[str]:
        return [p.strip().lower().lstrip("@") for p in self.shared_email_domains.split(",") if p.strip()]

    @property
    def only_sender_list(self) -> list[str]:
        return [p.strip().lower() for p in self.only_senders.split(",") if p.strip()]

    @property
    def blocked_subject_list(self) -> list[str]:
        return [p.strip().lower() for p in self.blocked_subjects.split(",") if p.strip()]

    @property
    def blocked_sender_list(self) -> list[str]:
        return [p.strip().lower() for p in self.blocked_senders.split(",") if p.strip()]


settings = Settings()
