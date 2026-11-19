// Stories renderer: JSON [{file, photo, focus?, label, text}] -> PNG 1080x1920.
// Full-bleed photo, dark gradient at the bottom, teaser text. No Instagram-only wording:
// stories are auto-reposted to VK and Telegram.
// Usage: node story.js spec.json out_dir
const { font, withRenderer } = require('./browser');
const path = require('path');
const fs = require('fs');

const PHOTO_DIR = process.env.PHOTO_DIR || '/mnt/project-files/photo-bank/ACTIVE';
const FONTS = [font('lora', 600), font('inter', 500), font('inter', 600)].join('');
const photoFile = id => path.join(PHOTO_DIR, fs.readdirSync(PHOTO_DIR).find(x => x.startsWith(id + '_')));
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');

const html = s => `<!doctype html><meta charset="utf-8">${FONTS}<style>
*{margin:0;box-sizing:border-box}body{width:1080px;height:1920px;overflow:hidden;background:#121214}
.ph{position:absolute;inset:0;background:url('/photo') ${(s.focus || [50, 25]).join('% ')}%/cover no-repeat}
.g{position:absolute;inset:0;background:linear-gradient(180deg,rgba(18,18,20,0) 35%,rgba(18,18,20,.82) 62%,rgba(18,18,20,.95) 100%)}
.box{position:absolute;left:90px;right:90px;bottom:330px;color:#F5F5F4}
.l{font:600 30px Inter;letter-spacing:4px;text-transform:uppercase;color:#E9C9A8;margin-bottom:34px}
.t{font:600 58px/1.25 Lora}
.s{position:absolute;left:90px;bottom:200px;font:500 30px Inter;color:#C9CACE}
</style><div class="ph"></div><div class="g"></div>
<div class="box"><div class="l">${esc(s.label)}</div><div class="t">${esc(s.text)}</div></div>
<div class="s">Татьяна Иргисцева · психолог, сексолог, гипнолог</div>`;

(async () => {
  const [specPath, outDir] = process.argv.slice(2);
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  fs.mkdirSync(outDir, { recursive: true });
  await withRenderer({ width: 1080, height: 1920 }, async (page, load) => {
    for (const s of spec) {
      await load(html(s), new Map([['/photo', photoFile(s.photo)]]));
      await page.evaluate(() => {
        const photo = new Image();
        photo.src = '/photo';
        return photo.decode();
      });
      await page.screenshot({ path: path.join(outDir, s.file) });
      console.log(s.file);
    }
  });
})().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
