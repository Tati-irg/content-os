const { chromium } = require('playwright'); const fs=require('fs'), path=require('path');
const NM=path.join(__dirname,'node_modules/@fontsource');
const base=[['black','чёрный','#121214'],['graphite','графит','#2B2C30'],['cool gray','холодный серый','#8E9299'],['cool gray light','светлый холодный серый','#E7E8EA'],['white','белый','#F5F5F4'],['taupe','тауп','#8A7F76'],['taupe light','светлый тауп','#D6D0CA'],['cool muted brown','холодный приглушённый коричневый','#5E524C']];
const acc=[['wine','винный','#7B1E33'],['indigo','глубокий индиго','#2C3566'],['terracotta','терракота','#A24F38']];
const sw=(a,big)=>a.map(([e,r,h])=>`<div class="c"><div class="b ${big?'big':''}" style="background:${h}"></div><div class="n">${r}</div><div class="e">${e} · ${h}</div></div>`).join('');
const html=`<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="file://${NM}/inter/400.css"><link rel="stylesheet" href="file://${NM}/inter/600.css"><link rel="stylesheet" href="file://${NM}/lora/600.css">
<style>body{margin:0;width:1080px;height:1350px;background:#F5F5F4;font-family:Inter;color:#121214;padding:80px;box-sizing:border-box}
h1{font:600 64px Lora;margin:0 0 8px}p{font:400 26px/1.4 Inter;color:#45464B;margin:0 0 40px}h2{font:600 24px Inter;letter-spacing:.14em;text-transform:uppercase;color:#8A7F76;margin:30px 0 20px}
.g{display:grid;grid-template-columns:repeat(4,1fr);gap:22px}.g3{grid-template-columns:repeat(3,1fr)}
.b{height:120px;border-radius:18px;border:1px solid #DCDDE0}.b.big{height:170px}.n{font:600 22px/1.25 Inter;margin-top:12px}.e{font:400 18px Inter;color:#8E9299;margin-top:4px}
.no{font:400 24px/1.5 Inter;color:#45464B;margin-top:40px}</style></head><body>
<h1>Палитра каруселей</h1><p>Одна на все шаблоны. Шаблон меняет вёрстку, цвета остаются эти.<br>В одной карусели один акцент.</p>
<h2>Основа</h2><div class="g">${sw(base)}</div><h2>Акценты</h2><div class="g g3">${sw(acc,1)}</div>
<div class="no"><b>Не используем:</b> неон, конфетную пастель, случайный фиолетовый, зелёный, бирюзовый.</div></body></html>`;
(async()=>{const f=path.join(__dirname,'_pal.html');fs.writeFileSync(f,html);const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome'});const p=await b.newPage({viewport:{width:1080,height:1350}});await p.goto('file://'+f);await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);await p.screenshot({path:process.argv[2]});await b.close();fs.unlinkSync(f)})();
