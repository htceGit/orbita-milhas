# Operação do portal

## Separação de responsabilidades

- GitHub Pages: frontend do Órbita.
- Supabase: Auth, contas, preferências, favoritos, radares pessoais, dados recebidos e alertas Telegram.
- Motor externo: escreve em `public.tarifaspromo` com chave de servidor. Seu código, agenda e implantação pertencem a outro projeto.

O workflow do coletor antigo foi desativado; as sessões restantes foram canceladas, seus históricos removidos e seu ambiente de espera excluído. As APIs antigas scan-api e calendar-api retornam HTTP 410 e não executam operações de coleta. Este repositório só publica e verifica o frontend. Alterações no site não alteram o motor externo.

## Contas e acesso

Login, cadastro, confirmação de e-mail e recuperação de senha usam Supabase Auth. A Administração gerencia planos Free/Pro, validade do Pro e suspensão. Usuários não podem promover a própria conta. A reserva administrativa é privada e o administrador é promovido após confirmar o e-mail reservado.

A tabela de tarifas permite somente leitura por usuários com perfil ativo. A gravação é exclusiva do servidor. A view existente `vw_melhores_ofertas` usa `security_invoker`, respeitando as mesmas permissões. Não use essa view ou uma chave de servidor para contornar o login.

Favoritos novos ficam em `tarifaspromo_favorites`, vinculados ao usuário e ao ID bigint da tarifa. Favoritos antigos são reaproveitados quando existe correspondência de rota e datas no feed novo. Cada usuário só lê e altera seus próprios dados. Os radares têm limite de 3 no Free e 30 no Pro/admin; servem para destacar tarifas do catálogo, sem controlar o coletor externo.

## Exibição e atualização

Todas as tarifas válidas recebidas para datas atuais/futuras são elegíveis ao catálogo. O preço máximo é escolhido nos filtros. Não há expiração fictícia de oito horas. O site informa a data de atualização recebida e oferece conferência no Google Flights.

O navegador atualiza o feed a cada 60 segundos enquanto a aba está visível, sem formulário/modal em edição. Há atualização manual na área de atualizações e na Administração. A leitura é paginada; a renderização começa com 24 cartões. A presença de tarifas recentes não é uma confirmação de saúde do worker externo.

## Telegram

As tabelas `private.telegram_settings` e `private.telegram_alerts`, o token no Vault e a Edge Function `telegram-alert` continuam em uso. Destinatário fixo: a conversa já vinculada ao bot do proprietário. Nenhuma credencial deve ir para HTML/JS, repositório ou logs.

O trigger `tarifaspromo_telegram_alert` avalia inserções e mudanças de preço/companhia/voos/datas. Somente preços estritamente abaixo de R$ 3.000 para LATAM exclusivamente ou abaixo de R$ 2.500 para demais companhias entram na fila. LATAM com trechos de outra empresa segue o limite de R$ 2.500. O catálogo não herda esses limites.

A deduplicação ignora atualizações do mesmo preço e itinerário. O despacho e o claim conferem novamente os dados atuais; tarifas que subiram de preço ou perderam a elegibilidade não são enviadas. O cron privado processa a fila e recupera falhas do relay. Até três tentativas de transporte; intervalo mínimo progressivo. O token só é lido pelo caminho de servidor, com nonce de uso único.

A migração não dispara mensagens retroativas para todo o catálogo existente. Novas tarifas e mudanças elegíveis passam pelo trigger.

## Limpeza do legado

Foram retiradas as tabelas do coletor antigo: `offers`, `fare_history`, `favorites`, `scanner_settings`, `scanner_state`, `scan_runs`, `scan_events`, `scan_session_summaries` e `calendar_jobs`. A tabela privada vazia `billing_events`, que era apenas uma reserva futura sem integração ativa, também foi retirada. Migrações históricas permanecem versionadas.

Permanecem as tabelas usadas pelo portal: `profiles`, `preferences`, `monitors`, `pro_interest`, `tarifaspromo` e `tarifaspromo_favorites`; no schema privado, a reserva administrativa e as duas tabelas do Telegram. Schemas e tabelas gerenciados pelo Supabase não são removidos.

## Preparação comercial

O Pro tem liberação administrativa e registro de interesse; não há cobrança ou renovação automática. Configure SMTP próprio antes de abrir os cadastros ao público. Domínio próprio, identificação do operador, contato de privacidade e termos definitivos continuam necessários para o lançamento.
