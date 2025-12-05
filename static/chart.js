<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const chartLabels = {{ member_labels | tojson }};
const chartData = {{ member_balances | tojson }};
let chartType = 'bar';
let balanceChart;

const ctx = document.getElementById('balanceChart').getContext('2d');

function renderChart(type) {
  if (balanceChart) {
    balanceChart.destroy();
  }
  balanceChart = new Chart(ctx, {
    type: type,
    data: {
      labels: chartLabels,
      datasets: [{
        label: type === 'bar' ? 'Balance ($)' : '',
        data: chartData,
        borderWidth: 1,
        backgroundColor: [
          'rgba(75, 192, 192, 0.5)',
          'rgba(255, 99, 132, 0.5)',
          'rgba(255, 206, 86, 0.5)',
          'rgba(54, 162, 235, 0.5)',
          'rgba(153, 102, 255, 0.5)',
          'rgba(255, 159, 64, 0.5)'
        ]
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: type === 'bar' ? {
        y: { beginAtZero: true }
      } : {}
    }
  });
}

renderChart(chartType);

document.getElementById('chartType').addEventListener('change', function() {
  chartType = this.value;
  renderChart(chartType);
});
</script>
