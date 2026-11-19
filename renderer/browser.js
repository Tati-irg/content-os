const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { once } = require('node:events');
const { chromium } = require('playwright-core');

const fonts = path.join(__dirname, 'node_modules', '@fontsource');
const contentTypes = {
  '.css': 'text/css',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.avif': 'image/avif',
};

function font(pkg, weight, italic = false) {
  return `<link rel="stylesheet" href="/fonts/${pkg}/${weight}${italic ? '-italic' : ''}.css">`;
}

async function withRenderer(viewport, render) {
  let html;
  let assets;
  const server = http.createServer((req, res) => {
    const route = req.url;
    if (req.method === 'GET' && route === '/') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(html);
      return;
    }
    const fontFile = /^\/fonts\/((?:inter|inter-tight|lora|montserrat)\/(?:files\/)?[\w.-]+\.(?:css|woff2?))$/.exec(route);
    const file = fontFile ? path.join(fonts, fontFile[1]) : assets?.get(route);
    if (req.method !== 'GET' || !file) {
      res.writeHead(404).end();
      return;
    }
    const stream = fs.createReadStream(file);
    stream.once('error', () => {
      if (res.headersSent) res.destroy();
      else res.writeHead(404).end();
    });
    stream.once('open', () => {
      res.writeHead(200, {
        'Content-Type': contentTypes[path.extname(file).toLowerCase()] || 'application/octet-stream',
        'Cache-Control': 'no-store',
      });
      stream.pipe(res);
    });
  });

  server.listen(0, '127.0.0.1');
  let browser;
  try {
    await once(server, 'listening');
    const origin = `http://127.0.0.1:${server.address().port}`;
    const executablePath = process.env.CHROME ||
      ['/usr/bin/chromium', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find(file => fs.existsSync(file));
    browser = await chromium.launch({ executablePath });
    const page = await browser.newPage({ viewport });
    await page.route('**/*', route =>
      new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    return await render(page, async (document, files = new Map()) => {
      html = document;
      assets = files;
      await page.goto(origin, { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
    });
  } finally {
    try {
      await browser?.close();
    } finally {
      server.close();
    }
  }
}

module.exports = { font, withRenderer };
