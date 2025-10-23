// Search Analytics Dashboard
// Fetches and visualizes search logs via Lambda proxy

// API Configuration
const ANALYTICS_API_URL = 'https://4v4og53bcl2ce6nbsgcy7krz5m0cxyaw.lambda-url.us-east-1.on.aws';

// Charts
let latencyChart, timingChart, overlapChart;

// Data cache
let searchData = [];

// ==========================================
// Data Fetching
// ==========================================

async function fetchSearchLogs(limit = 100) {
    try {
        const response = await fetch(`${ANALYTICS_API_URL}/?limit=${limit}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (!data.ok) {
            throw new Error(data.error || 'Failed to fetch search logs');
        }

        // Sort by timestamp descending (already sorted by backend but double-check)
        const items = data.items || [];
        items.sort((a, b) => b.timestamp - a.timestamp);

        return items;
    } catch (error) {
        console.error('Error fetching search logs:', error);
        throw error;
    }
}

// ==========================================
// Analytics Calculations
// ==========================================

function calculateStats(searches) {
    if (!searches || searches.length === 0) {
        return {
            total: 0,
            avgTime: 0,
            p95Time: 0,
            p99Time: 0,
            avgQuality: 0,
            errorRate: 0
        };
    }

    const times = searches.map(s => s.total_time_ms || 0).sort((a, b) => a - b);
    const qualities = searches.map(s => {
        const metrics = s.result_quality_metrics || {};
        return metrics.avg_feature_match_ratio || 0;
    });

    const errors = searches.filter(s => s.errors && s.errors.length > 0).length;

    return {
        total: searches.length,
        avgTime: Math.round(times.reduce((a, b) => a + b, 0) / times.length),
        p95Time: Math.round(times[Math.floor(times.length * 0.95)]),
        p99Time: Math.round(times[Math.floor(times.length * 0.99)]),
        avgQuality: (qualities.reduce((a, b) => a + b, 0) / qualities.length * 100).toFixed(1),
        errorRate: ((errors / searches.length) * 100).toFixed(1)
    };
}

function getTimingBreakdown(searches) {
    const components = [
        'constraint_extraction_ms',
        'embedding_generation_ms',
        'bm25_ms',
        'knn_text_ms',
        'knn_image_ms',
        'rrf_fusion_ms',
        'tag_boosting_ms'
    ];

    const averages = {};
    components.forEach(comp => {
        const values = searches
            .map(s => (s.timing || {})[comp] || 0)
            .filter(v => v > 0);
        averages[comp] = values.length > 0
            ? values.reduce((a, b) => a + b, 0) / values.length
            : 0;
    });

    return averages;
}

function getOverlapStats(searches) {
    const stats = {
        bm25_text: 0,
        bm25_image: 0,
        text_image: 0,
        all_three: 0
    };

    searches.forEach(s => {
        const overlap = s.result_overlap || {};
        stats.bm25_text += overlap.bm25_text_overlap || 0;
        stats.bm25_image += overlap.bm25_image_overlap || 0;
        stats.text_image += overlap.text_image_overlap || 0;
        stats.all_three += overlap.all_three_overlap || 0;
    });

    const total = searches.length;
    return {
        bm25_text: (stats.bm25_text / total).toFixed(1),
        bm25_image: (stats.bm25_image / total).toFixed(1),
        text_image: (stats.text_image / total).toFixed(1),
        all_three: (stats.all_three / total).toFixed(1)
    };
}

function getSlowSearches(searches, threshold = 2000) {
    return searches
        .filter(s => s.total_time_ms > threshold)
        .map(s => {
            const timing = s.timing || {};
            let slowest = { component: 'unknown', time: 0 };

            for (const [key, value] of Object.entries(timing)) {
                if (key !== 'total_ms' && key !== 'bedrock_embedding_calls' && value > slowest.time) {
                    slowest = { component: key, time: value };
                }
            }

            return {
                ...s,
                slowestComponent: slowest.component,
                slowestTime: slowest.time,
                slowestPercent: ((slowest.time / s.total_time_ms) * 100).toFixed(1)
            };
        })
        .sort((a, b) => b.total_time_ms - a.total_time_ms);
}

function getPoorQualitySearches(searches, threshold = 0.03) {
    return searches
        .filter(s => {
            const metrics = s.result_quality_metrics || {};
            return (metrics.avg_score || 0) < threshold;
        })
        .map(s => {
            const metrics = s.result_quality_metrics || {};
            const overlap = s.result_overlap || {};
            const issues = [];

            if ((metrics.avg_feature_match_ratio || 0) === 0) {
                const constraints = s.extracted_constraints || {};
                if (constraints.must_have && constraints.must_have.length > 0) {
                    issues.push('No feature matches');
                }
            }

            if ((overlap.all_three_overlap || 0) === 0) {
                issues.push('No strategy consensus');
            }

            if (s.warnings && s.warnings.length > 0) {
                issues.push(...s.warnings.map(w => w.message));
            }

            return {
                ...s,
                issues: issues.join(', ') || 'Low scores'
            };
        })
        .sort((a, b) => {
            const aScore = (a.result_quality_metrics || {}).avg_score || 0;
            const bScore = (b.result_quality_metrics || {}).avg_score || 0;
            return aScore - bScore;
        });
}

function assessQuality(search) {
    const metrics = search.result_quality_metrics || {};
    const overlap = search.result_overlap || {};
    const avgScore = metrics.avg_score || 0;
    const matchRatio = metrics.avg_feature_match_ratio || 0;
    const allThreeOverlap = overlap.all_three_overlap || 0;

    if (avgScore < 0.02) return 'poor';
    if (matchRatio === 0 && (search.extracted_constraints || {}).must_have && (search.extracted_constraints.must_have.length > 0)) return 'poor';
    if (allThreeOverlap === 0) return 'moderate';
    return 'good';
}

// ==========================================
// UI Updates
// ==========================================

function updateStats(stats) {
    document.getElementById('totalSearches').textContent = stats.total;
    document.getElementById('avgTime').textContent = stats.avgTime;
    document.getElementById('p95Time').textContent = stats.p95Time;
    document.getElementById('avgQuality').textContent = stats.avgQuality + '%';
}

function createLatencyChart(searches) {
    const ctx = document.getElementById('latencyChart').getContext('2d');

    // Create histogram bins
    const times = searches.map(s => s.total_time_ms || 0);
    const bins = [
        { label: '0-500ms', count: 0 },
        { label: '500-1000ms', count: 0 },
        { label: '1-2s', count: 0 },
        { label: '2-3s', count: 0 },
        { label: '3-5s', count: 0 },
        { label: '>5s', count: 0 }
    ];

    times.forEach(t => {
        if (t < 500) bins[0].count++;
        else if (t < 1000) bins[1].count++;
        else if (t < 2000) bins[2].count++;
        else if (t < 3000) bins[3].count++;
        else if (t < 5000) bins[4].count++;
        else bins[5].count++;
    });

    if (latencyChart) latencyChart.destroy();

    latencyChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: bins.map(b => b.label),
            datasets: [{
                label: 'Number of Searches',
                data: bins.map(b => b.count),
                backgroundColor: '#006aff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 1 }
                }
            }
        }
    });
}

function createTimingChart(timingBreakdown) {
    const ctx = document.getElementById('timingChart').getContext('2d');

    const labels = {
        'constraint_extraction_ms': 'Constraint Extraction',
        'embedding_generation_ms': 'Embedding Generation',
        'bm25_ms': 'BM25 Search',
        'knn_text_ms': 'kNN Text Search',
        'knn_image_ms': 'kNN Image Search',
        'rrf_fusion_ms': 'RRF Fusion',
        'tag_boosting_ms': 'Tag Boosting'
    };

    const data = Object.entries(timingBreakdown)
        .map(([key, value]) => ({
            label: labels[key] || key,
            value: Math.round(value)
        }))
        .filter(item => item.value > 0)
        .sort((a, b) => b.value - a.value);

    if (timingChart) timingChart.destroy();

    timingChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.label),
            datasets: [{
                label: 'Average Time (ms)',
                data: data.map(d => d.value),
                backgroundColor: [
                    '#006aff',
                    '#0080ff',
                    '#3399ff',
                    '#66b3ff',
                    '#99ccff',
                    '#cce6ff',
                    '#e6f2ff'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { beginAtZero: true }
            }
        }
    });
}

function createOverlapChart(overlapStats) {
    const ctx = document.getElementById('overlapChart').getContext('2d');

    if (overlapChart) overlapChart.destroy();

    overlapChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['BM25 ∩ Text', 'BM25 ∩ Image', 'Text ∩ Image', 'All Three'],
            datasets: [{
                label: 'Avg Overlap (properties)',
                data: [
                    parseFloat(overlapStats.bm25_text),
                    parseFloat(overlapStats.bm25_image),
                    parseFloat(overlapStats.text_image),
                    parseFloat(overlapStats.all_three)
                ],
                backgroundColor: '#006aff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
    return date.toLocaleDateString();
}

function updateRecentSearchesTable(searches) {
    const tbody = document.getElementById('searchTableBody');
    tbody.innerHTML = '';

    searches.slice(0, 20).forEach(search => {
        const quality = assessQuality(search);
        const metrics = search.result_quality_metrics || {};
        const counts = search.result_counts || {};

        const issues = [];
        if (search.errors && search.errors.length > 0) issues.push(`${search.errors.length} errors`);
        if (search.warnings && search.warnings.length > 0) issues.push(`${search.warnings.length} warnings`);

        const row = document.createElement('tr');
        row.className = 'clickable-row';
        row.innerHTML = `
            <td><div class="query-text" title="${search.query_text}">${search.query_text || 'N/A'}</div></td>
            <td><span class="time-badge">${formatTime(search.timestamp)}</span></td>
            <td>${Math.round(search.total_time_ms || 0)}ms</td>
            <td>${counts.final_returned || 0}</td>
            <td>${(metrics.avg_score || 0).toFixed(4)}</td>
            <td><span class="badge badge-${quality}">${quality}</span></td>
            <td>${issues.join(', ') || '-'}</td>
        `;
        row.onclick = () => showSearchDetails(search);
        tbody.appendChild(row);
    });
}

function updateSlowSearchesTable(slowSearches) {
    const tbody = document.getElementById('slowSearchesBody');
    tbody.innerHTML = '';

    if (slowSearches.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #999;">No slow searches found</td></tr>';
        return;
    }

    slowSearches.slice(0, 10).forEach(search => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><div class="query-text" title="${search.query_text}">${search.query_text || 'N/A'}</div></td>
            <td>${Math.round(search.total_time_ms)}ms</td>
            <td>${search.slowestComponent.replace('_ms', '').replace(/_/g, ' ')}</td>
            <td>${Math.round(search.slowestTime)}ms</td>
            <td>${search.slowestPercent}%</td>
        `;
        tbody.appendChild(row);
    });
}

