# Órbita · Portal de oportunidades internacionais

Frontend HTML/CSS/JavaScript publicado no [GitHub Pages](https://htcegit.github.io/orbita-milhas/), com login, perfis Free/Pro, favoritos, radares pessoais e administração de usuários no Supabase.

O coletor é um projeto externo operado pelo proprietário no Railway. **Este repositório não contém nem agenda pesquisas de voos.** Os únicos workflows ativos são verificação e publicação do portal.

## Fonte das tarifas

O portal lê `public.tarifaspromo` usando a sessão Supabase do usuário. A tabela é preenchida pelo coletor com uma chave de servidor. O navegador usa somente a chave pública e não pode inserir, alterar ou excluir tarifas. RLS restringe a leitura a perfis ativos; contas suspensas perdem acesso mesmo com uma sessão anterior.

A consulta usa datas futuras ou o dia atual em Brasília. Campos em português são adaptados em `web/tarifas.js`; IDs bigint são recebidos como texto para preservar a precisão. O portal mostra todas as tarifas válidas recebidas, **sem reaplicar os tetos do coletor antigo e sem inventar expiração**. Filtros de preço, origem, região e datas são escolhas do usuário. A leitura percorre páginas de 500 registros, até 10.000 tarifas mais baratas por consulta; o portal informa quando atingir esse limite. A tela mostra inicialmente 24 cartões e oferece “Ver mais”.

A aba ativa verifica atualizações a cada minuto. A área de atividade mostra as atualizações das tarifas; não simula estado, agenda ou cobertura do coletor externo. Radares pessoais destacam dados recebidos que atendem aos critérios e não alteram as pesquisas do Railway.

Os detalhes incluem companhia, datas, horários, números dos voos, duração, conexões e aeronave quando informados. Preços e condições devem ser confirmados no Google Flights. A projeção LATAM de 25–30% é uma simulação de planejamento; não consulta resgates, saldo ou disponibilidade no LATAM Pass. Companhias mistas não recebem essa projeção.

## Alertas Telegram

O Supabase mantém os alertas privados de `tarifaspromo`:

- LATAM exclusivamente: preço **menor que R$ 3.000**.
- Demais companhias, inclusive mistas: preço **menor que R$ 2.500**.
- Valores iguais aos limites não alertam. Esses tetos não limitam o catálogo do portal.

O trigger coloca mensagens em uma fila privada, deduplica rota/datas/preço/companhia/voos e usa a Edge Function `telegram-alert`. O token fica no Vault; o HTTP do banco contém somente UUID e nonce de despacho. A mensagem só é enviada se a tarifa ainda atender à regra no momento do despacho e da leitura pela função. Existe uma única repetição lógica da mensagem na fila, com até três tentativas de transporte e retenção de 90 dias. Timeouts podem provocar reenvio caso a entrega não tenha sido confirmada.

## Desenvolvimento

```sh
npm ci
npm test
npm run test:db
npm run build
npm run dev
```

Demonstração: `http://127.0.0.1:4173/?demo=1`. Usa dados fictícios e armazenamento local, separados das contas e dos dados reais. `public-config.json` só contém URL e chave pública. Variáveis `PUBLIC_SUPABASE_URL` e `PUBLIC_SUPABASE_PUBLISHABLE_KEY` podem substituí-las no build. Nunca incorpore uma chave de servidor no frontend.

Os testes de banco usam PGlite e doubles locais de Vault/pg_net/Cron, sem enviar mensagens. As migrações históricas são mantidas para reconstruir o esquema; as migrações finais retiram as tabelas e funções do coletor antigo e migram os alertas para a fonte externa.

Consulte [docs/OPERACAO.md](docs/OPERACAO.md). SMTP próprio, domínio, cobrança e checkout do Pro continuam como etapas futuras.
