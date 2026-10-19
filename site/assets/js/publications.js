(()=>{
 'use strict';
 const allEl=document.querySelector('#all-publications');
 if(!allEl)return;
 const selEl=document.querySelector('#selected-publications');
 const search=document.querySelector('#paper-search');
 const year=document.querySelector('#paper-year');
 const type=document.querySelector('#paper-type');
 const status=document.querySelector('#paper-status');
 const note=document.querySelector('#publication-source-note');
 const noResults=document.querySelector('#paper-no-results');
 const more=document.querySelector('#paper-load-more');
 let publications=[],limit=30;
 const external=(url)=>typeof url==='string' && /^https:\/\//i.test(url);
 const makeLink=(label,url)=>{
   const a=document.createElement('a');a.textContent=label;a.href=url;
   a.target='_blank';a.rel='noopener noreferrer';return a;
 };
 function renderPaper(p){
   const item=document.createElement('article');item.className='paper-item';
   const y=document.createElement('div');y.className='paper-year';y.textContent=String(p.year||'');
   const content=document.createElement('div');content.className='paper-content';
   const h=document.createElement('h3');
   const record=[p.dblp_url,p.doi_url,p.openaire_url,p.openalex_url].find(external)||'https://dblp.org/pid/134/1019.html';
   h.append(makeLink(String(p.title||'Untitled'),record));
   const authors=document.createElement('p');authors.className='paper-authors';authors.textContent=(p.authors||[]).join(', ');
   const venue=document.createElement('p');venue.className='paper-venue';
   const badge=document.createElement('span');badge.className='paper-badge';badge.textContent=p.type||'Other';
   venue.append(badge,document.createTextNode(' · '+(p.venue||'Publication')));
   const links=document.createElement('div');links.className='paper-links';
   if(external(p.doi_url))links.append(makeLink('DOI ↗',p.doi_url));
   if(external(p.pdf_url) && p.pdf_url!==p.doi_url)links.append(makeLink('Full text ↗',p.pdf_url));
   // DBLP publishes BibTeX for each publication record; no client-side API required.
   if(external(p.dblp_url) && p.key && !p.key.startsWith('openaire/') && !p.key.startsWith('openalex/') && /^[A-Za-z0-9._/:-]+$/.test(p.key)) links.append(makeLink('BibTeX ↗','https://dblp.org/rec/'+p.key+'.bib'));
   content.append(h,authors,venue,links);item.append(y,content);return item;
 }
 const normalize=s=>(s||'').toString().normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 function visible(p){
   const q=normalize(search.value.trim());
   const hay=normalize([p.title,(p.authors||[]).join(' '),p.venue,p.year,p.type].join(' '));
   return (!q||hay.includes(q)) && (!year.value||String(p.year)===year.value) && (!type.value||p.type===type.value);
 }
 function update(){
   const matched=publications.filter(visible);const shown=matched.slice(0,limit);
   allEl.replaceChildren(...shown.map(renderPaper));
   status.textContent=`${shown.length} of ${matched.length} matching publications (${publications.length} total)`;
   noResults.hidden=matched.length!==0;
   more.hidden=matched.length<=limit;
 }
 Promise.all([
   fetch('data/publications.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error(`Bibliography HTTP ${r.status}`);return r.json()}),
   fetch('data/selected-publications.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error(`Selection HTTP ${r.status}`);return r.json()})
 ]).then(([source,selected])=>{
   publications=(Array.isArray(source.publications)?source.publications:[]).filter(p=>p&&p.key&&p.title);
   publications.sort((a,b)=>(Number(b.year)||0)-(Number(a.year)||0)||a.title.localeCompare(b.title));
   const byKey=new Map(publications.map(p=>[p.key,p]));
   const highlights=(Array.isArray(selected.keys)?selected.keys:[]).map(k=>byKey.get(k)).filter(Boolean);
   selEl.replaceChildren(...highlights.map(renderPaper));
   if(!highlights.length)selEl.textContent='No publications selected yet.';
   for(const y of [...new Set(publications.map(p=>p.year).filter(Boolean))].sort((a,b)=>b-a)){
     const opt=document.createElement('option');opt.value=String(y);opt.textContent=String(y);year.append(opt);
   }
   note.textContent=source.bootstrap_only
      ? 'Initial sample bibliography. Run the GitHub Action “Update bibliography and deploy” to import the complete DBLP record.'
      : (source.source==='openaire+cached-dblp'?'Source: OpenAIRE (ORCID and author-name search), preserving previously catalogued DBLP records.':source.source==='openalex+cached-dblp'?'Sources: OpenAlex and previously catalogued DBLP records.':'Source: DBLP computer science bibliography.')+' Last synchronized: '+(source.last_synced_utc||'not available')+' (UTC).';
   update();
 }).catch(err=>{
   status.textContent='The local bibliography could not be loaded.';
   selEl.textContent='Please visit DBLP for selected works.';
   note.textContent='To preview the site locally, run: python3 -m http.server 8080';
   console.error('Bibliography load failed',err);
 });
 [search,year,type].forEach(el=>el.addEventListener(el===search?'input':'change',()=>{limit=30;update()}));
 more.addEventListener('click',()=>{limit+=30;update()});
})();
