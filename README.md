# Órbita · Radar de oportunidades internacionais

Portal em HTML, CSS e JavaScript, hospedado no GitHub Pages. Supabase fornece Auth, Postgres com RLS e uma Edge Function para o motor. Consultas em Python rodam no GitHub Actions em sessões com pausa mínima de 15 minutos após cada término.

- Portal: https://htcegit.github.io/orbita-milhas/
- Demonstração: https://htcegit.github.io/orbita-milhas/?demo=1
- Supabase: https://supabase.com/dashboard/project/czywkkvwwtcikigbxvty
- Motor: https://github.com/htceGit/orbita-milhas/actions/workflows/scanner.yml

## O que está implementado

Cadastro com confirmação de e-mail, login, recuperação de senha, perfis Free/Pro e administração. Contas Free têm até 3 radares; Pro tem até 30. Os limites são aplicados pelo banco. Usuários não podem alterar seu plano, papel ou status. A suspensão de acesso é verificada no banco mesmo com um token emitido anteriormente.

Exploração de tarifas, filtros por região/origem/destino/preço/datas, favoritos, radares personalizados, projeções de custo com milhas, preferências por usuário, histórico do motor e configuração administrativa de origens/destinos/intervalo. A demonstração usa apenas dados fictícios e armazenamento local, separado das tabelas de produção.

O administrador inicial é reservado no banco privado e promovido **somente após confirmar o e-mail escolhido pelo proprietário**. A reserva não é exposta no repositório. Nenhuma senha inicial é definida pelo projeto.

## Pesquisa

