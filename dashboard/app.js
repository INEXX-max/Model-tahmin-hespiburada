// app.js

document.getElementById('excelUpload').addEventListener('change', handleFile, false);

let chartInstances = {};

function formatMoney(amount) {
    return amount.toLocaleString('tr-TR', { maximumFractionDigits: 0 }) + ' ₺';
}

function animateValue(obj, start, end, duration) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const current = Math.floor(progress * (end - start) + start);
        obj.innerHTML = formatMoney(current);
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    document.getElementById('loader').classList.remove('hidden');
    document.getElementById('dashboardContent').classList.add('hidden');

    const reader = new FileReader();
    reader.onload = function(e) {
        const data = new Uint8Array(e.target.result);
        const workbook = XLSX.read(data, { type: 'array' });
        
        processData(workbook);
        
        document.getElementById('loader').classList.add('hidden');
        document.getElementById('dashboardContent').classList.remove('hidden');
    };
    reader.readAsArrayBuffer(file);
}

function processData(workbook) {
    // 1. Özet Sayfası
    const summarySheet = workbook.Sheets['Özet'];
    if (summarySheet) {
        const summaryData = XLSX.utils.sheet_to_json(summarySheet);
        
        let totalCost = 0;
        let kiralikCost = 0;
        let spotCost = 0;
        let routeCount = 0;
        let dayCount = 0;
        let tripCount = 0;

        summaryData.forEach(row => {
            if (row['Metrik'] === 'Toplam Maliyet (TL)') totalCost = row['Değer'];
            if (row['Metrik'] === 'Toplam Kiralık Maliyet (TL)') kiralikCost = row['Değer'];
            if (row['Metrik'] === 'Toplam Spot Maliyet (TL)') spotCost = row['Değer'];
            if (row['Metrik'] === 'Toplam Guzergah Sayisi') routeCount = row['Değer'];
            if (row['Metrik'] === 'Toplam Gun Sayisi') dayCount = row['Değer'];
            if (row['Metrik'] === 'Toplam Kayit Sayisi') tripCount = row['Değer'];
        });

        // Animasyonlu KPI Güncelleme
        animateValue(document.getElementById('totalCost'), 0, totalCost, 2000);
        animateValue(document.getElementById('kiralikCost'), 0, kiralikCost, 1500);
        animateValue(document.getElementById('spotCost'), 0, spotCost, 1500);

        document.getElementById('routeCount').innerText = routeCount;
        document.getElementById('dayCount').innerText = dayCount;
        document.getElementById('tripCount').innerText = tripCount;

        // Progress Barlar
        setTimeout(() => {
            const kiralikPct = (kiralikCost / totalCost) * 100;
            const spotPct = (spotCost / totalCost) * 100;
            document.getElementById('kiralikBar').style.width = `${kiralikPct}%`;
            document.getElementById('spotBar').style.width = `${spotPct}%`;
        }, 500);

        // Chart 1: Maliyet Dağılımı (Doughnut)
        renderCostChart(kiralikCost, spotCost);
    }

    // 2. Analiz_Yogunluk Sayfası
    const densitySheet = workbook.Sheets['Analiz_Yogunluk'];
    if (densitySheet) {
        const densityData = XLSX.utils.sheet_to_json(densitySheet);
        const top5 = densityData.slice(0, 5);
        renderDensityChart(top5);
    }

    // 3. Filo_Kaydirma Sayfası
    const feedSheet = workbook.Sheets['Filo_Kaydirma'];
    if (feedSheet) {
        const feedData = XLSX.utils.sheet_to_json(feedSheet);
        renderLiveFeed(feedData.slice(0, 30)); // İlk 30 kaydı canlandır
    }
}

function renderCostChart(kiralik, spot) {
    const ctx = document.getElementById('costChart').getContext('2d');
    
    if(chartInstances.cost) chartInstances.cost.destroy();

    chartInstances.cost = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Kiralık Havuzu', 'Spot (Dış Kaynak)'],
            datasets: [{
                data: [kiralik, spot],
                backgroundColor: ['#00e676', '#ff9100'],
                borderWidth: 0,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: { position: 'bottom', labels: { color: '#8b9bb4' } }
            }
        }
    });
}

function renderDensityChart(data) {
    const ctx = document.getElementById('densityChart').getContext('2d');
    
    if(chartInstances.density) chartInstances.density.destroy();

    const labels = data.map(d => `${d['Cikis']} \u2192 ${d['Varis']}`);
    const values = data.map(d => d['Toplam Talep Desi']);

    chartInstances.density = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Taşınan Toplam Hacim (Desi)',
                data: values,
                backgroundColor: 'rgba(0, 210, 255, 0.6)',
                borderColor: '#00d2ff',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8b9bb4' } },
                x: { grid: { display: false }, ticks: { color: '#8b9bb4', maxRotation: 45, minRotation: 45 } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

function renderLiveFeed(feedData) {
    const list = document.getElementById('fleetFeed');
    list.innerHTML = ''; // Temizle

    feedData.forEach((item, index) => {
        // Tarihi düzelt
        let dateStr = item['Tarih'];
        if (typeof dateStr === 'number') {
            const date = new Date(Math.round((dateStr - 25569) * 86400 * 1000));
            dateStr = date.toLocaleDateString('tr-TR');
        }

        const type = item['Araç Türü'] || 'Bilinmiyor';
        let badgeClass = 'badge-diger';
        if(type.includes('Tır')) badgeClass = 'badge-tir';
        else if(type.includes('Kamyon')) badgeClass = 'badge-kamyon';

        const li = document.createElement('li');
        li.className = 'feed-item';
        li.style.animationDelay = `${index * 0.15}s`; // Stagger effect

        li.innerHTML = `
            <div>${dateStr}</div>
            <div class="${badgeClass} font-bold">${type} (x${item['Adet']})</div>
            <div>
                ${item['Kaynak Güzergah']}
                <span class="route-arrow">\u2192</span>
                <span style="color: #fff">${item['Hedef Güzergah']}</span>
            </div>
        `;
        list.appendChild(li);
    });
}
