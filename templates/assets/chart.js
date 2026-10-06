// 銘柄チャートのホバー（クロスヘア＋ツールチップ）
(function () {
  document.querySelectorAll('.chart-box').forEach(function (box) {
    var svg = box.querySelector('svg.chart');
    var data = JSON.parse(box.querySelector('script[type="application/json"]').textContent);
    var tip = box.querySelector('.tip');
    var cross = svg.querySelector('.cross');
    var hit = svg.querySelector('.hit');
    var n = data.dates.length;
    var fmt = function (v) { return v == null ? '—' : v.toLocaleString(undefined, {maximumFractionDigits: 2}); };
    function show(evt) {
      var pt = evt.touches ? evt.touches[0] : evt;
      var r = svg.getBoundingClientRect();
      var sx = (pt.clientX - r.left) * data.w / r.width;
      var i = Math.max(0, Math.min(n - 1, Math.floor((sx - data.x0) / data.pw * n)));
      var cx = data.x0 + data.pw * (i + 0.5) / n;
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('visibility', 'visible');
      tip.innerHTML = '<b>' + data.dates[i] + '</b><br>' +
        '<i style="background:var(--series-1)"></i>終値 ' + fmt(data.close[i]) + '<br>' +
        '<i style="background:var(--series-2)"></i>' + data.ls + ' ' + fmt(data.sma_s[i]) + '<br>' +
        '<i style="background:var(--series-3)"></i>' + data.ll + ' ' + fmt(data.sma_l[i]) + '<br>' +
        '出来高 ' + fmt(data.vol[i]);
      tip.style.display = 'block';
      var px = cx / data.w * r.width;
      var left = px + 12 + tip.offsetWidth > r.width ? px - 12 - tip.offsetWidth : px + 12;
      tip.style.left = (left + 8) + 'px';
    }
    function hide() { tip.style.display = 'none'; cross.setAttribute('visibility', 'hidden'); }
    hit.addEventListener('mousemove', show);
    hit.addEventListener('touchstart', show, {passive: true});
    hit.addEventListener('touchmove', show, {passive: true});
    hit.addEventListener('mouseleave', hide);
    hit.addEventListener('touchend', function () { setTimeout(hide, 1500); });
  });
})();
