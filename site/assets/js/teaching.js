(function(){
 'use strict';
 const openButtons=document.querySelectorAll('[data-course-open]');
 let previousFocus=null;
 function closeDialog(dialog) {if(dialog?.open)dialog.close();}
 for(const button of openButtons){
   button.addEventListener('click',()=>{
     const dialog=document.getElementById('course-'+button.dataset.courseOpen);
     if(!dialog||typeof dialog.showModal!=='function')return;
     previousFocus=document.activeElement;
     dialog.showModal();
     dialog.querySelector('[data-course-close]')?.focus();
   });
 }
 for(const dialog of document.querySelectorAll('.course-dialog')){
   dialog.querySelector('[data-course-close]')?.addEventListener('click',()=>closeDialog(dialog));
   dialog.addEventListener('click',event=>{
      if(event.target===dialog)closeDialog(dialog);
   });
   dialog.addEventListener('close',()=>{
     if(previousFocus && previousFocus.isConnected) previousFocus.focus();
     previousFocus=null;
   });
 }
})();
