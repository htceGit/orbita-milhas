# API própria de calendário do Órbita

O coletor é mantido neste repositório em `calendar_service/`. Usa um navegador isolado e os controles públicos do Google Flights. Captura respostas nativas de calendário, valida datas/permanência/moeda e devolve JSON de preços. Não depende do fork anterior para extrair o calendário. O `fast-flights` continua fornecendo o construtor de URLs e a validação detalhada de companhia.

## API autenticada publicada

Endpoint: `https://czywkkvwwtcikigbxvty.supabase.co/functions/v1/calendar-api`.

Use `Authorization: Bearer <access_token da sessão Supabase>`. A chave pública da aplicação não substitui o token do usuário. O servidor verifica a sessão no Supabase Auth e o status no perfil; metadados editáveis do usuário não concedem permissões.

Para solicitar uma captura, envie POST:

```json
{
  "action": "create",
  "request": {
    "origin": "GRU",
    "destination": "MIA",
    "departure_start": "2026-11-16",
    "departure_end": "2026-11-30",
    "min_days": 7,
    "max_days": 20,
    "max_stops": 2
  }
}
```

As datas são exemplos; devem estar entre amanhã e seis meses à frente. Origens aceitas: CWB, JOI, NVT, FLN, VCP e GRU. Destino: aeroporto IATA. Sempre ida e volta, econômica, um adulto, BRL. Permanência de 1–60 dias e 0–2 conexões. Campos desconhecidos são rejeitados.

Criação de pedidos está restrita à administração. O retorno sem cache é HTTP 202 com `job_id`, `status: queued` e a informação de processamento na próxima rodada do motor, programada a cada quatro horas. No cache completo de quatro horas, retorna HTTP 200 com `cached: true`. Há limite de um pedido por minuto e uma captura pendente por usuário. A fila é durável no Supabase; o navegador roda no GitHub Actions, sem contratação de servidor adicional.

Para consultar o resultado, envie POST com:

```json
{"action":"get","id":"UUID retornado em job_id"}
```

O retorno inclui status, pedido, erros, validade e `result.entries`, com os preços capturados. O dono do pedido e a administração podem consultá-lo; capturas automáticas globais são visíveis a contas ativas. Contas suspensas não têm acesso. `stale: true` identifica resultado fora da validade de quatro horas. O banco retém capturas por sete dias e não permite que clientes insiram resultados.

## Resultado

Cada entrada traz `origin`, `destination`, `departure_date`, `return_date`, `stay_days`, `price_brl` e `currency: BRL`.

Os metadados incluem `priced_combinations`, `total_combinations`, `search_calls`, `calendar_requests`, `completed_sweeps`, `requested_sweeps`, `collected_at`, `status` e `note`. `completed` significa que a navegação planejada terminou, não que todas as combinações possuem tarifas ou que a companhia foi validada. `partial` preserva os preços anteriores à falha. A mesma combinação é deduplicada dentro da captura.

O gráfico nativo usa duração fixa. A API reúne o intervalo solicitado em janelas de até 60 dias; não transforma uma chamada HTTP à nossa API em uma única chamada ao Google. Para 182 datas e 14 permanências, estima-se inicialmente 60 chamadas de pesquisa por rota, mais tentativas limitadas de recuperação. O worker desconta o custo real do orçamento da rodada, incluindo tentativas que falharam. Arquivos estáticos não são consultas de pesquisa.

A captura não confirma companhia, bagagem, disponibilidade de resgate ou preço final de emissão. As melhores datas, inclusive dos pedidos administrativos, seguem para `worker/provider.py` com orçamento reservado e o limite de conexões pedido, que identifica a companhia e confirma o preço da consulta detalhada antes de publicar uma oferta no portal. Projeções de milhas ficam restritas à identificação LATAM, como simulação.

## API síncrona opcional

Instale as dependências em um ambiente virtual e o navegador:

```sh
.venv/bin/python -m pip install -r calendar_service/requirements.lock
.venv/bin/python -m playwright install chromium
.venv/bin/python -m uvicorn calendar_service.api:app --host 127.0.0.1 --port 4184
```

Configure `CALENDAR_API_TOKEN` no ambiente, com pelo menos 32 caracteres aleatórios, antes de iniciar. Não coloque a credencial no frontend ou em arquivos versionados. Sem token configurado, a API recusa capturas. Em desenvolvimento, `CALENDAR_BROWSER_CHANNEL=chrome` utiliza Chrome instalado, sempre em contexto temporário sem perfil pessoal.

- `GET /health`: disponibilidade do serviço, sem consultar Google.
- `POST /v1/calendar`: mesma estrutura de `request` acima, sem o envoltório `action`.
- Autenticação: `Authorization: Bearer <CALENDAR_API_TOKEN>`.
- `GET /docs`: documentação OpenAPI interativa.

A API síncrona mantém uma captura em andamento por processo, limite de tempo, cache de quatro horas limitado a 32 pedidos e retorna HTTP 429 para concorrência, 422 para parâmetros inválidos e 503 para indisponibilidade do Google. Execute um processo por instância para manter esse limite. Use HTTPS no proxy reverso se hospedar fora do loopback.

Docker, a partir da raiz do repositório:

```sh
docker build -f calendar_service/Dockerfile -t orbita-calendar .
docker run --rm --init -p 127.0.0.1:4184:8080 --env CALENDAR_API_TOKEN orbita-calendar
```

O Dockerfile instala Chromium correspondente à versão fixada do Playwright e executa o serviço como usuário sem privilégios. A imagem é opcional; a API publicada no Supabase usa a fila e não depende de um container permanente.

## Testes

```sh
npm test
npm run test:db
.venv/bin/python -m unittest discover -s calendar_service/tests -v
CALENDAR_BROWSER_CHANNEL=chrome .venv/bin/python -m calendar_service.smoke
```

O smoke faz uma captura real pequena via HTTP, verifica recusa sem autenticação e reutilização do cache quando a captura termina completa. Gera uma credencial temporária em memória; não imprime nem salva esse token. Não persiste ofertas no banco. A captura do Google pode ser parcial ou indisponível em qualquer ambiente, especialmente em datacenters. Não há solver de CAPTCHA, reutilização de conta pessoal nem garantia de cobertura integral.

## Seleção das melhores datas

O worker seleciona até **cinco pares de datas distintos para cada origem × destino × permanência** depois de reunir todas as janelas da captura. Uma captura de 7–20 dias pode gerar até 70 consultas detalhadas. As cinco vagas são para o período inteiro de cada duração, não para cada janela. Uma captura parcial só permite ordenar os preços já obtidos; não confirma que sejam os cinco menores de todo o horizonte.

O orçamento da rodada reserva essas consultas antes de iniciar a captura. Pedidos manuais sem saldo suficiente ficam na fila. Nas pesquisas automáticas, o planejador pode agrupar parte das durações e retomar a próxima duração na rodada seguinte. A administração mostra a mesma regra de seleção, mas a presença de um preço no calendário não comprova que a consulta detalhada tenha sido concluída.
