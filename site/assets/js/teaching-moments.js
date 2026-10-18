/* Simple accessible photo viewer; images remain local and static. */
(()=>{
  'use strict';
  const dialog=document.getElementById('moments-lightbox');
  const photo=dialog?.querySelector('#moment-large-photo');
  const counter=dialog?.querySelector('#moment-count');
  const triggers=[...document.querySelectorAll('[data-moment-index]')];
  if(!dialog || !photo || !counter || !triggers.length) return;
  const files=triggers.map((_,i)=>`assets/images/teaching-moments/class-${String(i+1).padStart(2,'0')}.webp`);
  let position=0, lastTrigger=null, startX=null;
  function show(i) {
    position=(i+files.length)%files.length;
    photo.src=files[position];
    photo.alt=`Group photograph from an end-of-course gathering, image ${position+1} of ${files.length}`;
    counter.textContent=`${position+1} / ${files.length}`;
  }
  triggers.forEach((button,i)=>button.addEventListener('click',()=>{
    lastTrigger=button;
    show(i);
    if(typeof dialog.showModal==='function') dialog.showModal();
    dialog.querySelector('.moments-close')?.focus();
  }));
  dialog.querySelector('.moments-close')?.addEventListener('click',()=>dialog.close());
  dialog.querySelector('.moments-arrow.prev')?.addEventListener('click',()=>show(position-1));
  dialog.querySelector('.moments-arrow.next')?.addEventListener('click',()=>show(position+1));
  dialog.addEventListener('keydown',event=>{
    if(event.key==='ArrowLeft'){event.preventDefault();show(position-1)}
    if(event.key==='ArrowRight'){event.preventDefault();show(position+1)}
  });
  dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close()});
  dialog.addEventListener('close',()=>{photo.removeAttribute('src');lastTrigger?.focus();});
  dialog.addEventListener('touchstart',event=>{startX=event.changedTouches[0].screenX},{passive:true});
  dialog.addEventListener('touchend',event=>{
    if(startX===null)return;
    const dx=event.changedTouches[0].screenX-startX;
    if(Math.abs(dx)>55)show(position+(dx>0?-1:1));
    startX=null;
  },{passive:true});
})();
