/* surveys/static/surveys/results.js */
document.addEventListener("DOMContentLoaded", function(){
  // Read data embedded in dataset attributes on container
  const container = document.querySelector("[data-results]");
  if(!container || typeof Plotly === "undefined") return;

  const dataObj = JSON.parse(container.dataset.results);

  // Preferences bar chart
  (function(){
    const labels = dataObj.top_preferences.map(i => i.label);
    const values = dataObj.top_preferences.map(i => i.value);
    const trace = {
      x: labels, y: values, type: "bar", hoverinfo:"x+y",
      marker: { /* no explicit colors per style guide; let Plotly default */ }
    };
    const layout = {
      margin:{l:40,r:10,t:10,b:40},
      paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)",
      xaxis:{tickfont:{color:"#cfd8ff"}},
      yaxis:{tickfont:{color:"#cfd8ff"}, gridcolor:"#1f2746"},
    };
    Plotly.newPlot("prefBar", [trace], layout, {displayModeBar:false, responsive:true});
  })();

  // Status donut
  (function(){
    const labels = dataObj.status_breakdown.map(i => i.label);
    const values = dataObj.status_breakdown.map(i => i.value);
    const trace = {
      labels, values, type:"pie", hole:0.55, sort:false
    };
    const layout = {
      margin:{l:10,r:10,t:10,b:10},
      paper_bgcolor:"rgba(0,0,0,0)",
      plot_bgcolor:"rgba(0,0,0,0)",
      showlegend:true, legend:{font:{color:"#cfd8ff"}}
    };
    Plotly.newPlot("statusDonut",[trace], layout, {displayModeBar:false, responsive:true});
  })();

  // Trend lines
  (function(){
    const labels = dataObj.trend.labels;
    const total = dataObj.trend.total;
    const completed = dataObj.trend.completed;
    const tr1 = { x: labels, y: total, name:"Total", type:"scatter" };
    const tr2 = { x: labels, y: completed, name:"Completadas", type:"scatter" };
    const layout = {
      margin:{l:40,r:10,t:10,b:40},
      paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)",
      xaxis:{tickfont:{color:"#cfd8ff"}},
      yaxis:{tickfont:{color:"#cfd8ff"}, gridcolor:"#1f2746"},
      legend:{font:{color:"#cfd8ff"}}
    };
    Plotly.newPlot("trendLines",[tr1,tr2], layout, {displayModeBar:false, responsive:true});
  })();

  // Satisfaction distribution (bar)
  (function(){
    const labels = dataObj.satisfaction_dist.map(i => i.range);
    const values = dataObj.satisfaction_dist.map(i => i.count);
    Plotly.newPlot("satDist", [{
      x: labels, y: values, type:"bar"
    }], {
      margin:{l:40,r:10,t:10,b:40},
      paper_bgcolor:"rgba(0,0,0,0)", plot_bgcolor:"rgba(0,0,0,0)",
      xaxis:{tickfont:{color:"#cfd8ff"}},
      yaxis:{tickfont:{color:"#cfd8ff"}, gridcolor:"#1f2746"}
    }, {displayModeBar:false, responsive:true});
  })();
});