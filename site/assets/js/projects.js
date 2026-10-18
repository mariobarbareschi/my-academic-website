(function(){'use strict';
 const cards=[...document.querySelectorAll('.research-project-card')];
 const search=document.querySelector('#project-search');
 const buttons=[...document.querySelectorAll('.project-filter')];
 const count=document.querySelector('#project-result-count');
 const empty=document.querySelector('#project-no-results');
 let category='all';
 function update(){
   const q=(search?.value||'').trim().toLowerCase();let shown=0;
   cards.forEach(card=>{
      const ok=(category==='all'||card.dataset.category===category)&&(!q||(card.dataset.search||'').includes(q));
      card.hidden=!ok;
      if(ok)shown++;
   });
   if(count)count.textContent=shown+' of '+cards.length+' projects shown';
   if(empty)empty.hidden=shown!==0;
 }
 buttons.forEach(button=>button.addEventListener('click',()=>{
   category=button.dataset.filter||'all';
   buttons.forEach(x=>{const selected=x===button;x.classList.toggle('is-active',selected);x.setAttribute('aria-pressed',String(selected));});update();
 }));
 search?.addEventListener('input',update);
 update();
})();
