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

Cada consulta detalhada usa ida e volta, 1 adulto, econômica, BRL e o máximo de conexões configurado. As companhias são livres: publica-se a menor tarifa válida retornada para o par de datas, com nomes das companhias. A publicação exige preço em dinheiro de ida e volta de **até R$ 3.000 para EUA** ou **até R$ 3.500 para Europa**, para qualquer companhia, inclusive LATAM, antes de projetar milhas. O worker filtra candidatos no calendário e descarta preços detalhados acima desses tetos e o banco impede sua gravação. O portal também aplica a regra. Ofertas legadas acima do teto ficam expiradas, com histórico preservado. A política compartilhada está em `fare-policy.json`; alterações exigem atualizar a função de validação na migração do banco. A contagem `offers_price_filtered` distingue descartes de falhas e consultas vazias. Resultados mistos ou de outras empresas não recebem projeção LATAM. A resposta inicial identifica as opções de ida com preço de uma busca de ida e volta; não confirma todos os segmentos da volta nem disponibilidade de resgate.

Origens: **CWB (Curitiba), JOI (Joinville), NVT (Navegantes), FLN (Florianópolis), VCP (Campinas) e GRU (Guarulhos)**. A restrição vale para a configuração global, os novos radares e o motor. Radares antigos de origens removidas são preservados, pausados e ignorados pelo motor. Há 13 destinos de EUA/Europa ativos, e Tóquio, Seul e Bangkok cadastrados para ativação opcional.

Saídas de amanhã até seis meses de calendário à frente, inclusive. Permanência padrão: 7–20 dias. A volta pode exceder o horizonte de seis meses. O motor também inclui os intervalos dos radares pessoais de contas ativas e respeita o plano vigente.

### Cobertura e capacidade

Com 6 origens, 13 destinos, 182 dias e 14 permanências, a matriz tem **198.744 combinações**. O horizonte e os radares personalizados podem alterar esse total. Uma biblioteca não oficial não fornece capacidade garantida para revisar toda a matriz.

O modo híbrido usa o **coletor próprio `calendar_service`**, com Playwright e um navegador isolado sem conta Google. Abre uma página por lote de rota, usa o seletor nativo de datas e captura as respostas `GetCalendarPicker` geradas pela interface. O navegador e seu contexto são reaproveitados entre rotas; cada página é fechada ao terminar. Não há reprodução de chamadas assinadas nem transferência de cookies pessoais.

O coletor percorre os meses efetivamente pedidos pelo Google para cada duração. A primeira resposta costuma reunir dois meses; cada avanço normalmente acrescenta um mês. Mudar a permanência reposiciona o calendário na data de ida selecionada. Por isso, não é seguro assumir que três avanços cobrem seis meses ou alternar avanço/recuo sem conferir os intervalos. Uma varredura só conta como completa quando a união dos intervalos respondidos cobre todo o período solicitado. Datas com preço têm contagem separada.

Para saídas de 18/10/2026 a 17/04/2027 e permanências 7–20, a estimativa inicial é **85 chamadas de calendário por rota**: uma página + até seis respostas por permanência. O número varia com os meses abrangidos e com o comportamento do Google. A navegação espera a resposta correspondente à rota/duração e uma estabilização de 500 ms da interface, sem `networkidle` ou recargas por janela. O coletor antigo de gráfico permanece disponível com `CALENDAR_TRANSPORT=graph` para reversão operacional.

Antes dos detalhes, o worker elimina preços de calendário acima de **R$ 3.000 para EUA / R$ 3.500 para Europa**. Entre os preços elegíveis, seleciona **até dois pares de datas distintos por origem × destino × permanência**, considerando todo o período capturado. Só essas datas passam à leitura detalhada, que verifica novamente o preço e identifica a companhia. O contador `offers_price_filtered` registra descartes após os detalhes; preços brutos de calendário continuam contabilizados como capturados. Uma captura parcial seleciona apenas os melhores preços já obtidos.

O parser próprio de detalhes lê **tarifas recomendadas e demais opções**, exige token de moeda BRL, preço positivo, rota/data e conexões coerentes. Campos opcionais de emissões/horários não derrubam tarifas válidas. O processo de detalhes reaproveita o cliente HTTP e mantém o limite externo de 40 segundos por consulta; travamentos encerram e recriam esse processo.

O cursor continua por rota/permanência. Durações ainda não tentadas após uma interrupção permanecem na fila; falhar um mês não descarta automaticamente todas as permanências seguintes. Três durações consecutivas com erro encerram o lote. Três capturas consecutivas sem resultados encerram a etapa, e bloqueios explícitos interrompem imediatamente. O modo híbrido **não usa o saldo em consultas aleatórias**. O modo somente detalhado continua disponível por escolha administrativa.

Na matriz de exemplo há **1.092 calendários lógicos** (6 × 13 × 14) e até **2.184 detalhes**. Considerando 85 chamadas por rota, a estimativa sem falhas é **6.630 chamadas para calendários + até 2.184 detalhes = 8.814 chamadas**. Com teto de 1.000, um exemplo sem falhas e com dois detalhes elegíveis em todas as durações comporta cerca de 123 calendários lógicos (11,26%). O filtro de preço pode liberar saldo para outros calendários; falhas e mudanças do Google reduzem a captura. Isso é planejamento, não cobertura garantida nem contagem de todas as requisições HTTP de recursos auxiliares.

**Validação local em 17/10/2026:** API com autenticação e cache capturou 30/30 preços em 15 datas × duas permanências. Duas consultas de detalhes levaram 1,32 s e 1,48 s no mesmo processo. Ensaios de seis meses continuaram recebendo erros do Google e preservaram resultados parciais; não comprovam revisão integral nem a mesma latência no Actions. A comparação com FlightsRasp, as medições e a avaliação do Railway estão em [docs/MOTOR_E_RAILWAY.md](docs/MOTOR_E_RAILWAY.md).

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
python3 -m venv .venv
.venv/bin/python -m pip install -r calendar_service/requirements.txt
export PATH="$PWD/.venv/bin:$PATH"
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

## Alertas Telegram

Ofertas salvas dentro dos tetos geram alertas por trigger no Supabase, com rota, ida/volta, permanência, companhia, preço e botão do Google Flights. A mesma oferta no mesmo preço não repete a mensagem. O envio usa fila assíncrona, Edge Function e tentativas limitadas; token no Vault e destinatário privado. Nenhuma credencial é publicada no GitHub Pages. Veja a configuração e o fluxo de entrega em [operação](docs/OPERACAO.md#alertas-de-tarifas-no-telegram).
