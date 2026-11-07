"""Fluxo da NOVA: recebe um e-mail, filtra, identifica o cliente e monta o pré-atendimento.

Ainda não chama nenhum ERP: a base de clientes é `data/clientes.txt` e o
pré-atendimento fica salvo no banco. O ponto de integração está marcado com
`>>> INTEGRAÇÃO ERP` em `_pipeline` (ver README).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.customers import contacts, groups, names
from app.customers.service import Customer, find_customer, load_aliases, load_customers
from app.database import repository as repo
from app.database.models import EmailRecord
from app.documents.validator import (describe_invalid, display_document, extract_documents,
                                     find_invalid_document, normalize)
from app.email import templates
from app.email.models import IncomingEmail
from app.email.sender import MailGateway
from app.rules import engine
from app.rules.blocklist import load_blocked_senders
from app.rules.engine import Action
from app.rules.states import Status
from app.timeutil import to_utc

log = logging.getLogger("nova.processor")

DUPLICATE = "DUPLICATE"

_RE_PREFIX = re.compile(r"^\s*(re|res)\s*:", re.IGNORECASE)


def referenced_ids(incoming: IncomingEmail) -> list[str]:
    """Message-IDs citados em References e In-Reply-To (se houver)."""
    raw = f"{incoming.headers.get('references', '')} {incoming.headers.get('in-reply-to', '')}"
    return raw.split()


def is_team_sender(address: str, entries: list[str]) -> bool:
    address = (address or "").lower()
    return any(address == e or (e.startswith("@") and address.endswith(e)) for e in entries)


def is_reply(incoming: IncomingEmail) -> bool:
    """O e-mail se apresenta como continuação de uma conversa (cabeçalhos ou 'Re:')."""
    return bool(referenced_ids(incoming)) or bool(_RE_PREFIX.match(incoming.subject or ""))

_IGNORE_STATUS = {
    Action.IGNORE_SELF: Status.IGNORED_SELF,
    Action.IGNORE_NOREPLY: Status.IGNORED_NOREPLY,
    Action.IGNORE_AUTOMATED: Status.IGNORED_AUTOMATED,
    Action.IGNORE_BLOCKED: Status.IGNORED_BLOCKED,
}


class ReplyError(Exception):
    pass


def _shown(raw: str) -> str:
    """Como repetir ao cliente o número que ele digitou: CPF com dígitos ocultos."""
    n = normalize(raw)
    return display_document(n) if len(n) == 11 and n.isdigit() else raw


def _mask(document: str) -> str:
    return f"***{document[3:9]}**" if len(document) == 11 else document


class EmailProcessor:
    def __init__(self, session_factory, mail: MailGateway, settings: Settings,
                 cutoff: datetime | None = None) -> None:
        self.cutoff = cutoff
        self.session_factory = session_factory
        self.mail = mail
        self.settings = settings

    def process(self, incoming: IncomingEmail) -> str:
        with self.session_factory() as db:
            if repo.get_email_by_message_id(db, incoming.message_id):
                log.info("E-mail duplicado ignorado: %s", incoming.message_id)
                return DUPLICATE

            rec = repo.create_email(db, incoming)
            if self.cutoff and to_utc(incoming.received_at) < to_utc(self.cutoff):
                repo.add_event(db, rec, "IGNORED_OLD", "recebido antes do corte (PROCESS_FROM)")
                repo.set_status(db, rec, Status.IGNORED_OLD)
                return rec.status

            if self.settings.ignore_unknown_replies and is_reply(incoming):
                known_thread = repo.thread_known_to_nova(
                    db, exclude_id=rec.id, conversation_id=rec.conversation_id,
                    reference_ids=referenced_ids(incoming), since=self.cutoff)

                # Alguns clientes de e-mail não preservam a raiz/References da
                # conversa. Se há uma solicitação de documento em aberto para o
                # mesmo remetente e assunto, recuperar a conversa pendente antes
                # de classificá-la como antiga. Isso não valida CNPJ: a mensagem
                # segue pelo pipeline normal e o documento ainda precisa passar
                # pela validação matemática e existir em clientes.txt.
                if not known_thread:
                    pending = repo.find_pending_reply_thread(
                        db, exclude_id=rec.id, from_email=rec.from_email,
                        subject=rec.subject, since=self.cutoff)
                    if pending is not None:
                        rec.conversation_id = pending.conversation_id
                        db.commit()
                        repo.add_event(
                            db, rec, "THREAD_RECOVERED_BY_PENDING_DOCUMENT",
                            "resposta ligada à solicitação pendente pelo remetente e assunto normalizado",
                        )
                        known_thread = True

                if not known_thread:
                    repo.add_event(db, rec, "IGNORED_OLD_THREAD",
                                   "resposta em conversa que a NOVA não acompanhou (anterior ao go-live)")
                    repo.set_status(db, rec, Status.IGNORED_OLD_THREAD)
                    return rec.status

            # Quem é da equipe nunca recebe resposta da NOVA; e a conversa passa a ser da equipe.
            if is_team_sender(rec.from_email, self.settings.team_sender_list):
                repo.add_event(db, rec, "IGNORED_TEAM", "e-mail de alguém da equipe")
                repo.set_status(db, rec, Status.IGNORED_TEAM)
                return rec.status

            if repo.conversation_taken_by_team(db, rec.conversation_id, rec.id):
                repo.add_event(db, rec, "ALREADY_HANDLED", "alguém da equipe já assumiu esta conversa")
                repo.set_status(db, rec, Status.ALREADY_HANDLED)
                return rec.status

            if repo.conversation_already_handled(db, rec.conversation_id):
                repo.add_event(db, rec, "ALREADY_HANDLED", "conversa já validada/encaminhada antes")
                repo.set_status(db, rec, Status.ALREADY_HANDLED)
                return rec.status

            check = engine.pre_check(
                incoming,
                nova_email=self.settings.nova_email,
                extra_blocked=self.settings.blocked_sender_list + load_blocked_senders(),
                allow_reply_to_on_noreply=self.settings.allow_reply_to_on_noreply,
                blocked_subjects=self.settings.blocked_subject_list,
                only_senders=self.settings.only_sender_list,
            )
            if check.action is not Action.PROCEED:
                repo.add_event(db, rec, check.action.value, check.reason)
                repo.set_status(db, rec, _IGNORE_STATUS[check.action])
                return rec.status

            rec.reply_address = check.reply_address
            db.commit()
            repo.add_event(db, rec, "RECEIVED", f"de {rec.from_email}")
            self._run(db, rec)
            return rec.status

    def _run(self, db: Session, rec: EmailRecord) -> None:
        try:
            self._pipeline(db, rec)
        except ReplyError as exc:
            # Falhou especificamente ao ENVIAR a resposta (ex.: SMTP fora do
            # ar) -- a decisão (CNPJ validado, pré-atendimento criado, etc.)
            # já pode ter sido tomada e salva antes deste ponto. Status
            # próprio (REPLY_ERROR) para não se misturar com falhas de
            # lógica/parsing (Status.ERROR), embora `retry_pending()`
            # reprocesse os dois (Status.RETRYABLE).
            log.exception("Falha ao enviar resposta para o e-mail %s", rec.message_id)
            db.rollback()
            rec.retry_count = (rec.retry_count or 0) + 1
            rec.last_error = str(exc)[:2000]
            db.commit()
            repo.add_event(db, rec, "REPLY_ERROR", str(exc)[:500])
            repo.set_status(db, rec, Status.REPLY_ERROR)
        except Exception as exc:  # noqa: BLE001
            log.exception("Erro inesperado no e-mail %s", rec.message_id)
            db.rollback()
            rec.retry_count = (rec.retry_count or 0) + 1
            rec.last_error = str(exc)[:2000]
            db.commit()
            repo.add_event(db, rec, "ERROR", str(exc)[:500])
            repo.set_status(db, rec, Status.ERROR)

    def _pipeline(self, db: Session, rec: EmailRecord) -> None:
        text = f"{rec.subject}\n{rec.body}"
        docs = extract_documents(text)

        # 1º) E-mail (ou domínio) já salvo/vinculado a um cliente: reconhece por ele e
        #     NÃO pede o CNPJ/CPF. Se o e-mail não estiver salvo, segue para o 2º passo.
        linked = self._customer_from_contact(db, rec)
        # Um documento explicitamente informado, mas inválido, não deve ser
        # ignorado só porque o remetente já está vinculado a um cliente.
        # Nesse caso, solicite a correção; o vínculo só é usado quando não há
        # documento inválido no texto.
        bad = find_invalid_document(text) if not docs else None
        if linked is not None and not docs and bad:
            repo.add_event(db, rec, "DOCUMENT_INVALID",
                           "número informado não é um CNPJ/CPF válido; vínculo de contato não utilizado")
            self._ask_document(db, rec, invalid=True, informado=bad)
            return

        if linked is not None:
            if docs and not any(normalize(d.number) == normalize(linked.document) for d in docs):
                repo.add_event(db, rec, "DOCUMENT_IGNORED_LINK_USED",
                               "e-mail já vinculado a um cliente; CNPJ/CPF do texto não foi usado")
            elif not docs and bad:
                repo.add_event(db, rec, "DOCUMENT_IGNORED_LINK_USED",
                               "número com formato de CNPJ/CPF inválido no texto; usado o vínculo do contato")
            rec.cnpj_cpf = linked.document
            db.commit()
            self._confirm_customer(db, rec, linked, via_link=True)
            return

        # 2º) E-mail não reconhecido: valida pelo CNPJ/CPF informado (ou pede, se não veio).
        document = None
        if docs:
            document, matched = self._select_document(docs)
            if len(docs) > 1:
                msg = (f"{len(docs)} documentos no texto; usando o cadastrado ({_mask(document)})"
                       if matched else
                       f"{len(docs)} documentos no texto, nenhum cadastrado; usando o 1º ({_mask(document)})")
                repo.add_event(db, rec, "MULTIPLE_DOCUMENTS_FOUND", msg)

        if not document:
            bad = find_invalid_document(text)  # tem número, mas está incorreto (dígito ou quantidade)
            # 3º) Sem e-mail/domínio reconhecido e sem CNPJ/CPF: tenta pelo NOME que o cliente citou
            #     (assinatura/apresentação) e confere se existe na base, vinculado a um CNPJ/CPF.
            #     Só se não houver número "quebrado" no texto (quem digitou o CNPJ errado recebe o aviso).
            if not bad:
                named = self._customer_from_name(db, rec)
                if named is not None:
                    customer, citado = named
                    rec.cnpj_cpf = customer.document
                    db.commit()
                    self._confirm_customer(db, rec, customer, via_link=False, name_note=citado)
                    return
            # 4º) Nada achou: aí sim pede o CNPJ/CPF.
            self._ask_document(db, rec, invalid=bool(bad), informado=bad or "")
            return

        rec.cnpj_cpf = document
        db.commit()
        repo.add_event(db, rec, "DOCUMENT_FOUND", _mask(document))

        # >>> INTEGRAÇÃO ERP: trocar find_customer() por uma consulta real ao ERP
        # e abrir o chamado antes da confirmação ao cliente.
        customer = find_customer(document)
        if customer is None:
            repo.add_event(db, rec, "CUSTOMER_NOT_FOUND", _mask(document))
            self._reply(rec, templates.customer_not_found(display_document(document)))

            already_notified = repo.count_not_found_notifications(db, rec.from_email, document)
            if already_notified < self.settings.max_not_found_notifications:
                self._notify_team(*templates.team_customer_not_found(
                    document=_mask(document), sender=rec.reply_address or rec.from_email,
                    subject=rec.subject, body=rec.body))
                repo.add_event(db, rec, "TEAM_NOTIFIED_NOT_FOUND", _mask(document))
            else:
                repo.add_event(db, rec, "TEAM_NOTIFICATION_SKIPPED",
                               f"equipe já avisada {already_notified}x sobre este remetente+documento")

            repo.set_status(db, rec, Status.CUSTOMER_NOT_FOUND)
            repo.set_status(db, rec, Status.HUMAN_REVIEW)
            return

        self._confirm_customer(db, rec, customer, via_link=False)

    def _customer_from_contact(self, db: Session, rec: EmailRecord) -> Customer | None:
        """Cliente já conhecido pelo e-mail/domínio de quem escreveu, ou None (aí a NOVA pede o CNPJ/CPF)."""
        # Regra de grupo: se alguém do grupo (data/grupos.txt) está no De OU no Cc, o e-mail é
        # cadastrado direto nesse cliente/grupo, antes de qualquer outro vínculo (e mesmo que
        # o remetente seja de outra empresa ou o texto traga outro CNPJ).
        rule = groups.resolve_group(rec.from_email, (rec.cc_raw or "").split(","))
        if rule is not None:
            repo.add_event(db, rec, "GROUP_RULE_USED",
                           f"{rule.matched} ({rule.where}) -> {rule.customer.name}")
            return rule.customer
        if not self.settings.contact_links_enabled:
            return None
        # A identidade é o remetente real (From), não o Reply-To usado apenas
        # para direcionar respostas. Assim, um endereço Reply-To conhecido não
        # permite que um remetente novo pule a conferência do CNPJ/CPF.
        match = contacts.resolve(
            db,
            rec.from_email,
            self.settings.shared_domain_list,
            allow_auto_domain=self.settings.link_domain_auto,
        )
        if match.stale:
            repo.add_event(db, rec, "CONTACT_LINK_STALE",
                           f"{match.stale} vínculo(s) apontam para cliente que não está mais na base")
        if match.ambiguous:
            repo.add_event(db, rec, "CONTACT_LINK_AMBIGUOUS",
                           f"{match.matched} está vinculado a {len(match.ambiguous)} clientes; pedindo o CNPJ/CPF")
            return None
        if match.customer is None:
            return None
        repo.add_event(db, rec, "CONTACT_LINK_USED",
                       f"reconhecido por {match.via} ({match.matched}) -> {match.customer.name}")
        return match.customer

    def _customer_from_name(self, db: Session, rec: EmailRecord) -> tuple[Customer, str] | None:
        """Cliente cadastrado cujo NOME aparece na assinatura/apresentação do e-mail.
        Devolve (cliente, trecho que o cliente escreveu) ou None (aí a NOVA pede o CNPJ/CPF).
        Nome ambíguo (dois cadastros empatados) não é chutado."""
        if not self.settings.name_match_enabled:
            return None
        lines = names.candidate_lines(rec.subject or "", rec.body or "", rec.from_name or "")
        match = names.match_customer(load_customers(), lines, load_aliases())
        if match.ambiguous:
            repo.add_event(db, rec, "CUSTOMER_NAME_AMBIGUOUS",
                           f"nome citado casa com {len(match.ambiguous)} cadastros; pedindo o CNPJ/CPF")
            return None
        if not match.found:
            return None
        customer = find_customer(match.document)
        if customer is None:
            return None
        repo.add_event(db, rec, "CUSTOMER_MATCHED_BY_NAME",
                       f"cadastro '{match.name}' reconhecido pelo nome '{match.matched_as}' citado no e-mail")
        return customer, match.matched_as

    def _confirm_customer(self, db: Session, rec: EmailRecord, customer: Customer, *, via_link: bool,
                          name_note: str = "") -> None:
        """Cliente identificado (pelo CNPJ/CPF do e-mail ou pelo vínculo do contato):
        cria o pré-atendimento (juntando mensagens anteriores da conversa que esperavam o
        documento), confirma ao cliente e, se foi pelo CNPJ/CPF, aprende o vínculo do contato."""
        repo.add_event(db, rec, "CUSTOMER_VALIDATED", customer.name)
        if repo.had_human_review(db, rec.conversation_id, exclude_id=rec.id):
            # O cliente demorou/errou antes e a conversa chegou a ser escalada
            # (HUMAN_REVIEW), mas se corrigiu depois. Isso é esperado e bom —
            # só registra, não impede a validação (ver conversation_already_handled).
            repo.add_event(db, rec, "REOPENED_AFTER_HUMAN_REVIEW",
                            "cliente se corrigiu depois de uma escalada anterior nesta conversa")

        waiting = repo.find_waiting_documents(db, rec.conversation_id, exclude_id=rec.id)
        observacoes = self._build_observacoes(rec, waiting)
        if name_note:
            observacoes = (f"[CONFIRMAR CLIENTE] Identificado apenas pelo nome citado no e-mail "
                           f"('{name_note}' -> cadastro '{customer.name}'), sem CNPJ/CPF e sem e-mail "
                           f"vinculado. Conferir se é mesmo este cliente (e a filial) ao assumir.\n\n"
                           + observacoes)
        repo.create_pre_atendimento(
            db,
            email_id=rec.id,
            cliente_documento=customer.document,
            cliente_nome=customer.name,
            contato_nome=rec.from_name or "",
            contato_email=rec.reply_address or rec.from_email,
            tipo_atendimento=self.settings.ticket_type,
            canal=self.settings.ticket_channel,
            tipo_acesso=self.settings.ticket_access_type,
            observacoes=observacoes,
        )
        repo.add_event(db, rec, "PRE_ATENDIMENTO_CRIADO", customer.name)

        # Reconhecido só pelo nome: NÃO grava vínculo de e-mail (qualquer um pode escrever "Omega" na
        # assinatura). O vínculo só nasce depois de uma conferência por CNPJ/CPF.
        if not via_link and not name_note and self.settings.contact_links_enabled:
            self._learn_contacts(db, rec, customer)

        for w in waiting:  # a solicitação original foi absorvida por este pré-atendimento
            repo.set_status(db, w, Status.CUSTOMER_VALIDATED)

        if name_note:
            self._reply(rec, templates.customer_identified_by_name(customer.name))
        else:
            self._reply(rec, templates.customer_validated(
                nome=customer.name, documento="" if via_link else display_document(customer.document),
                via_link=via_link))
        repo.add_event(db, rec, "CUSTOMER_NOTIFIED", "atendimento confirmado")
        repo.set_status(db, rec, Status.CUSTOMER_VALIDATED)

    def _learn_contacts(self, db: Session, rec: EmailRecord, customer: Customer) -> None:
        """Vincula apenas o remetente que efetivamente informou o CNPJ/CPF validado.

        Outros remetentes anteriores na mesma conversa não ficam vinculados
        automaticamente, pois a mensagem de uma pessoa não comprova que outro
        endereço pertence ao mesmo cliente. O Reply-To continua sendo usado para
        direcionar respostas, mas não como identidade do contato.
        """
        address = (rec.from_email or "").lower()
        if not address:
            return
        for event, value in contacts.learn(
                db, address, customer.document, link_domain=self.settings.link_domain_auto,
                shared_extra=self.settings.shared_domain_list, email_id=rec.id):
            repo.add_event(db, rec, event, f"{value} -> {customer.name}")

    def _ask_document(self, db: Session, rec: EmailRecord, invalid: bool = False, informado: str = "") -> None:
        # "Pedido" e "número incorreto" têm contadores separados: quem digitou o CNPJ errado
        # sempre recebe o aviso de que está incorreto (até o limite de avisos), mesmo que
        # a conversa já tenha tido pedidos de documento antes.
        asked = repo.count_document_requests(
            db, rec.conversation_id, "DOCUMENT_INVALID" if invalid else "DOCUMENT_REQUESTED")
        if asked >= self.settings.max_document_requests:
            # O cliente também precisa saber que acabaram as tentativas (uma única vez por conversa).
            if repo.count_document_requests(db, rec.conversation_id, "DOCUMENT_LIMIT") == 0:
                self._reply(rec, templates.document_limit(_shown(informado) if informado else ""))
            repo.add_event(db, rec, "DOCUMENT_LIMIT", f"{asked} solicitações sem resposta válida")
            repo.set_status(db, rec, Status.HUMAN_REVIEW)
            self._notify_team(*templates.team_review(
                reason="Cliente não informou um CNPJ/CPF válido após as solicitações da NOVA.",
                sender=rec.reply_address or rec.from_email, subject=rec.subject, body=rec.body))
            return
        if invalid:
            self._reply(rec, templates.document_invalid(_shown(informado), describe_invalid(informado) if informado else ""))
            repo.add_event(db, rec, "DOCUMENT_INVALID", "número informado não é um CNPJ/CPF válido")
        else:
            self._reply(rec, templates.request_document())
            repo.add_event(db, rec, "DOCUMENT_REQUESTED", "")
        repo.set_status(db, rec, Status.WAITING_DOCUMENT)

    @staticmethod
    def _select_document(docs: list) -> tuple[str, bool]:
        """Se a mensagem trouxer mais de um CNPJ/CPF (ex.: um é do cliente e o
        outro aparece num boleto anexado ou citado no corpo), usa o que estiver
        cadastrado na base (data/clientes.txt). Se nenhum estiver cadastrado,
        usa o primeiro que aparece no texto — assim o CUSTOMER_NOT_FOUND ainda
        aponta um documento concreto para a equipe conferir. Devolve também se
        o escolhido bateu com algum cadastro (só para a mensagem de log)."""
        for doc in docs:
            if find_customer(doc.number) is not None:
                return doc.number, True
        return docs[0].number, False

    def retry_pending(self) -> int:
        """Reprocessa e-mails que falharam antes (status ERROR, ex.: Gmail
        fora do ar na hora de responder) e ainda não esgotaram
        `max_retries`. Sem isso, uma falha passageira deixava o e-mail
        travado em ERROR para sempre, exigindo reprocessar manualmente.
        Chamado pelo worker a cada ciclo. create_pre_atendimento() é
        idempotente, então reprocessar um e-mail que já tinha chegado a criar
        o pré-atendimento (e falhou depois, ex.: ao enviar a confirmação) não
        duplica o registro."""
        count = 0
        with self.session_factory() as db:
            for rec in repo.list_retryable(db, self.settings.max_retries):
                repo.add_event(db, rec, "RETRY_ATTEMPT",
                                f"tentativa {rec.retry_count + 1}/{self.settings.max_retries}")
                self._run(db, rec)
                count += 1
        return count

    def escalate_stale_waiting(self) -> int:
        """Varre conversas em WAITING_DOCUMENT que passaram de
        `stale_waiting_hours` sem o cliente responder NADA (nem certo, nem
        errado) e escala para a equipe. Sem isso, um cliente que simplesmente
        some deixa a conversa esperando para sempre, porque o resto do fluxo só
        reage quando uma nova mensagem chega. Chamado pelo worker a cada ciclo."""
        hours = self.settings.stale_waiting_hours
        if not hours:
            return 0
        limite = datetime.now(timezone.utc) - timedelta(hours=hours)
        count = 0
        with self.session_factory() as db:
            for rec in repo.list_stale_waiting(db, limite):
                repo.add_event(db, rec, "DOCUMENT_TIMEOUT", f"sem resposta há mais de {hours}h")
                repo.set_status(db, rec, Status.HUMAN_REVIEW)
                self._notify_team(*templates.team_review(
                    reason=f"Cliente não respondeu ao pedido de CNPJ/CPF em {hours}h.",
                    sender=rec.reply_address or rec.from_email, subject=rec.subject, body=rec.body))
                count += 1
        return count

    @staticmethod
    def _build_observacoes(rec: EmailRecord, waiting: list[EmailRecord]) -> str:
        """Observações do pré-atendimento: junta a solicitação original (se o
        CNPJ veio numa resposta separada) com a mensagem que trouxe o documento.
        Inclui o assunto quando ele agrega algo além do corpo (útil quando o
        corpo é só "CNPJ: ..." e o assunto é que descreve o problema)."""
        def describe(r: EmailRecord) -> str:
            body = r.body.strip()
            subject = (r.subject or "").strip()
            if subject and subject.lower() not in body.lower():
                return f"Assunto: {subject}\n{body}".strip()
            return body

        if waiting:
            partes = [describe(w) for w in waiting]
            partes.append(describe(rec))
            return "\n\n".join(p for p in partes if p)
        return describe(rec)

    def _reply(self, rec: EmailRecord, body: str) -> None:
        # References = a cadeia que este e-mail já trazia + o Message-ID dele
        # mesmo (é o que o RFC 5322 pede). Sem isso, cada resposta da NOVA
        # "esquece" a raiz da conversa e, depois de 2-3 idas e vindas, o
        # cliente respondendo de novo parece uma conversa nova pra NOVA — e ela
        # volta a pedir o CNPJ mesmo já validado.
        references = f"{rec.references_raw} {rec.message_id}".strip() if rec.references_raw else rec.message_id
        try:
            self.mail.send_reply(
                graph_id=rec.graph_id,
                from_email=rec.from_email,
                to=rec.reply_address or rec.from_email,
                subject=templates.re_subject(rec.subject),
                body=body,
                references=references,
            )
        except Exception as exc:  # noqa: BLE001
            raise ReplyError(str(exc)) from exc

    def _notify_team(self, subject: str, body: str) -> None:
        to = self.settings.team_email
        if not to:
            log.warning("TEAM_EMAIL não configurado; aviso à equipe apenas no log: %s", subject)
            return
        try:
            self.mail.send_mail(to=to, subject=subject, body=body)
        except Exception:  # noqa: BLE001
            log.exception("Falha ao avisar a equipe")
