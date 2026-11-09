/** Shared (server + client): runs before first paint so the page never flashes the wrong theme. */
export const THEME_KEY = "matchbook:theme";
export const THEME_BOOT = `try{var t=localStorage.getItem("${THEME_KEY}");document.documentElement.dataset.theme=t==="ramp"?"ramp":"editorial"}catch(e){document.documentElement.dataset.theme="editorial"}`;