function updatePoorQualityTable(poorSearches) {
    const tbody = document.getElementById('poorQualityBody');
    tbody.innerHTML = '';

    if (poorSearches.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #999;">No poor quality searches found</td></tr>';
        return;
    }

    poorSearches.slice(0, 10).forEach(search => {
        const metrics = search.result_quality_metrics || {};
        const overlap = search.result_overlap || {};

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><div class="query-text" title="${search.query_text}">${search.query_text || 'N/A'}</div></td>
            <td>${(metrics.avg_score || 0).toFixed(4)}</td>
            <td>${((metrics.avg_feature_match_ratio || 0) * 100).toFixed(0)}%</td>
            <td>BM25∩Text: ${overlap.bm25_text_overlap || 0}, All: ${overlap.all_three_overlap || 0}</td>
            <td>${search.issues}</td>
        `;
        tbody.appendChild(row);
    });
}

function showSearchDetails(search) {
    // For now, just log to console
    // In a full implementation, could show a modal with complete details
    console.log('Search Details:', search);
    alert(`Query ID: ${search.query_id}\n\nQuery: "${search.query_text}"\n\nClick OK to see details in console (F12)`);
}

function showError(message) {
    const container = document.getElementById('errorContainer');
    container.innerHTML = `<div class="error-message">⚠️ ${message}</div>`;
}

function clearError() {
    document.getElementById('errorContainer').innerHTML = '';
}

// ==========================================
// Main Load Function
// ==========================================

async function loadDashboard() {
    const refreshBtn = document.getElementById('refreshBtn');
    refreshBtn.disabled = true;
    refreshBtn.textContent = 'Loading...';
    clearError();

    try {
        // Fetch data
        searchData = await fetchSearchLogs(100);

        if (searchData.length === 0) {
            showError('No search data found. Make some searches first!');
            return;
        }

        // Calculate statistics
        const stats = calculateStats(searchData);
        updateStats(stats);

        // Update charts
        createLatencyChart(searchData);
        createTimingChart(getTimingBreakdown(searchData));
        createOverlapChart(getOverlapStats(searchData));

        // Update tables
        updateRecentSearchesTable(searchData);
        updateSlowSearchesTable(getSlowSearches(searchData, 2000));
        updatePoorQualityTable(getPoorQualitySearches(searchData, 0.03));

        console.log(`Loaded ${searchData.length} search logs`);

    } catch (error) {
        console.error('Error loading dashboard:', error);
        showError('Failed to load search data. Check console for details.');
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.textContent = 'Refresh Data';
    }
}

// ==========================================
// Event Listeners
// ==========================================

document.getElementById('refreshBtn').addEventListener('click', loadDashboard);

// Load on page load
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
});
