(function(){
  'use strict';
  const trigger=document.querySelector('.mobile-trigger');
  const sidebar=document.querySelector('.site-sidebar');
  const scrim=document.querySelector('.menu-scrim');
  function toggle(open){
    if(!sidebar||!trigger||!scrim)return;
    sidebar.classList.toggle('open',open);
    scrim.classList.toggle('active',open);
    trigger.setAttribute('aria-expanded',String(open));
    trigger.setAttribute('aria-label',open?'Close navigation':'Open navigation');
    document.body.style.overflow=open?'hidden':'';
  }
  trigger?.addEventListener('click',()=>toggle(!sidebar.classList.contains('open')));
  scrim?.addEventListener('click',()=>toggle(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape')toggle(false)});
  sidebar?.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>toggle(false)));


// The same navigation markup is used on every page. A real indicator
// element allows compatible browsers to move it between documents.
const nav = document.querySelector('.side-nav');
const currentNavLink = nav?.querySelector('a[aria-current="page"]');
if (nav && currentNavLink) {
  const indicator = document.createElement('span');
  indicator.className = 'nav-active-indicator';
  indicator.setAttribute('aria-hidden', 'true');
  nav.prepend(indicator);
  function positionIndicator() {
    indicator.style.top = currentNavLink.offsetTop + 'px';
    indicator.style.height = currentNavLink.offsetHeight + 'px';
  }
  positionIndicator();
  window.addEventListener('resize', positionIndicator, {passive:true});
}

// Keep ordinary links, back/forward, external destinations and downloads
// intact. The fallback is needed in particular for local file:// previews.
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const nativeCrossDocument = ('onpageswap' in window) &&
                            ('onpagereveal' in window) &&
                            CSS.supports('view-transition-name: page-content') &&
                            location.protocol !== 'file:';
const fallback = !nativeCrossDocument;
const storageKey = 'mb-page-nav-start';
function saveNavigationTime() {
  try { sessionStorage.setItem(storageKey, String(Date.now())); } catch (_) {}
}
function consumeNavigationTime() {
  try {
    const time = Number(sessionStorage.getItem(storageKey));
    sessionStorage.removeItem(storageKey);
    return Number.isFinite(time) && Date.now() - time < 4000;
  } catch (_) { return false; }
}
if (fallback && !reduceMotion.matches && consumeNavigationTime()) {
  document.documentElement.classList.add('page-entering');
  document.querySelector('.site-main')?.addEventListener('animationend', () => {
    document.documentElement.classList.remove('page-entering');
  }, {once: true});
} else {
  consumeNavigationTime();
}
let leaving = false;
document.addEventListener('click', event => {
  if (!fallback || reduceMotion.matches || leaving || event.defaultPrevented ||
      event.button !== 0 || event.metaKey || event.ctrlKey ||
      event.shiftKey || event.altKey) return;
  const link = event.target.closest?.('a[href]');
  if (!link || link.hasAttribute('download') || link.target === '_blank') return;
  let destination;
  try { destination = new URL(link.href, location.href); } catch (_) { return; }
  if (destination.origin !== location.origin ||
      !/\.html?$/i.test(destination.pathname) ||
      (destination.pathname === location.pathname &&
       destination.search === location.search)) return;
  event.preventDefault();
  leaving = true;
  saveNavigationTime();
  document.documentElement.classList.add('page-leaving');
  window.setTimeout(() => { window.location.assign(destination.href); }, document.documentElement.classList.contains('home-page') ? 560 : 155);
});
window.addEventListener('pageshow', () => {
  document.documentElement.classList.remove('page-leaving');
  leaving = false;
});
})();
