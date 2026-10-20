# Publicar o Órbita no Cloudflare Pages pelo GitHub

O código está preparado para importar o repositório existente. A criação do projeto Pages e a autorização da integração com GitHub são feitas na sua conta Cloudflare, seguindo este guia. O endereço de produção só será conhecido depois dessa criação.

O Cloudflare hospeda somente o frontend estático. O Supabase atual continua fornecendo as tarifas e a autenticação administrativa; o coletor no Railway e os alertas Telegram continuam funcionando nos ambientes atuais. Nenhuma migração de banco é necessária para esta mudança de hospedagem.

## 1. Conectar o repositório

1. Acesse o [painel Cloudflare](https://dash.cloudflare.com/).
2. Abra **Workers & Pages → Create application → Pages → Connect to Git**. Escolha a criação de um projeto **Pages** com integração Git.
3. Selecione **GitHub** e autorize a integração para o repositório `htceGit/orbita-milhas`. Na seleção de repositórios do GitHub, é suficiente liberar apenas esse repositório.
4. Selecione [htceGit/orbita-milhas](https://github.com/htceGit/orbita-milhas) e avance para a configuração.

Referência: [integração Git do Cloudflare Pages](https://developers.cloudflare.com/pages/get-started/git-integration/).

## 2. Preencher os campos do build

| Campo | Valor |
| --- | --- |
| Project name | `orbita-milhas`, se disponível; pode escolher outro nome |
| Production branch | `main` |
| Framework preset | `None` |
| Build command | `npm ci --include=dev --no-audit --no-fund && npm run build` |
| Build output directory | `dist` |
| Root directory / Path | Deixar vazio: usar a raiz do repositório |

Adicione a variável de build **`SKIP_DEPENDENCY_INSTALL`** com valor **`1`**. Ela desativa a instalação automática do Pages, porque o comando acima já instala exatamente as versões do `package-lock.json`. O `--include=dev` garante a presença do esbuild, usado apenas para compilar o site. Use a mesma configuração em Production e, se ativar prévias, em Preview.

Node.js 22 é selecionado automaticamente pelo arquivo `.node-version`. Não é preciso instalar Wrangler nem configurar um comando de deploy: o Pages publica a pasta `dist` ao terminar o build.

Referências: [configuração do build](https://developers.cloudflare.com/pages/configuration/build-configuration/) e [versão do Node e instalação das dependências](https://developers.cloudflare.com/pages/configuration/build-image/).

## 3. Configuração do Supabase

**Para o Supabase atual, não precisa adicionar variáveis extras.** O arquivo `public-config.json` já contém a URL e a chave pública do projeto `czywkkvwwtcikigbxvty`. O build usa esses valores automaticamente.

Se quiser substituir a configuração no painel do Cloudflare, estas são as únicas variáveis de aplicação usadas pelo frontend:

| Variável | Valor |
| --- | --- |
| `PUBLIC_SUPABASE_URL` | `https://czywkkvwwtcikigbxvty.supabase.co` |
| `PUBLIC_SUPABASE_PUBLISHABLE_KEY` | A chave pública `sb_publishable_…` de `public-config.json` |

As duas variáveis entram no JavaScript entregue ao navegador e devem pertencer ao mesmo projeto. Nunca coloque `service_role`, `sb_secret_…`, senha do banco ou token Telegram nessas variáveis. A proteção dos dados continua sendo feita pelas permissões e políticas RLS existentes no Supabase. O build recusa chaves com outro prefixo e impede um deploy Pages sem configuração do Supabase.

## 4. Publicar e conferir

1. Clique em **Save and Deploy**.
2. Aguarde a conclusão e copie a URL de produção indicada pelo Cloudflare. O endereço terá o formato `https://NOME-DO-PROJETO.pages.dev`.
3. Abra a URL sem `?demo=1`, para conferir as tarifas reais. No Cloudflare, o portal fica na raiz do domínio, sem o caminho `/orbita-milhas/` usado no GitHub Pages.
4. Confira as tarifas, a expansão das rotas, os filtros de aeroportos e meses, os detalhes e o link para o Google Flights. No celular, confira também os filtros de múltipla seleção.
5. Abra `/#salvas` e `/#admin`. O catálogo é público; só a administração exige login.

O `dist` contém apenas a página, JS/CSS compilados, favicon e arquivos de configuração da hospedagem. Código do banco, testes, dependências e arquivos de desenvolvimento não são publicados nessa pasta. O `_headers` é interpretado pelo Pages para aplicar segurança e cache. O HTML deve ser revalidado; JS/CSS com hash recebem cache de um ano e mudam de URL quando seu conteúdo muda.

Para conferir esses cabeçalhos depois de publicar, abra as ferramentas de desenvolvedor do navegador, aba **Network**, e inspecione a resposta da página e de um arquivo `app.HASH.js`. Na página devem aparecer `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` e `Cache-Control: public, max-age=0, must-revalidate`; no JS com hash, `Cache-Control: public, max-age=31536000, immutable`.

Referência: [cabeçalhos HTTP no Pages](https://developers.cloudflare.com/pages/configuration/headers/). O servidor local e o GitHub Pages não interpretam esse arquivo.

## 5. Autorizar o novo endereço na administração do Supabase

Faça esta configuração **depois de conhecer e testar a URL real do Pages**. A leitura pública das ofertas e o login com senha não dependem desse redirecionamento; ele é necessário para o retorno dos links de recuperação de senha da administração.

1. Abra [Supabase → Authentication → URL Configuration](https://supabase.com/dashboard/project/czywkkvwwtcikigbxvty/auth/url-configuration).
2. Em **Redirect URLs**, adicione a URL raiz e a URL administrativa do novo portal, com a barra antes do fragmento.
3. Quando escolher o Cloudflare como endereço principal, altere **Site URL** para a raiz do novo portal.
4. Salve. Mantenha os endereços antigos do GitHub autorizados enquanto estiver usando os dois portais.

Por exemplo, **somente se** a URL criada tiver sido `https://orbita-milhas.pages.dev`:

```text
Site URL:
https://orbita-milhas.pages.dev/

Redirect URLs a adicionar:
https://orbita-milhas.pages.dev/
https://orbita-milhas.pages.dev/#admin
```

Troque o domínio do exemplo pela URL real recebida. Use URLs exatas de produção; não libere todos os domínios `*.pages.dev`. Prévia de branch pode consultar o catálogo público sem ser autorizada para recuperação administrativa. O portal monta o retorno administrativo a partir do endereço onde está aberto, sem domínio GitHub fixado no código.

Referência: [redirecionamentos do Supabase Auth](https://supabase.com/docs/guides/auth/redirect-urls).

Favoritas e sessão administrativa ficam no armazenamento de cada domínio no navegador: não são transferidas automaticamente do GitHub Pages para o Cloudflare. As contas e tarifas continuam no mesmo banco; basta entrar novamente na administração. A mudança de hospedagem também não altera a configuração de SMTP.

## 6. Domínio próprio, se desejar

No projeto Pages, abra **Custom domains → Set up a domain** e siga o fluxo antes de criar os registros DNS. Para um domínio raiz, o domínio precisa estar na mesma conta Cloudflare, com os nameservers configurados conforme o painel. Um subdomínio em DNS externo pode usar CNAME, conforme as instruções apresentadas.

Depois que o domínio próprio estiver ativo em HTTPS, repita a configuração de **Site URL** e **Redirect URLs** no Supabase com o domínio escolhido. O código não precisa mudar.

Referência: [domínios personalizados no Pages](https://developers.cloudflare.com/pages/configuration/custom-domains/).

## Atualizações e retorno a uma versão anterior

Com a integração ativa, cada push para `main` dispara um novo deploy de produção no Cloudflare Pages. Alterações de tarifas chegam pelo Supabase e não precisam de novo deploy. Em **Deployments**, confira o commit publicado; se precisar, selecione uma implantação de produção anterior e use a opção de rollback disponível no painel.

O workflow `Publicar portal no GitHub Pages (manual)` está disponível somente para execução manual. Na preparação desta migração, a hospedagem GitHub Pages não estava habilitada no repositório. Para um eventual retorno, habilite Pages com GitHub Actions nas configurações do repositório e execute o workflow manualmente. O workflow `Verificações do portal` continua automático em pushes e pull requests. Depois de conectar o Cloudflare, as publicações serão feitas pela integração Git do próprio Pages.

## Diagnóstico rápido

| Sintoma | Conferência |
| --- | --- |
| Tela inicial do Worker em vez do portal | Confirmar que foi criado um projeto **Pages**, com saída `dist` |
| Build não encontra `package.json` | Deixar Root directory vazio |
| Build não encontra esbuild | Usar o comando com `npm ci --include=dev` indicado acima |
| URL/credencial Supabase inválida | Remover substituições indevidas ou fornecer as duas variáveis públicas corretas e refazer o deploy |
| Aparecem tarifas fictícias | Remover `?demo=1` do endereço |
| Recuperação retorna ao site antigo | Conferir URL exata em Redirect URLs e Site URL no Supabase |
| Mudou uma variável, mas o portal não mudou | Fazer novo deploy; a configuração é incorporada durante o build |
| CSS/JS retornam HTML ou 404 | Confirmar saída `dist` e abrir a raiz da URL Pages, sem `/orbita-milhas/` |

As rotas internas usam `#ofertas`, `#salvas` e `#admin`; não precisam de `_redirects` nem de reescrita global para `index.html`.
