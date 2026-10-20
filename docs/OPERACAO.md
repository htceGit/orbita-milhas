# Operação do portal

## Separação de responsabilidades

- Cloudflare Pages: destino preparado para o frontend do Órbita; implantação pelo GitHub descrita em [CLOUDFLARE_PAGES.md](CLOUDFLARE_PAGES.md). GitHub Pages continua ativo durante a transição.
- Supabase: Auth, contas, preferências, favoritos, radares pessoais, dados recebidos e alertas Telegram.
- Motor externo: escreve em `public.tarifaspromo` com chave de servidor. Seu código, agenda e implantação pertencem a outro projeto.

O workflow do coletor antigo foi desativado; as sessões restantes foram canceladas, seus históricos removidos e seu ambiente de espera excluído. As APIs antigas scan-api e calendar-api retornam HTTP 410 e não executam operações de coleta. Este repositório só publica e verifica o frontend. Alterações no site não alteram o motor externo.

## Catálogo público e administração

A navegação é aberta, sem cadastro nem login. A migração `public_promotions_portal` permite SELECT de `tarifaspromo` aos papéis `anon` e `authenticated`, com RLS para tarifas positivas e partida atual/futura em Brasília. Visitantes e usuários autenticados não recebem escrita nessa tabela. O coletor mantém suas permissões de servidor. A view `vw_melhores_ofertas` continua com `security_invoker` e sem acesso anônimo, pois o frontend lê a tabela diretamente.

A entrada `#admin`, acessível pelo rodapé, usa Supabase Auth. Somente perfis administrativos ativos podem carregar a administração. Recuperação de senha e contas existentes foram mantidas. Dados de perfis e configurações privadas não foram liberados junto com as tarifas. Suspender uma conta restringe suas operações privadas; o catálogo continua público.

Favoritas da experiência pública ficam na chave local `orbita-public-saved`, separada da demonstração. Não há sincronização entre navegadores. Os antigos favoritos em `tarifaspromo_favorites` continuam isolados por usuário, com seus registros preservados. Os dados de preferências, radares e interesse Pro também foram preservados; essas funcionalidades não aparecem no novo portal.

## Exibição e atualização

Todas as tarifas válidas recebidas para datas atuais/futuras são elegíveis ao catálogo. O preço máximo é escolhido nos filtros. Não há expiração fictícia de oito horas. O site informa a data de atualização recebida e oferece conferência no Google Flights.

O navegador atualiza o feed a cada 60 segundos enquanto a aba está visível, sem formulário/modal em edição. Há atualização manual junto da lista e na Administração. A leitura é paginada; a renderização começa com até 24 grupos de origem × destino recolhidos. As opções são criadas ao expandir cada grupo, 12 por vez. Os resumos e preços mínimos consideram somente as tarifas que passam pelos filtros selecionados. Origem, destino, região, companhia, meses de ida (ano e mês) e tipo de viagem permitem seleção múltipla; as opções na mesma categoria usam OU e categorias diferentes usam E. Os meses mostram contagens com os demais filtros aplicados. As seleções permanecem na URL, usando parâmetros repetidos; parâmetros antigos com um só valor também são aceitos. O compartilhamento de uma tarifa usa `?oferta=ID`, abrindo os detalhes quando ela ainda pertence ao catálogo. A presença de tarifas recentes não é uma confirmação de saúde do worker externo.

## Telegram

As tabelas `private.telegram_settings` e `private.telegram_alerts`, o token no Vault e a Edge Function `telegram-alert` continuam em uso. Destinatário fixo: a conversa já vinculada ao bot do proprietário. Nenhuma credencial deve ir para HTML/JS, repositório ou logs.

O trigger `tarifaspromo_telegram_alert` avalia inserções e mudanças de preço/companhia/voos/datas. Somente preços estritamente abaixo de R$ 3.000 para LATAM exclusivamente ou abaixo de R$ 2.500 para demais companhias entram na fila. LATAM com trechos de outra empresa segue o limite de R$ 2.500. O catálogo não herda esses limites.

A deduplicação ignora atualizações do mesmo preço e itinerário. O despacho e o claim conferem novamente os dados atuais; tarifas que subiram de preço ou perderam a elegibilidade não são enviadas. O cron privado processa a fila e recupera falhas do relay. Até três tentativas de transporte; intervalo mínimo progressivo. O token só é lido pelo caminho de servidor, com nonce de uso único.

A migração não dispara mensagens retroativas para todo o catálogo existente. Novas tarifas e mudanças elegíveis passam pelo trigger.

## Limpeza do legado

Foram retiradas as tabelas do coletor antigo: `offers`, `fare_history`, `favorites`, `scanner_settings`, `scanner_state`, `scan_runs`, `scan_events`, `scan_session_summaries` e `calendar_jobs`. A tabela privada vazia `billing_events`, que era apenas uma reserva futura sem integração ativa, também foi retirada. Migrações históricas permanecem versionadas.

Permanecem as tabelas usadas pelo portal: `profiles`, `preferences`, `monitors`, `pro_interest`, `tarifaspromo` e `tarifaspromo_favorites`; no schema privado, a reserva administrativa e as duas tabelas do Telegram. Schemas e tabelas gerenciados pelo Supabase não são removidos.

## Experiência atual

O portal é gratuito e aberto, sem apresentação de planos ou cadastro público. O mesmo build estático funciona no Cloudflare Pages e no GitHub Pages. O acesso ao catálogo não depende de SMTP. A administração permanece autenticada e os alertas Telegram mantêm suas regras privadas.
