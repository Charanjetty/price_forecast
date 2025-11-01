// app.js - Way2Agri dashboard front-end
// Expects backend JSON from /predict/ with:
// { current_price: number,
//   metrics: {mae, rmse, accuracy, confidence},
//   history: [{date:'YYYY-MM-DD', actual: num, predicted: num}, ...],
//   forecast: [{date:'YYYY-MM-DD', forecast: num, change_pct: num}, ...],
//   avg_forecast: number
// }

async function fetchForecast(uploadFile) {
  // prepare formdata if file provided
  let url = '/predict/';
  let options = { method: 'GET' };
  if (uploadFile) {
    // send CSV via POST multipart if user uploaded
    const fd = new FormData();
    fd.append('file', uploadFile);
    options = { method: 'POST', body: fd };
  }
  const r = await fetch(url, options);
  if (!r.ok) {
    const txt = await r.text();
    console.error('Server error', txt);
    throw new Error('Server error: ' + r.status);
  }
  return await r.json();
}

function isoDate(d){ // for display, keep YYYY-MM-01
  return d.split('T')[0];
}

function renderMetrics(metrics, currentPrice, avgForecast) {
  document.getElementById('currentPrice').textContent = currentPrice ? `₹${currentPrice.toFixed(2)}` : '—';
  document.getElementById('avgForecast').textContent = avgForecast ? `₹${avgForecast.toFixed(2)}` : '—';
  const trend = metrics && metrics.trend_pct ? metrics.trend_pct : null;
  const trendEl = document.getElementById('trendPercent');
  if (trend !== null) {
    const sign = trend >= 0 ? '+' : '';
    trendEl.innerHTML = `<span class="${trend >= 0 ? 'change-up' : 'change-down'}">${sign}${trend.toFixed(1)}%</span>`;
  } else {
    trendEl.textContent = '—';
  }
}

function buildForecastTable(forecast) {
  const tbody = document.querySelector('#forecastTable tbody');
  tbody.innerHTML = '';
  forecast.forEach(row => {
    const tr = document.createElement('tr');
    const d = document.createElement('td');
    d.textContent = row.date.split('T')[0];
    const p = document.createElement('td');
    p.textContent = `₹${row.forecast.toFixed(2)}`;
    const c = document.createElement('td');
    c.textContent = `${row.change_pct >= 0 ? '+' : ''}${row.change_pct.toFixed(1)}%`;
    c.className = row.change_pct >= 0 ? 'change-up' : 'change-down';
    tr.append(d,p,c);
    tbody.append(tr);
  });
}

function drawPlot(history, forecast) {
  // combine history (actual) and forecast for continuity
  const histX = history.map(r=>r.date);
  const histY = history.map(r=>r.actual);

  const forecastX = forecast.map(r=>r.date);
  const forecastY = forecast.map(r=>r.forecast);

  const traceHist = {
    x: histX,
    y: histY,
    mode: 'lines',
    name: 'Historical',
    line: { color: '#0b6b3a' }
  };
  const traceForecast = {
    x: forecastX,
    y: forecastY,
    mode: 'lines+markers',
    name: 'Forecast',
    line: { color: '#00a86b', dash: 'dot' },
    marker: { size:6 }
  };

  const layout = {
    margin: { t: 30, r: 20, l: 60, b: 50 },
    xaxis: { title: 'Date' },
    yaxis: { title: 'Price (₹)' },
    legend: { orientation: 'h', x: 0.02, y: 1.08 }
  };

  Plotly.newPlot('chartArea', [traceHist, traceForecast], layout, {responsive:true});
}

document.addEventListener('DOMContentLoaded', function(){
  const predictBtn = document.getElementById('predictBtn');
  const refreshBtn = document.getElementById('refreshBtn');
  const csvFile = document.getElementById('csvFile');

  async function doFetch() {
    try {
      predictBtn.disabled = true;
      predictBtn.textContent = 'Predicting…';
      const file = csvFile.files.length ? csvFile.files[0] : null;
      const j = await fetchForecast(file);
      // expected structure check
      renderMetrics(j.metrics || {}, j.current_price, j.avg_forecast || null);
      buildForecastTable(j.forecast || []);
      drawPlot(j.history || [], j.forecast || []);
    } catch (err) {
      alert('Prediction failed: ' + (err.message || err));
      console.error(err);
    } finally {
      predictBtn.disabled = false;
      predictBtn.textContent = 'Predict Next 12 Months';
    }
  }

  predictBtn.addEventListener('click', doFetch);
  refreshBtn.addEventListener('click', () => location.reload());
});
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("predictForm");
    const resultSection = document.getElementById("resultSection");
    const priceDisplay = document.getElementById("predictedPrice");

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const month = document.getElementById("month").value;

        if (!month) return alert("Please select a month.");

        const response = await fetch(`/predict/?month=${month}`);
        const data = await response.json();

        // Display predicted price
        priceDisplay.textContent = `₹${data.predicted_price.toFixed(2)}`;
        resultSection.style.display = "block";

        // Update metrics
        document.getElementById("accuracy").textContent = `${data.accuracy}%`;
        document.getElementById("mae").textContent = `₹${data.mae.toFixed(2)}`;
        document.getElementById("confidence").textContent = `${data.confidence}%`;

        // Draw charts
        drawCharts(data.history);
    });
});

function drawCharts(history) {
    const ctx1 = document.getElementById("trendChart").getContext("2d");
    const ctx2 = document.getElementById("barChart").getContext("2d");

    const labels = history.map(item => item.date);
    const actuals = history.map(item => item.actual);
    const preds = history.map(item => item.predicted);

    new Chart(ctx1, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: "Actual Price",
                    data: actuals,
                    borderColor: "#28a745",
                    tension: 0.4,
                    fill: false
                },
                {
                    label: "Predicted Price",
                    data: preds,
                    borderColor: "#00a86b",
                    borderDash: [5,5],
                    tension: 0.4,
                    fill: false
                }
            ]
        },
        options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
    });

    new Chart(ctx2, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: "Forecasted Price (₹)",
                data: preds,
                backgroundColor: "#00a86b"
            }]
        },
        options: { responsive: true, scales: { y: { beginAtZero: true } } }
    });
}
