
/* Global Plotly dark defaults + colorway from CSS variables */
(function(){
  function cssVar(name, fallback){
    try{ return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback; }
    catch(e){ return fallback; }
  }
  const colorway = [
    cssVar("--bn-primary", "#4cc9f0"),
    cssVar("--bn-accent", "#f72585"),
    cssVar("--bn-success", "#2dc653"),
    cssVar("--bn-warning", "#f9c74f"),
    cssVar("--bn-danger",  "#f94144"),
    "#a0aec0"
  ];

  window.BYTEPLOT = {
    layout: {
      paper_bgcolor:"rgba(0,0,0,0)",
      plot_bgcolor:"rgba(0,0,0,0)",
      font:{ color: cssVar("--bn-text", "#e6edf3") },
      xaxis:{ gridcolor:"#1f2746", zerolinecolor:"#1f2746" },
      yaxis:{ gridcolor:"#1f2746", zerolinecolor:"#1f2746" },
      colorway: colorway,
      margin:{l:40,r:10,t:10,b:40},
      legend:{ bgcolor:"rgba(0,0,0,0)" }
    },
    config:{ displayModeBar:false, responsive:true }
  };

  // Monkey-patch Plotly.newPlot to merge defaults (non-destructive)
  const _ready = () => {
    if(!window.Plotly || window.Plotly.__byteneko_patched) return;
    const orig = window.Plotly.newPlot;
    window.Plotly.newPlot = function(el, data, layout, config){
      const L = Object.assign({}, BYTEPLOT.layout, (layout||{}));
      const C = Object.assign({}, BYTEPLOT.config, (config||{}));
      return orig.apply(this, [el, data, L, C]);
    };
    window.Plotly.__byteneko_patched = true;
  };
  if(document.readyState === "complete" || document.readyState === "interactive"){ _ready(); }
  else { document.addEventListener("DOMContentLoaded", _ready); }
})();
