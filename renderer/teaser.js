const { font, withRenderer } = require('./browser');

const [cover, out, label, text] = process.argv.slice(2);

withRenderer({ width: 1080, height: 1920 }, async (page, load) => {
  const html = `<!doctype html><meta charset="utf-8">${font('inter', 600)}${font('inter', 700)}<style>
*{margin:0}body{width:1080px;height:1920px;overflow:hidden;background:#121214;position:relative}
.bg{position:absolute;inset:-80px;background:url('/cover') center/cover;filter:blur(40px) brightness(.45)}
.l{position:absolute;left:60px;top:250px;font:600 36px Inter;letter-spacing:2px;text-transform:uppercase;color:#F5F5F4}
.c{position:absolute;left:60px;top:330px;width:960px;border-radius:24px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.t{position:absolute;left:60px;right:60px;top:1560px;font:700 50px/1.25 Inter;color:#F5F5F4}</style>
<div class="bg"></div><div class="l">${label}</div><img class="c" src="/cover"><div class="t">${text}</div>`;
  await load(html, new Map([['/cover', cover]]));
  await page.locator('.c').evaluate(image => image.decode());
  await page.screenshot({ path: out });
}).catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
