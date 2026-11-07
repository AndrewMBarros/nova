# NOVA - Guia de teste gratuito com Gmail (IMAP/SMTP)

Este caminho não usa Azure, Entra ID nem Microsoft 365. Custo: zero. O que muda no projeto é só a camada de e-mail (`MAIL_MODE=imap`); regras, processador, banco e ERP são os mesmos.

## 1. Crie a caixa da NOVA
Crie uma conta Gmail **exclusiva** para a NOVA (ex.: `nova.teste.suaempresa@gmail.com`). Não use seu Gmail pessoal: no modo `imap`, a NOVA responde de verdade aos e-mails que chegarem.

## 2. Ative a verificação em duas etapas
1. Acesse https://myaccount.google.com/security com a conta da NOVA.
2. Ative a **Verificação em duas etapas** (celular ou app autenticador).

Sem isso o Google não mostra a opção de senha de aplicativo. Não ative o "Programa de Proteção Avançada", que desativa senhas de aplicativo.

## 3. Gere a senha de aplicativo
1. Acesse https://myaccount.google.com/apppasswords (se der 404, procure "Senhas de app" na busca das configurações da conta).
2. Dê um nome (ex.: `NOVA`) e clique em **Criar**.
3. **Copie o código de 16 caracteres na hora**: ele aparece uma única vez. Os espaços não importam.
4. Se você trocar a senha principal da conta, a senha de aplicativo pode ser revogada. Gere outra.

O IMAP já vem ativado por padrão nas contas Google desde janeiro de 2025. Se algo falhar, confira em Gmail > Configurações > Ver todas as configurações > Encaminhamento e POP/IMAP.

## 4. Configure o `.env`
```
NOVA_EMAIL=nova.teste.suaempresa@gmail.com
MAIL_USERNAME=nova.teste.suaempresa@gmail.com
MAIL_PASSWORD=<senha de aplicativo de 16 caracteres>
MAIL_MODE=imap_readonly
```
(`IMAP_HOST`, `SMTP_HOST` e portas já vêm configurados para o Gmail.) O `.env` nunca vai para o Git.

## 5. Teste a conexão
```
python -m app.imap_check
```
Deve mostrar "Conectado por IMAP!" e a quantidade de não lidos. Para testar também o envio:
```
python -m app.imap_check --send-test seu.outro.email@exemplo.com
```

## 6. Rode a NOVA com e-mails reais
1. De **outro** e-mail seu, envie para a caixa da NOVA uma mensagem sem CNPJ (ex.: "Estamos sem internet").
2. `python -m app.worker --once` com `MAIL_MODE=imap_readonly`: a NOVA lê, decide e **só registra** a resposta no log. Nada é enviado.
3. Confira o resultado em `GET /dev/emails` (se a API estiver rodando) ou no log.
4. Quando estiver confiante, troque para `MAIL_MODE=imap` e repita. Agora a NOVA responde de verdade. Responda o e-mail dela com `CNPJ: 12.345.678/0001-95` (cliente fictício de `data/clientes.txt`) e veja o pré-atendimento ser criado (`GET /dev/pre-atendimentos`).
5. Sem `--once`, o worker fica rodando e consulta a caixa a cada `POLL_INTERVAL_SECONDS`.

Como as respostas mantêm a conversa (cabeçalhos In-Reply-To/References), a resposta do cliente com o CNPJ cai na mesma conversa do pedido original.

## 6b. O que a NOVA lê
Por data, a partir de `PROCESS_FROM` (ou do momento da 1ª execução), e não por "não lido". E-mails anteriores ao corte
nunca são respondidos. Por padrão ela não marca como lido (`MARK_READ=false`); se quiser esse comportamento no teste,
ponha `MARK_READ=true`. No IMAP o filtro do servidor é por dia; o corte exato é feito pela NOVA.

## 6c. Piloto seguro na lista do suporte
Quando o Gmail da NOVA entrar na lista, ele receberá **e-mails reais de clientes**. Para não responder a ninguém por engano:
1. Comece com `MAIL_MODE=imap_readonly` por um ou dois dias e leia o log: veja o que a NOVA *teria* respondido.
2. Ponha `PROCESS_FROM` com a data/hora de início do piloto (ela nunca toca no histórico).
3. Use `ONLY_SENDERS` com os seus endereços de teste (e, se quiser, `@suaempresa.com.br`). Enquanto estiver preenchido,
   a NOVA ignora todos os outros remetentes, inclusive clientes reais.
4. Ignore alertas automáticos de outros sistemas com `BLOCKED_SUBJECTS` (ex.: `Relatório diário,Alerta de monitoramento`).
5. Só quando tudo estiver correto: `MAIL_MODE=imap` e, no final, esvazie `ONLY_SENDERS` para liberar a todos.

## 7. Limites e cuidados
- O Gmail pessoal limita o envio a cerca de 500 destinatários por dia: sobra para testes.
- A senha de aplicativo não expira e dá acesso por IMAP/SMTP à caixa: guarde no `.env`, nunca no código ou no chat.
- As mensagens da NOVA saem com o cabeçalho `Auto-Submitted`, o que evita que outros robôs (e a própria NOVA) respondam a elas em laço.
- Envie os testes apenas a partir de endereços seus.

## 8. E na empresa?
Este caminho serve para validar o projeto de graça. Se o e-mail corporativo da empresa for Microsoft 365 (Exchange Online), a NOVA precisará usar o Microsoft Graph, porque a autenticação básica por IMAP/SMTP está sendo desativada nesse serviço. Nesse caso, o TI registra o aplicativo no diretório (Entra ID) que a empresa já tem. Isso é configuração, não compra. Se a empresa usar outro provedor com IMAP, este mesmo modo pode servir. Só a camada de e-mail muda; o restante do projeto continua igual.

## 9. Problemas comuns
| Sintoma | Causa provável |
|---|---|
| `AUTHENTICATIONFAILED` / `Application-specific password required` | Usou a senha normal, ou a verificação em duas etapas está desligada |
| Página de senhas de aplicativo não abre | Falta a verificação em duas etapas, ou a conta está na Proteção Avançada |
| `SMTPAuthenticationError 535` | Senha de aplicativo errada/revogada |
| Conectou, mas 0 não lidos | Os e-mails já estão como lidos; envie um novo |
| E-mail da NOVA cai no spam do destinatário | Comum em contas novas; marque como "não é spam" durante os testes |
