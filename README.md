# Órbita · Radar de oportunidades internacionais

Portal em HTML, CSS e JavaScript, hospedado no GitHub Pages. Supabase fornece Auth, Postgres com RLS e uma Edge Function para o motor. Consultas em Python rodam no GitHub Actions a cada quatro horas.

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

Cada consulta detalhada usa ida e volta, 1 adulto, econômica, BRL e o máximo de conexões configurado. As companhias são livres: publica-se a menor tarifa válida retornada para o par de datas, com nomes das companhias. Resultados mistos ou de outras empresas não recebem projeção LATAM. A resposta inicial identifica as opções de ida com preço de uma busca de ida e volta; não confirma todos os segmentos da volta nem disponibilidade de resgate.

Origens: **CWB (Curitiba), JOI (Joinville), NVT (Navegantes), FLN (Florianópolis), VCP (Campinas) e GRU (Guarulhos)**. A restrição vale para a configuração global, os novos radares e o motor. Radares antigos de origens removidas são preservados, pausados e ignorados pelo motor. Há 13 destinos de EUA/Europa ativos, e Tóquio, Seul e Bangkok cadastrados para ativação opcional.

Saídas de amanhã até seis meses de calendário à frente, inclusive. Permanência padrão: 7–20 dias. A volta pode exceder o horizonte de seis meses. O motor também inclui os intervalos dos radares pessoais de contas ativas e respeita o plano vigente.

### Cobertura e capacidade

Com 6 origens, 13 destinos, 182 dias e 14 permanências, a matriz tem **198.744 combinações**. O horizonte e os radares personalizados podem alterar esse total. Uma biblioteca não oficial não fornece capacidade garantida para revisar toda a matriz.

O modo híbrido usa um adaptador local do protocolo de calendário referenciado no [fork de licheng5625](https://github.com/licheng5625/google-flights/blob/d8962650dbcb79dd378d7ce92f41500e2ec8b024/fast_flights/calendar.py). Não instala nem executa código remoto durante as rodadas. Para cada rota/permanência, solicita um gráfico do período configurado e escolhe até três pares mais baratos. **Preços do calendário nunca são publicados diretamente**: cada candidato passa pela consulta detalhada, que confirma preço atual e identifica a companhia. O orçamento padrão de **600 chamadas** inclui ambas as etapas. As duas filas têm cursores persistentes separados.

**Estado observado em 17/10/2026:** os métodos de grade e gráfico do fork retornaram HTTP 200 com erro RPC 13, sem preços. O adaptador trata esse retorno como falha, não como calendário vazio bem-sucedido. Ao primeiro erro por rodada, passa automaticamente para a fila detalhada pelo restante do orçamento; tenta o calendário novamente na rodada seguinte. Não há alegação de aumento de cobertura enquanto essa fonte estiver indisponível. O modo “Somente busca detalhada” permite desativar a tentativa por configuração.

A atividade separa chamadas de calendário, preços descobertos, consultas detalhadas, tarifas publicadas e falhas. Não transforma preços de calendário em porcentagem de cobertura validada. São pesquisadas rotas e permanências diferentes, com datas distribuídas pelos seis meses. Como o horizonte se desloca diariamente, a fila não garante revisão integral de todos os pares absolutos de datas.

O modo completo tem limite operacional de três horas, timeout por chamada e interrupção após oito falhas consecutivas nas consultas detalhadas. Falhas do banco interrompem a execução como erro de infraestrutura. Calendário e consulta detalhada são integrações não oficiais sujeitas a bloqueios.

O cron é `17 */4 * * *` (UTC): aproximadamente 01:17, 05:17, 09:17, 13:17, 17:17 e 21:17 em São Paulo. O GitHub pode atrasar ou suspender agendas por inatividade; não é um serviço com garantia de pontualidade. A execução continua com o navegador fechado. Tarifas deixam de aparecer após oito horas; histórico de preço é retido por 90 dias.

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
