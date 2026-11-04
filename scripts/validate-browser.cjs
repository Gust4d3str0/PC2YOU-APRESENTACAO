const {chromium}=require('../.tools/browser/node_modules/playwright');
const fs=require('fs');
let activeBrowser;
(async()=>{
 const browser=await chromium.launch({headless:true}); activeBrowser=browser;
 const errors=[];
 for(const viewport of [{width:1920,height:1080},{width:1366,height:768}]){
  const page=await browser.newPage({viewport}); page.on('pageerror',e=>errors.push(e.message));
  for(const [id,title] of [['arquitetura','Arquitetura'],['fluxo','Fluxo completo'],['ia-analise','IA de análise'],['matcher','Product Matcher'],['telegram','Telegram'],['mercadolivre','Mercado Livre'],['mongodb','MongoDB'],['codigo','Código real']]){
   await page.goto('http://localhost:5174/apresentacao#'+id); await page.reload(); await page.getByRole('heading',{name:title,exact:true}).first().waitFor();
   if(id==='matcher') {await page.getByRole('button',{name:'Executar matcher',exact:true}).click(); await page.getByText('Normalização e features',{exact:true}).waitFor();}
   if(id==='mongodb') await page.getByRole('columnheader',{name:'id',exact:true}).waitFor();
   if(id==='telegram') await page.getByText('Última promoção real armazenada',{exact:true}).waitFor();
   await page.screenshot({path:`docs/demo/screenshots/${id}-${viewport.width}x${viewport.height}.png`});
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) errors.push('Horizontal overflow: '+id+' '+viewport.width);
  }
  await page.goto('http://localhost:5174/apresentacao#arquitetura');
  await page.getByRole('button',{name:'API IA',exact:true}).click();
  await page.getByRole('button',{name:'Ver código',exact:true}).click(); await page.getByRole('dialog').waitFor();
  await page.keyboard.press('Escape'); await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.locator('h1').click(); await page.keyboard.press('ArrowRight'); await page.getByRole('heading',{name:'Fluxo completo',exact:true}).waitFor();
  for(const url of ['/','/analyze-pc','/components/ryzen-5-5600','/build']){await page.goto('http://localhost:5174'+url);await page.locator('main').first().waitFor();}
  await page.close();
 }
 fs.writeFileSync('docs/demo/browser-validation.json',JSON.stringify({errors,screenshots:16,viewports:['1920x1080','1366x768']},null,2));
 await browser.close(); if(errors.length) throw Error(errors.join('\n')); console.log('Browser smoke passed; 16 screenshots.');
})().catch(async e=>{console.error(e); await activeBrowser?.close(); process.exitCode=1;});
