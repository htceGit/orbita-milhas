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

Em **GitHub → Actions → Radar Órbita · sessões com pausa de 15 minutos → Run workflow**, faça uma execução manual quando precisar. Não há chave Supabase para copiar: a função já aceita apenas a identidade OIDC desse workflow na branch principal.

A continuidade usa uma espera nativa de 15 minutos no ambiente `scanner-pause-15m`; ao liberar o job, ele solicita outra execução pelo próprio GitHub. O cron é uma reserva e pode atrasar. Falhas de parsing/bloqueios do Google aparecem como falhas de consulta. O coletor próprio abre um navegador isolado para descobrir datas no calendário. Em erros, preserva os preços obtidos e registra captura parcial. Três falhas consecutivas de calendário acionam a fila detalhada pelo restante da rodada. Bloqueios explícitos (403, 429 ou verificação humana) encerram a sessão, inclusive em capturas solicitadas pela administração. Oito falhas consecutivas da busca detalhada interrompem a rodada. O campo opcional `query_limit` na execução manual limita as chamadas para testes; zero utiliza o orçamento do portal. Um timeout do job ou cancelamento forçado pode deixar uma execução como `running`; o cursor continua salvo. A próxima verificação reconcilia o registro quando o GitHub confirma o término da execução correspondente; os contadores ficam limitados ao último progresso salvo. Sem essa confirmação, o gate mantém o bloqueio conservador.

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

## Ritmo das sessões

O motor seleciona até dois detalhes por origem/destino/permanência e tem teto padrão de 1.000 chamadas por sessão. O workflow verifica a pausa antes de instalar dependências: sessões não se sobrepõem, e outra só é liberada após pelo menos 15 minutos do término da última. Após a espera programada, a próxima execução depende também da fila de runners do GitHub. Falhas repetidas continuam interrompendo a captura.

Aumentar a frequência exige acompanhar uso real de Edge Functions, tamanho do banco e tráfego no painel Supabase. O Free inclui 500 mil invocações de Edge Functions/mês, 500 MB de banco e 5 GB de egress; isso não garante que qualquer frequência de busca caiba gratuitamente. Não foi contratado plano pago nem serviço adicional. Ver https://supabase.com/pricing.

## Monitor de sessões

Abra **Administração → Monitor de sessões**. O painel consulta o progresso a cada 15 segundos enquanto estiver visível. Permite escolher entre as 12 sessões recentes, acompanhar a mais nova, filtrar falhas e abrir a execução correspondente no Actions. Atualizações não substituem os formulários da administração.

O consumo compara chamadas efetivamente tentadas com o teto daquela sessão, inclusive o limite manual de teste. A cobertura representa pares únicos origem/destino/ida/volta com preço de calendário capturado dentro da matriz configurada. Preços brutos, datas detalhadas concluídas, tentativas, tarifas salvas, consultas vazias e recuperações aparecem separadamente. Sessões anteriores à implantação não possuem a causa original nem cobertura única retroativa.

O worker publica sinais e salva o cursor em intervalos de aproximadamente 15 segundos, além das mudanças de etapa. Durante uma resposta demorada, o sinal pode ficar temporariamente antigo; após dois minutos o painel avisa e o link do Actions permite conferir a execução. A próxima verificação tenta reconciliar registros sem encerramento com a execução correspondente no GitHub. Sem confirmação, o bloqueio é preservado.

A consulta detalhada tem timeout de transporte de 25 segundos e limite externo de 40 segundos. Falhas transitórias podem receber uma única nova tentativa após três segundos, se houver orçamento além da reserva para as demais datas selecionadas. Cada tentativa consome uma chamada. Erros de interpretação não são repetidos automaticamente; bloqueios encerram a sessão. Uma falha recuperada permanece no contador de falhas registradas, sem tornar por si só a sessão parcial. Esse contador inclui falhas finais de captura de calendário, tentativas detalhadas com erro e falhas de infraestrutura. Repetições e recuperações se referem às consultas detalhadas.

Eventos detalhados têm leitura exclusiva de administradores ativos e retenção de sete dias, removidos ao final das rodadas. Mensagens são limitadas e sanitizadas: não se guardam HTML, cookies, cabeçalhos ou credenciais. Resumos permanecem no histórico de sessões. Confira [DIAGNOSTICO_DO_MOTOR.md](DIAGNOSTICO_DO_MOTOR.md) para evidências e próximos aprimoramentos.

## Continuidade automática

O workflow inclui o job **Próxima sessão após pausa de 15 minutos**. O ambiente `scanner-pause-15m` tem `wait_timer=15`, sem revisores, restrito à branch `main`. Durante a espera, nenhum runner fica ativo. O job verifica a existência dessa regra antes de usar a identidade temporária do GitHub para solicitar a próxima execução com `query_limit=0`, `mode=scan` e `trigger_source=continuation`. Uma configuração sem a espera correta bloqueia o disparo. A concorrência mantém no máximo um workflow ativo e um pendente.

Em **Run workflow**, `mode=scan` executa e mantém a continuidade; `mode=once` executa uma única rodada; `mode=arm` apenas reativa a espera, sem pesquisar imediatamente. Limites de teste maiores que zero não iniciam uma sequência contínua. Falhas do motor ainda permitem a próxima tentativa após a pausa; cancelar o workflow interrompe sua continuidade. O cron de reserva permanece habilitado. Para parar apenas as consultas, pause o motor no portal; para desativar toda a rotina, desabilite o workflow e cancele a execução pendente no Actions.

O histórico apresenta **requisições**, **preços** e **varreduras completas/solicitadas** separadamente, além da origem e do teto efetivo de cada sessão. Uma requisição não representa seis meses completos; falhas e repetições entram nesse contador. Uma varredura completa corresponde a uma rota e permanência em todo o intervalo solicitado. Os campos novos não são inferidos retroativamente para sessões antigas.

O projeto está em repositório público. A disponibilidade gratuita do wait timer deve ser reavaliada antes de torná-lo privado. A rotina não usa token pessoal nem transfere credenciais GitHub ao Supabase.