A integração utiliza o projeto MIT [AWeirdDev/flights](https://github.com/AWeirdDev/flights), pacote `fast-flights==3.1.0`. É uma integração **não oficial** com Google Flights; pode sofrer bloqueios ou alterações. Não é uma API de disponibilidade de milhas LATAM Pass.

Cada consulta detalhada usa ida e volta, 1 adulto, econômica, BRL e o máximo de conexões configurado. As companhias são livres: publica-se a menor tarifa válida retornada para o par de datas, com nomes das companhias. A publicação exige preço em dinheiro de ida e volta de **até R$ 3.000 para EUA** ou **até R$ 3.500 para Europa**, para qualquer companhia, inclusive LATAM, antes de projetar milhas. O worker descarta preços acima desses tetos e o banco impede sua gravação. O portal também aplica a regra. Ofertas legadas acima do teto ficam expiradas, com histórico preservado. A política compartilhada está em `fare-policy.json`; alterações exigem atualizar a função de validação na migração do banco. A contagem `offers_price_filtered` distingue descartes de falhas e consultas vazias. Resultados mistos ou de outras empresas não recebem projeção LATAM. A resposta inicial identifica as opções de ida com preço de uma busca de ida e volta; não confirma todos os segmentos da volta nem disponibilidade de resgate.

Origens: **CWB (Curitiba), JOI (Joinville), NVT (Navegantes), FLN (Florianópolis), VCP (Campinas) e GRU (Guarulhos)**. A restrição vale para a configuração global, os novos radares e o motor. Radares antigos de origens removidas são preservados, pausados e ignorados pelo motor. Há 13 destinos de EUA/Europa ativos, e Tóquio, Seul e Bangkok cadastrados para ativação opcional.

Saídas de amanhã até seis meses de calendário à frente, inclusive. Permanência padrão: 7–20 dias. A volta pode exceder o horizonte de seis meses. O motor também inclui os intervalos dos radares pessoais de contas ativas e respeita o plano vigente.

### Cobertura e capacidade

Com 6 origens, 13 destinos, 182 dias e 14 permanências, a matriz tem **198.744 combinações**. O horizonte e os radares personalizados podem alterar esse total. Uma biblioteca não oficial não fornece capacidade garantida para revisar toda a matriz.

O modo híbrido usa o **coletor próprio `calendar_service`**, com Playwright e um navegador isolado sem conta Google. Abre a página pública, usa o gráfico de preços e captura as respostas `GetCalendarGraph` geradas pela própria interface. Não usa o endpoint antigo do fork, não altera requisições assinadas e não transfere cookies de um navegador pessoal.

A API aceita permanência de 7–20 dias (ou o intervalo configurado), mas o gráfico nativo consulta uma duração fixa por vez. O coletor reúne essas durações em janelas de até 60 datas de ida. Uma rota com 182 datas e 14 permanências tem estimativa inicial de **60 chamadas de pesquisa**: 4 páginas + 56 calendários, além de eventuais tentativas limitadas de recuperação. Não são apenas 78 chamadas para toda a matriz. O orçamento de 1.000 contabiliza navegação de pesquisa, tentativas de calendário e consultas detalhadas; arquivos estáticos do Google são recursos auxiliares.

Depois de reunir as janelas de uma captura, o motor seleciona **até dois pares de datas distintos por origem × destino × permanência**, considerando todos os preços obtidos no período. As permanências de 10 e 11 dias têm seleções independentes; as janelas mensais não recebem duas vagas cada uma. Só as datas selecionadas passam pela consulta detalhada para confirmar preço e companhia, e somente essa etapa publica ofertas. Capturas parciais selecionam os melhores preços disponíveis e continuam identificadas como parciais.

O cursor de calendário avança por rota e permanência. O planejador agrupa durações consecutivas para reaproveitar páginas e só inicia um lote com saldo para o calendário e até dois detalhes de cada duração. Se o saldo permitir parte das durações de uma rota, o restante fica para a próxima rodada. Ele não gasta o saldo em consultas individuais arbitrárias quando o calendário está disponível, nem repete um mesmo calendário na mesma rodada. A configuração anterior usa uma versão diferente de cursor e é reiniciada automaticamente ao atualizar. Preços em moeda diferente de BRL, sem datas válidas ou sem preço positivo são descartados.

Na matriz de exemplo há **1.092 calendários lógicos** (6 × 13 × 14), **até 2.184 consultas detalhadas** e **3.276 operações lógicas**. Com as quatro janelas do coletor atual, a estimativa sem falhas é **4.368 respostas de calendário + 312 carregamentos de páginas + 2.184 detalhes = 6.864 chamadas de pesquisa** para a matriz inteira. O orçamento padrão é 1.000 por sessão, configurável no portal. Sem falhas, um lote inicial comporta aproximadamente 158 dos 1.092 calendários lógicos (14,47% das combinações); o valor efetivo depende da captura. Uma sessão não garante a revisão de toda a matriz. A cobertura de preços no calendário e a confirmação de itinerários são medidas diferentes.

**Validação em 17/10/2026:** uma captura de 15 datas × duas permanências retornou os 30 preços, com autenticação e cache testados através da API HTTP local. Uma captura de seis meses × duas permanências retornou 300 preços de 364 combinações solicitadas e foi corretamente marcada como parcial após o Google interromper a resposta. Esses resultados não garantem a mesma cobertura em outras rotas ou no ambiente do Actions.

Bloqueios e verificações humanas interrompem a captura; não há resolução automática de CAPTCHA. Resultados já obtidos são preservados como parciais. Até três falhas consecutivas de calendário desativam essa etapa no restante da rodada; bloqueios explícitos interrompem imediatamente. O motor continua com a fila detalhada quando aplicável.

A API pública autenticada do Supabase recebe pedidos e entrega resultados. Pedidos sem cache entram na fila da próxima sessão disponível, respeitando a pausa mínima entre sessões. Capturas recentes completas têm cache de quatro horas; capturas ficam armazenadas por sete dias. A API síncrona em FastAPI também está pronta para execução local ou em Docker. Veja [docs/API_CALENDARIO.md](docs/API_CALENDARIO.md).

A atividade separa chamadas de calendário, preços descobertos, consultas detalhadas, tarifas publicadas e falhas. Não transforma preços de calendário em porcentagem de cobertura validada. São pesquisadas rotas e permanências diferentes, com datas distribuídas pelos seis meses. Como o horizonte se desloca diariamente, a fila não garante revisão integral de todos os pares absolutos de datas.

O modo ampliado tem limite operacional de três horas, timeout por chamada e interrupção após oito falhas consecutivas nas consultas detalhadas. O navegador tem limite por captura e preserva resultados parciais. Falhas do banco interrompem a execução como erro de infraestrutura. Calendário e consulta detalhada são integrações não oficiais sujeitas a bloqueios.

Cada workflow normal solicita o próximo após uma espera nativa de 15 minutos no ambiente GitHub `scanner-pause-15m`. A espera não mantém runner nem navegador ativos e, em repositórios públicos, é compatível com GitHub Free. A continuidade usa apenas o `GITHUB_TOKEN` temporário do job, com `actions:write` restrito ao próprio repositório; não exige PAT nem credencial persistente. O cron dos minutos 07, 22, 37 e 52 permanece como reserva. `worker.session_gate` ainda impõe a pausa mínima, impede sobreposição e reconcilia encerramentos abruptos. A fila do GitHub pode acrescentar atraso. No portal, pausar o motor interrompe novas pesquisas; as verificações leves continuam para permitir a retomada. Tarifas expiram após oito horas; o histórico tem retenção de 90 dias.

## Economia com milhas

Somente ofertas cuja companhia identificada é exclusivamente LATAM mostram a projeção. A faixa exibida é uma **meta de 25–30%**, calculada sobre a tarifa em dinheiro. O simulador usa o custo por milheiro e as taxas informadas pelo usuário para calcular um orçamento máximo aproximado de milhas. Não há consulta a saldo, inventário de resgates ou cotação real LATAM Pass. Nunca use a faixa como promessa de economia ou oferta confirmada.

## Segurança do motor

O GitHub Actions solicita um JWT OIDC temporário. A Edge Function `scan-api` valida assinatura RS256, emissor, audiência, expiração, IDs imutáveis do repositório/proprietário, branch `main`, caminho do workflow e evento `schedule`/`workflow_dispatch`.

Somente operações de coleta permitidas são aceitas. A chave de serviço permanece no ambiente Supabase. O worker não pode alterar perfis, planos, reservas administrativas ou configurações pelo endpoint. O portal incorpora apenas a chave pública `sb_publishable_`, protegida por RLS. Nunca publique uma chave `service_role` ou `sb_secret_`.

## Desenvolvimento

```sh
npm ci
npm test
npm run test:db
npm run build
npm run dev
```

Abra `http://127.0.0.1:4173/?demo=1`. O build gera arquivos estáticos em `dist/`. `public-config.json` contém somente configuração pública; variáveis `PUBLIC_SUPABASE_URL` e `PUBLIC_SUPABASE_PUBLISHABLE_KEY` podem substituí-la.

Motor local (opcional):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r worker/requirements.txt
.venv/bin/python -m worker.smoke
```

O smoke faz uma consulta real sem persistir. A execução completa roda no Actions com OIDC; fora dele, exige `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` em variáveis locais, nunca no front. `FLIGHTS_PROXY` é opcional e deve ser cadastrado como secret do GitHub caso necessário.

## Operação e abertura comercial

Consulte [docs/OPERACAO.md](docs/OPERACAO.md). A estrutura Free/Pro e a lista de interessados estão implementadas. **Não há cobrança, checkout ou renovação automática.** A tabela privada de eventos está reservada para um futuro webhook de cobrança com assinatura verificada e idempotência.

Para cadastro público comercial, configure SMTP próprio no Supabase. O serviço de e-mail padrão tem limites e restrições de destinatários. Cadastros devem manter confirmação de e-mail. Antes de vender, publique a identificação do operador, contato de privacidade, termos definitivos e política de retenção de dados pessoais.

O GitHub Pages tem restrições ao uso como hospedagem de SaaS comercial. Antes do lançamento comercial, migre o frontend estático para uma hospedagem que permita esse uso; autenticação e dados podem continuar no Supabase. Consulte os [limites oficiais do Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits).

### Diagnóstico e monitoramento

A Administração oferece monitor de sessões com progresso e eventos atualizados a cada 15 segundos, orçamento real da rodada e cobertura única dos preços de calendário. A seção **Composição executada** agrupa as rotas, períodos solicitados ao calendário, permanências e datas detalhadas. O resumo usa toda a sessão e é preservado no banco após o encerramento, mesmo depois da retenção dos logs. O worker preserva a classe e a mensagem sanitizada da falha original e distingue timeout, conexão, erro HTTP, formato inválido e resposta sem tarifa válida. Há uma nova tentativa limitada para falhas transitórias; 403, 429 e verificações humanas encerram a sessão. Eventos são exclusivos de administradores ativos e retidos por sete dias. Veja [operação](docs/OPERACAO.md#monitor-de-sessões) e [revisão do motor](docs/DIAGNOSTICO_DO_MOTOR.md).

O histórico diferencia requisições de calendário (incluindo tentativas), varreduras completas por rota/permanência e preços capturados. Cada sessão registra origem (`manual`, `schedule` ou `continuation`), orçamento efetivo e eventual limite manual de teste. Sessões antigas mantêm campos não registrados como desconhecidos.
