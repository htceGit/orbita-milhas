import { build } from 'esbuild';
import { mkdir, cp, writeFile, rm, readFile, rename } from 'node:fs/promises';
import {createHash} from 'node:crypto';
const config=JSON.parse(await readFile('public-config.json','utf8'));
const url = process.env.PUBLIC_SUPABASE_URL ?? config.supabaseUrl ?? '';
const key = process.env.PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? config.supabasePublishableKey ?? '';
if (key && !key.startsWith('sb_publishable_')) throw new Error('Use uma chave pública sb_publishable_, nunca uma chave secreta.');
if (url && !/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(url)) throw new Error('URL Supabase inválida.');
await rm('dist', {recursive:true, force:true});
await mkdir('dist', {recursive:true});
await Promise.all(['index.html', 'styles.css', 'favicon.svg'].map(f => cp(`web/${f}`, `dist/${f}`)));
await build({entryPoints:['web/app.js'], bundle:true, minify:true, sourcemap:false, outfile:'dist/app.js', format:'esm', target:['es2022'], define:{__SUPABASE_URL__:JSON.stringify(url), __SUPABASE_KEY__:JSON.stringify(key)}});
// Asset URLs change with their content, avoiding stale browser/CDN JS or CSS.
let html=await readFile('dist/index.html','utf8');
for(const name of ['app.js','styles.css']){
 const hash=createHash('sha256').update(await readFile(`dist/${name}`)).digest('hex').slice(0,12);
 const [base,extension]=name.split('.');
 const versioned=`${base}.${hash}.${extension}`;
 await rename(`dist/${name}`,`dist/${versioned}`);
 html=html.replace(`./${name}`,`./${versioned}`);
}
await writeFile('dist/index.html',html);
await writeFile('dist/.nojekyll','');
console.log(`Build pronto em dist/ · ${url ? 'Supabase configurado' : 'modo demonstração, sem credenciais'}`);
