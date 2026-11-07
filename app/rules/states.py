class Status:
    """Estados possíveis de um e-mail processado pela NOVA."""

    RECEIVED = "RECEIVED"
    IGNORED_SELF = "IGNORED_SELF"
    IGNORED_NOREPLY = "IGNORED_NOREPLY"
    IGNORED_AUTOMATED = "IGNORED_AUTOMATED"
    IGNORED_OLD = "IGNORED_OLD"
    IGNORED_OLD_THREAD = "IGNORED_OLD_THREAD"   # resposta dentro de conversa que a NOVA não iniciou/acompanhou (anterior ao go-live)
    IGNORED_BLOCKED = "IGNORED_BLOCKED"
    IGNORED_TEAM = "IGNORED_TEAM"   # e-mail de alguém da equipe (a NOVA nunca responde; a conversa passa a ser da equipe)
    ALREADY_HANDLED = "ALREADY_HANDLED"   # conversa já validada/encaminhada antes; não responde de novo
    WAITING_DOCUMENT = "WAITING_DOCUMENT"
    CUSTOMER_VALIDATED = "CUSTOMER_VALIDATED"   # CNPJ/CPF encontrado na base de clientes
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"   # CNPJ/CPF válido, mas não é cliente cadastrado
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REPLY_ERROR = "REPLY_ERROR"
    ERROR = "ERROR"

    RETRYABLE = (REPLY_ERROR, ERROR)
    TERMINAL = (
        IGNORED_SELF, IGNORED_NOREPLY, IGNORED_AUTOMATED, IGNORED_OLD, IGNORED_OLD_THREAD, IGNORED_BLOCKED, IGNORED_TEAM,
        CUSTOMER_VALIDATED, HUMAN_REVIEW, ALREADY_HANDLED,
    )
    # Registros que NÃO provam que a NOVA acompanhou a conversa (ver thread_known_to_nova)
    NOT_A_NOVA_THREAD = (IGNORED_OLD, IGNORED_OLD_THREAD, IGNORED_SELF)
