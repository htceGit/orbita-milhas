# Operação do Órbita

## Primeiro acesso

1. Abra o portal, escolha **Criar conta** e use o e-mail reservado para a administração.
2. Confirme o cadastro pelo e-mail, no mesmo navegador em que iniciou o cadastro (fluxo PKCE).
3. Entre novamente. A conta confirmada recebe Administração e Pro. Outros usuários recebem Free.
4. Em Administração, ajuste aeroportos, destinos, permanência, conexões e orçamento de consultas. As alterações entram na próxima rodada.

Uma reserva administrativa só pode ser consumida uma vez. Novos administradores devem ser promovidos pelo operador do banco; o formulário de usuários altera apenas Free/Pro, validade do Pro e suspensão.

## URLs de autenticação

Em **Authentication → URL Configuration** no Supabase:

- Site URL: `https://htcegit.github.io/orbita-milhas/`
- Redirect URLs: `https://htcegit.github.io/orbita-milhas/`

Use a URL exata, incluindo o caminho do repositório. Para testar login local, adicione o endereço local explicitamente; não adicione curingas amplos ao ambiente comercial.

## E-mails transacionais

Configure um provedor SMTP em **Authentication → Emails → SMTP Settings**. O serviço padrão Supabase não substitui um provedor comercial e pode restringir envios a endereços da equipe. Defina domínio/remetente, autentique o domínio e valide confirmação de conta e recuperação de senha com um destinatário externo.

Não desative a confirmação para contornar limites de e-mail: ela protege a reserva do administrador e a posse dos endereços cadastrados. Nenhuma integração SMTP paga foi contratada por este projeto.

## Execuções

Em **GitHub → Actions → Radar Órbita · a cada 4 horas → Run workflow**, faça uma execução manual quando precisar. Não há chave Supabase para copiar: a função já aceita apenas a identidade OIDC desse workflow na branch principal.

O cron é aproximado e deve ser acompanhado. Falhas de parsing/bloqueios do Google aparecem como falhas de consulta. O coletor próprio abre um navegador isolado para descobrir datas no calendário. Em erros, preserva os preços obtidos e registra captura parcial. Três falhas consecutivas de calendário ou um bloqueio explícito acionam a fila detalhada pelo restante da rodada. Oito falhas consecutivas da busca detalhada interrompem a rodada. O campo opcional `query_limit` na execução manual limita as chamadas para testes; zero utiliza o orçamento do portal. Um timeout do job ou cancelamento forçado pode deixar uma execução como `running`; o cursor continua salvo. Confira o Actions e não trate esse registro como uma rodada concluída.

Contas suspensas não contribuem com radares para o motor. Ao expirar Pro, somente os três radares mais antigos são pesquisados até que o usuário reorganize as rotas. Pausar o motor não interrompe imediatamente uma rodada que já começou; a opção é lida no início de cada execução.

## Evolução para assinatura

1. Escolher um provedor de pagamentos, preços e regras de cancelamento.
2. Implementar checkout no servidor e webhook com assinatura validada.
3. Deduplicar pelo ID do evento em `private.billing_events`.
4. Alterar `profiles.plan` e `pro_until` somente no backend.
5. Testar atraso de pagamento, reembolso, expiração, renovação e tentativa de promoção pelo navegador.

O botão de interesse em Pro registra apenas o interesse no banco. Ele não envia mensagens nem contrata serviço.

## Proteção e dados

Migrations estão em `supabase/migrations/`. Os testes em `tests/database.mjs` executam Postgres em memória e verificam isolamento entre usuários, limites, privilégios e suspensão. Para novas mudanças, aplique migrations por CLI/MCP, rode os testes e revise os advisors do Supabase.

O histórico de preços tem retenção de 90 dias. Para exclusão de dados pessoais, o operador deve excluir a conta pelo Supabase Auth; chaves estrangeiras removem perfil, favoritos, preferências e radares. Faça revogação de sessões antes da exclusão quando houver exigência de bloqueio imediato.

O GitHub Pages publica o código estático. O repositório é público; dados dos usuários e eventos privados ficam no Supabase. O catálogo e as ofertas não têm acesso anônimo pelo banco.

## API de calendário

A Administração inclui **Calendário próprio**: solicite uma rota, datas de saída e permanência; acompanhe a fila e veja os menores preços capturados. Pedidos novos aguardam a próxima rodada do motor. O painel se atualiza automaticamente a cada minuto sem substituir o formulário de configurações. A prévia de calendário ainda não confirma companhia nem disponibilidade de milhas.

O worker processa pedidos administrativos antes da descoberta automática, respeitando o mesmo orçamento global. Uma única captura por usuário pode permanecer na fila ou em processamento. Execuções interrompidas são detectadas na próxima rodada e marcadas como falhas. Os dados brutos de sessão, cookies e headers do Google não são armazenados. Preços completos são comprimidos; o navegador recebe apenas os resumos necessários ou os dados pedidos à API autenticada.

Leia [API_CALENDARIO.md](API_CALENDARIO.md) para contratos, autenticação, execução local, Docker e testes.
