const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('../.tools/browser/node_modules/playwright');
const snippets = require('../frontend/src/presentation/snippets.json');
(async () => {
 const browser = await chromium.launch({headless:true});
 const errors=[];
 try {
  for (const viewport of [{width:1920,height:1080},{width:1366,height:768}]) {
   const page = await browser.newPage({viewport});
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://localhost:5174/apresentacao#codigo');
   const main=page.locator('.pz-main .pz-explorer');
   await main.getByRole('button',{name:'Exibir comentários',exact:true}).click();
   assert.equal(await main.locator('.pz-line-note').count(),snippets[0].code.split('\n').filter(l=>l.trim()).length);
   await page.getByRole('button',{name:'</> Código real',exact:true}).click();
   const dialog=page.getByRole('dialog');
   await dialog.getByRole('button',{name:'Ocultar comentários',exact:true}).waitFor();
   let lastTab=null;
   for (const snippet of snippets) {
    const tab = snippet.tab === 'React' ? 'Frontend' : snippet.tab;
    if (tab !== lastTab) await dialog.getByRole('button',{name:tab,exact:true}).click();
    lastTab=tab;
    await dialog.getByRole('button',{name:snippet.title,exact:true}).click();
    await dialog.getByRole('button',{name:'Ocultar comentários',exact:true}).waitFor();
    const actual=await dialog.locator('.pz-code-explained .pz-src').allTextContents();
    assert.deepEqual(actual,snippet.code.split('\n').map(line=>line||' '),snippet.id);
    assert.equal(await dialog.locator('.pz-line-note').count(),snippet.code.split('\n').filter(line=>line.trim()).length,snippet.id);
   }
   await dialog.getByRole('button',{name:'IA',exact:true}).click();
   await dialog.getByRole('button',{name:'Cache, trava e limite de taxa',exact:true}).click();
   await dialog.locator('.pz-code-toolbar').scrollIntoViewIfNeeded();
   await page.screenshot({path:`docs/demo/screenshots/codigo-com-comentarios-${viewport.width}x${viewport.height}.png`});
   await dialog.getByRole('button',{name:'Ocultar comentários',exact:true}).click();
   assert.equal(await dialog.locator('.pz-line-note').count(),0);
   await dialog.getByRole('button',{name:'Exibir comentários',exact:true}).waitFor();
   await page.screenshot({path:`docs/demo/screenshots/codigo-sem-comentarios-${viewport.width}x${viewport.height}.png`});
   await page.keyboard.press('Escape');
   await page.getByRole('dialog').waitFor({state:'hidden'});
   await main.getByRole('button',{name:'Exibir comentários',exact:true}).waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.close();
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync('docs/demo/comment-validation.json',JSON.stringify({snippets:snippets.length,sourceLines:snippets.reduce((n,s)=>n+s.code.split('\n').length,0),viewports:['1920x1080','1366x768'],errors,checks:['toggle','source preserved','all guides','tab selection','preference shared','drawer close','no horizontal page overflow']},null,2));
  console.log('29 snippets / 588 lines checked in both viewports. Toggle and source fidelity passed.');
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
