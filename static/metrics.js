(() => {
  const dataNode = document.getElementById("metrics-chart-data");
  if (!dataNode) return;
  const data = JSON.parse(dataNode.textContent),
    colors = [
      "#d9ae58",
      "#6ecf93",
      "#68b8d5",
      "#d66c62",
      "#a88bdd",
      "#e99bab",
      "#9ac5ed",
      "#d3d96c",
      "#e79c5f",
      "#63c5b5",
    ];
  function draw(canvasId, legendId, totalId, items, totalLabel) {
    const canvas = document.getElementById(canvasId),
      legend = document.getElementById(legendId),
      total = document.getElementById(totalId),
      context = canvas.getContext("2d");
    const sum = items.reduce((value, item) => value + item.value, 0),
      ratio = window.devicePixelRatio || 1,
      width = canvas.clientWidth,
      height = canvas.clientHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    const radius = Math.max(0, Math.min(width, height) / 2 - 5),
      centerX = width / 2,
      centerY = height / 2;
    if (sum) {
      let angle = -Math.PI / 2;
      items.forEach((item, index) => {
        if (item.value <= 0) return;
        const end = angle + (item.value / sum) * Math.PI * 2;
        context.beginPath();
        context.moveTo(centerX, centerY);
        context.arc(centerX, centerY, radius, angle, end);
        context.closePath();
        context.fillStyle = colors[index % colors.length];
        context.fill();
        angle = end;
      });
    } else {
      context.beginPath();
      context.arc(centerX, centerY, radius, 0, Math.PI * 2);
      context.fillStyle = "#27313d";
      context.fill();
    }
    legend.replaceChildren();
    items.forEach((item, index) => {
      const row = document.createElement("li"),
        swatch = document.createElement("span"),
        label = document.createElement("span"),
        value = document.createElement("strong");
      swatch.className = "metrics-chart-swatch";
      swatch.style.backgroundColor = colors[index % colors.length];
      label.textContent = item.label;
      value.textContent = String(item.value);
      row.append(swatch, label, value);
      legend.append(row);
    });
    total.textContent = sum + " " + totalLabel;
  }
  draw(
    "completed-cases-chart",
    "completed-cases-legend",
    "completed-cases-total",
    data.completed,
    "completed cases",
  );
  draw(
    "case-stage-chart",
    "case-stage-legend",
    "case-stage-total",
    data.stages,
    "cases",
  );
})();
