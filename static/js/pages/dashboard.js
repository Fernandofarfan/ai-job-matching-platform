document.addEventListener("DOMContentLoaded", async function() {
    try {
        const response = await fetch('/api/analytics/funnel');
        const data = await response.json();

        if (data.success) {
            document.getElementById('countersRow').style.display = 'flex';

            // Populate Counters
            document.getElementById('kpiFound').innerText = data.funnel.found;
            document.getElementById('kpiApplied').innerText = data.funnel.applied;
            document.getElementById('kpiInterviews').innerText = data.funnel.interviews;
            document.getElementById('kpiOffers').innerText = data.funnel.offers;

            // Bar Chart (Funnel representation)
            const ctxFunnel = document.getElementById('funnelChart').getContext('2d');
            new Chart(ctxFunnel, {
                type: 'bar',
                data: {
                    labels: ['Oportunidades Encontradas', 'CVs Enviados', 'Llamadas/Entrevistas', 'Ofertas / Finalistas'],
                    datasets: [{
                        label: 'Volumen',
                        data: [data.funnel.found, data.funnel.applied, data.funnel.interviews, data.funnel.offers],
                        backgroundColor: [
                            'rgba(13, 110, 253, 0.5)',  // Primary
                            'rgba(13, 202, 240, 0.5)',  // Info
                            'rgba(255, 193, 7, 0.5)',   // Warning
                            'rgba(25, 135, 84, 0.5)'    // Success
                        ],
                        borderColor: [
                            'rgb(13, 110, 253)',
                            'rgb(13, 202, 240)',
                            'rgb(255, 193, 7)',
                            'rgb(25, 135, 84)'
                        ],
                        borderWidth: 1,
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(255,255,255,0.1)' },
                            ticks: { color: '#adb5bd' }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#adb5bd' }
                        }
                    },
                    plugins: {
                        legend: { display: false }
                    }
                }
            });

            // Pie Chart (Raw Status)
            const pureStats = data.raw_stats;
            const labels = Object.keys(pureStats);
            const values = Object.values(pureStats);

            const ctxPie = document.getElementById('pieChart').getContext('2d');
            new Chart(ctxPie, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: [
                            '#0d6efd', '#6c757d', '#198754', '#dc3545', '#ffc107', '#0dcaf0'
                        ],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#adb5bd' }
                        }
                    }
                }
            });
        }
    } catch (e) {
        console.error("Error cargando dashboard:", e);
    }
});
async function loadPortalStats() {
    try {
        const response = await fetch('/api/analytics/advanced');
        const data = await response.json();
        if (!data.success || !data.by_portal || data.by_portal.length === 0) return;
        const tbody = document.querySelector('#portal-table tbody');
        tbody.replaceChildren(...data.by_portal.map(p => {
            const tr = document.createElement('tr');
            const th = document.createElement('th');
            th.scope = 'row';
            th.textContent = p.portal;
            tr.appendChild(th);
            [p.saved, p.applied, p.responses, `${p.response_rate}%`].forEach(value => {
                const td = document.createElement('td');
                td.className = 'text-end';
                td.textContent = value;
                tr.appendChild(td);
            });
            return tr;
        }));
        if (data.avg_days_to_apply !== null && data.avg_days_to_apply !== undefined) {
            document.getElementById('avg-days-to-apply').textContent =
                `Postulás en promedio ${data.avg_days_to_apply} días después de guardar una oferta`;
        }
        document.getElementById('portal-row').style.display = '';
    } catch (e) {
        console.error("Error cargando el rendimiento por portal:", e);
    }
}
document.addEventListener("DOMContentLoaded", loadPortalStats);
