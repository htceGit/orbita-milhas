# Revisão do mecanismo de pesquisa — 17/10/2026

## Evidências

Na sessão `7f49c900-fd26-4643-831b-4242ec9751f6`, CWB → MCO, o calendário trouxe 364 preços de 364 combinações solicitadas em duas permanências. Das quatro datas selecionadas, três consultas detalhadas falharam e uma terminou sem tarifa válida. Os logs antigos preservavam apenas `RuntimeError`: dois pontos do código apagavam a exceção original. Não é possível atribuir essas três falhas históricas a bloqueio, rede ou parser com a evidência disponível.

A repetição local de CWB → MCO, 11–18/03/2027, retornou quatro opções pela biblioteca original. Isso demonstra comportamento intermitente nessa consulta, sem provar a causa anterior. O transporte controlado novo também retornou uma tarifa em teste real GRU → MIA, 21/11–05/12/2026. Um resultado isolado não comprova estabilidade geral.

Na primeira validação do novo diagnóstico no Actions (`39072643010`), o calendário preservou 360 preços antes de um `TimeoutError` ao abrir o botão `Price graph`; duas consultas detalhadas registraram `IndexError` e outra registrou `FlightsNotFound`. Isso confirma problemas de interpretação e espera nessa amostra, sem evidência de HTTP 403/429. O teste também detectou um lote de eventos com campos heterogêneos recusado pelo banco. O envio foi padronizado e recebeu teste de regressão; o encerramento da sessão é tentado mesmo quando os eventos não podem ser gravados.

A validação final no Actions (`39073852478`, sessão `b7120636-7885-4202-8140-67c310c1d2b1`) encerrou normalmente: 12 chamadas de um teto de 20, 120 pares únicos com preço de calendário, quatro datas detalhadas em cinco tentativas e quatro tarifas salvas. Uma falha `FlightsNotFound` foi recuperada na única repetição. Os nove eventos, incluindo causas e encerramento, foram persistidos. A sessão ficou parcial pelo timeout de calendário. O ensaio curto valida contadores, recuperação e persistência; sua cobertura não representa uma rodada de 1.000 chamadas.

## Mudanças implementadas

- Preservação da causa ao atravessar o subprocesso: código, classe original, mensagem sanitizada, status HTTP e possibilidade de nova tentativa.
- Inspeção da resposta HTTP e identificação de recusa, limite e verificação humana antes do parser. O erro da biblioteca na resposta de pesquisa é separado de uma lista vazia válida.
- Timeout explícito do transporte, limite externo por processo e uma única repetição de falhas transitórias, contabilizada no orçamento e respeitando a reserva para as demais datas.
- Bloqueio explícito encerra a sessão inteira, inclusive na fila administrativa; falhas de banco e telemetria interrompem como infraestrutura.
- Reconciliação de sessões sem encerramento: a próxima verificação consulta a execução exata no GitHub e só fecha o registro após confirmar o término, preservando a pausa mínima e os últimos contadores salvos.
- Progresso durante a captura de calendário, eventos administrativos em lotes, cursor salvo periodicamente e painel de sessões.
- Cobertura calculada por pares únicos com preço capturado; consumo de chamadas e validação detalhada têm contadores próprios.

## Oportunidades priorizadas

1. Medir uma sequência de sessões com o novo diagnóstico antes de mudar frequência ou orçamento. Comparar sucesso de detalhe, tempo por etapa, causas, recuperação e cobertura única por chamada. Sessões antigas não permitem reconstruir esses indicadores por causa.
2. Se predominarem erros de formato, adaptar o parser usando respostas de teste sanitizadas e testes de contrato. A integração permanece não oficial e sua estrutura pode mudar. Não armazenar respostas integrais de usuários.
3. Persistir as datas selecionadas ainda não detalhadas em uma fila própria. Hoje interrupções abruptas podem perder o restante dos candidatos do lote, apesar do cursor salvo. Isso exige deduplicação, expiração e testes de retomada.
4. Ampliar a reconciliação já implementada com testes de cancelamento e indisponibilidade prolongada. Quando o GitHub não confirma o encerramento, o gate mantém o bloqueio conservador e só permite a recuperação antiga após quatro horas.
5. Após obter amostra confiável, ajustar intervalo e política de repetição conforme as causas observadas. Não repetir automaticamente respostas de bloqueio nem introduzir serviços pagos sem decisão do operador.

O número de preços de calendário não garante disponibilidade de itinerário, companhia específica ou resgate LATAM Pass. A consulta detalhada continua necessária antes da publicação de uma oferta.

## Continuidade validada em produção

Em 17/10/2026, o ambiente `scanner-pause-15m` iniciou a espera às 22:43:02 UTC. Às 22:58:06 UTC, o job solicitou automaticamente a execução `39077164496`, criada por `github-actions[bot]`. A sessão `c445535a-d089-4c9e-8b2f-e1fb5aa9a8f0` começou às 22:58:48 UTC com `trigger_source=continuation`, `query_budget=1000` e sem limite manual de teste. Isso comprova a liberação do temporizador e a chegada ao motor; a sessão estava em andamento durante a validação. O cron permanece como reserva.

O histórico foi ajustado para separar tentativas de calendário, varreduras completas/solicitadas, preços e tentativas de detalhe. Inclui origem e orçamento efetivo. A apresentação móvel foi validada sem rolagem horizontal.
