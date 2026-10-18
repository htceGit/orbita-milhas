# Revisão do motor e avaliação de Railway

Comparação realizada em 17/10/2026. A pasta FlightsRasp foi apenas lida: seu código não foi executado nem importado. A implementação está no repositório do Órbita.

## O que foi aproveitado

| Etapa | Implementação atualizada |
| --- | --- |
| Calendário | Seletor nativo `GetCalendarPicker`, uma página por lote de rota e contexto reaproveitado. Navegação guiada pelas respostas, com estabilização curta de 500 ms. |
| Cobertura | União contínua dos intervalos das respostas; preço capturado e permanência completamente consultada são medidas diferentes. |
| Seleção | Filtra o teto de dinheiro antes dos detalhes e escolhe até duas datas distintas por duração. |
| Detalhes | Parser de campos essenciais, lendo opções recomendadas e demais tarifas. Não depende de emissões/horários opcionais. |
| Transporte | Um processo/cliente HTTP reaproveitado, com deadline externo de 40 s e reinício após travamento. |
| Falhas | Preserva resultados parciais, tenta outras durações, mantém as não tentadas no cursor e evita consultas aleatórias. Bloqueios explícitos encerram a sessão. |
| API | Uma thread é dona do navegador; cache de quatro horas, uma captura por instância e fechamento do navegador após cinco minutos ocioso. |

A referência fazia suposições que não foram copiadas: três avanços não comprovaram seis meses; a duração muda a posição do calendário; a URL sem datas abriu, em um ensaio, uma duração e um mês diferentes dos presumidos. O Órbita mantém uma data âncora explícita e valida origem, destino, adulto/econômica, conexões, datas e token BRL. Não foram copiados o disfarce de user agent nem a atribuição da duração por variável mutável no callback.

## Evidências e limites

- No mesmo payload público, o bloco recomendado continha R$ 3.799 e o primeiro preço no bloco lido pelo parser anterior era R$ 6.050. O parser novo encontrou oito tarifas válidas e selecionou R$ 3.799. Isso demonstra uma perda concreta de ofertas no parser anterior.
- Duas consultas HTTP de detalhes com o novo processo levaram **1,32 s e 1,48 s**; ambas devolveram tarifas e usaram o mesmo PID. Não representa um SLA nem a rede do Actions/Railway.
- O smoke HTTP local capturou **30/30 preços** (15 datas × permanências de 7 e 8 dias), verificou recusa sem autenticação e confirmou o cache na repetição.
- Um ensaio de seis meses FLN–MIA obteve **165 preços em 9,69 s**, com erro posterior do Google e status parcial. Em outra rota, GRU–MAD, a versão com continuação entre durações preservou **119 de 364 combinações com preço em 7,47 s**, também parcial. Não há evidência de cobertura integral nem de eliminação dos erros do provedor.
- A soma de RSS dos processos no macOS chegou a aproximadamente **677–719 MiB** nos ensaios curtos de navegador. RSS pode contar memória compartilhada mais de uma vez; não é memória média de um mês nem a medição de cgroup que será cobrada no Linux/Railway. O processo de detalhes isolado atingiu cerca de 85 MiB de RSS máximo.

Erros de pesquisa retornados pelo Google são classificados como `upstream_error / CalendarRpcError`; formato desconhecido continua sendo `parse_error`. A infraestrutura não pode garantir que o Google responderá a todas as consultas. O modo antigo de gráfico pode ser selecionado com `CALENDAR_TRANSPORT=graph` para reversão.

## Railway: parecer

**Pode melhorar a continuidade e reduzir a preparação entre rodadas**, por manter o ambiente instalado e permitir processo persistente. O desempenho de cada chamada ao Google depende também da rede, do IP do datacenter e do próprio Google. Migrar a hospedagem não corrige uma resposta inválida nem garante menos bloqueios. Não foi feito benchmark no Railway.

O Hobby custa no mínimo US$ 5/mês e inclui US$ 5 de consumo. Uso excedente é cobrado; o crédito também pode estar sendo usado por outros serviços do workspace. Preços consultados: RAM US$ 10/GB/mês, CPU US$ 20/vCPU/mês e saída US$ 0,05/GB. [Preços oficiais](https://docs.railway.com/pricing), [plano Hobby](https://docs.railway.com/pricing/plans).

Cenários ilustrativos, usando **médias mensais assumidas**, sem tráfego, armazenamento ou outros serviços:

| RAM média | CPU média | Recursos estimados/mês | Total mínimo Hobby |
| --- | --- | --- | --- |
| 0,20 GB | 0,02 vCPU | US$ 2,40 | US$ 5,00 |
| 0,40 GB | 0,05 vCPU | US$ 5,00 | US$ 5,00 |
| 0,70 GB | 0,10 vCPU | US$ 9,00 | US$ 9,00 |

Fórmula: `RAM média × 10 + CPU média × 20 + GB de saída × 0,05`. Não converta o pico de RAM dos ensaios em uma previsão de cobrança. A estimativa confiável exige observar as métricas reais de uma carga representativa no Railway. Fechar o Chromium durante a pausa reduz memória; manter somente o processo Python disponível preserva a instalação e o cache.

## Estrutura preparada e escopo da migração

O repositório já contém `railway.toml`, `calendar_service/Dockerfile` e `calendar_service/server.py`. A imagem usa dependências fixadas, usuário sem privilégios, porta `PORT` e contexto Docker limitado aos arquivos de código necessários. A API privada exige token de pelo menos 32 caracteres; nenhuma credencial do Supabase é necessária para apenas capturar calendários. Execute uma réplica/um processo por serviço. Configure o token em Variables, nunca no GitHub Pages.

**Nada foi implantado nem contratado no Railway nesta revisão.** O scanner publicado continua rodando no Actions com OIDC e pausa mínima de 15 minutos. A configuração preparada serve a API de calendário; não conecta automaticamente o Actions a um serviço remoto.

Para migrar o motor completo, será necessário primeiro configurar uma identidade de máquina restrita ao coletor na `scan-api`: o OIDC atual só aceita o workflow específico do GitHub. Não se deve desativar essa verificação nem colocar `service_role` no navegador. Também será necessário mover a coordenação das sessões/cursor para o worker persistente e desativar o disparo de coleta do Actions no corte, mantendo uma única fila de execução. Auth, banco, filtros, RLS, monitor administrativo e alertas Telegram podem continuar no Supabase.

Sugestão: homologar o coletor privado no Railway com uma amostra limitada, comparar taxa de respostas válidas, duração, preços únicos e consumo, e só então efetuar o corte. O candidato está preparado para revisão; a migração depende da escolha do serviço e da configuração de identidade restrita.
