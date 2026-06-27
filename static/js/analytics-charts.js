/**
 * Analytics sub-tab charts — lazy-rendered, theme-aware visualizations.
 * Depends on globals from dashboard.js (chartTheme, uiScale, cssVar, etc.).
 */
const AnalyticsCharts = (() => {
    const ANALYTICS_PANES = ["performance", "risk", "exposure", "signals", "markets"];
    let activePane = "performance";
    const rendered = new Set(["performance"]);
    let contributionPeriod = "day";

    let riskRewardChart = null;
    let correlationChart = null;
    let drawdownChart = null;
    let treemapChart = null;
    let analystChart = null;

    let _tapeRaf = null;
    let _tapePaused = false;
    let _tapeInView = true;
    let _cachedMarkets = [];

    const $ = (id) => document.getElementById(id);

    function token(name, fallback) {
        const v = typeof cssVar === "function" ? cssVar(name) : "";
        return v || fallback;
    }

    function showLoading(id, on) {
        const el = $(id);
        if (el) {
            el.style.display = on ? "" : "none";
            el.setAttribute("aria-hidden", on ? "false" : "true");
        }
    }

    function showEmpty(id, on) {
        const el = $(id);
        if (el) el.style.display = on ? "" : "none";
    }

    function actionColor(action) {
        const a = (action || "hold").toLowerCase();
        if (a === "buy" || a === "add") return token("--accent-green", "#30d158");
        if (a === "trim" || a === "sell") return token("--accent-red", "#ff453a");
        return token("--accent-cyan", "#64d2ff");
    }

    function corrColor(value) {
        const t = Math.max(-1, Math.min(1, value));
        if (t >= 0) {
            const alpha = 0.15 + t * 0.75;
            return `color-mix(in srgb, var(--accent-red) ${Math.round(alpha * 100)}%, transparent)`;
        }
        const alpha = 0.15 + Math.abs(t) * 0.75;
        return `color-mix(in srgb, var(--accent-blue) ${Math.round(alpha * 100)}%, transparent)`;
    }

    function registerPlugins() {
        if (typeof Chart === "undefined") return;
        const matrix = window.ChartMatrix || window["chartjs-chart-matrix"];
        if (matrix?.MatrixController) {
            Chart.register(matrix.MatrixController, matrix.MatrixElement);
        }
        const treemap = window.ChartTreemap || window["chartjs-chart-treemap"];
        if (treemap?.TreemapController) {
            Chart.register(treemap.TreemapController, treemap.TreemapElement);
        }
    }

    function syncSubPaneIndicator() {
        const track = $("analytics-zone-tabs");
        if (!track) return;
        track.dataset.activePane = activePane;
        track.querySelectorAll(".analytics-zone-tab").forEach(btn => {
            const on = btn.dataset.analyticsPane === activePane;
            btn.classList.toggle("is-active", on);
            btn.setAttribute("aria-selected", String(on));
        });
        document.querySelectorAll(".analytics-sub-pane").forEach(pane => {
            const on = pane.dataset.analyticsPane === activePane;
            pane.classList.toggle("is-active", on);
            pane.hidden = !on;
        });
    }

    function setSubPane(pane) {
        if (!ANALYTICS_PANES.includes(pane)) pane = "performance";
        if (pane === activePane) return;
        activePane = pane;
        syncSubPaneIndicator();
        if (!rendered.has(pane)) {
            rendered.add(pane);
            loadPane(pane);
        } else if (pane === "markets") {
            refreshMarketsTape(_cachedMarkets);
        }
        requestAnimationFrame(resizeCharts);
    }

    function initSubTabs() {
        const track = $("analytics-zone-tabs");
        if (!track) return;
        track.querySelectorAll("[data-analytics-pane]").forEach(btn => {
            btn.addEventListener("click", () => setSubPane(btn.dataset.analyticsPane));
        });
        syncSubPaneIndicator();

        const periodGroup = $("contribution-period-tabs");
        periodGroup?.querySelectorAll("[data-period]").forEach(btn => {
            btn.addEventListener("click", () => {
                contributionPeriod = btn.dataset.period || "day";
                periodGroup.dataset.activePeriod = contributionPeriod;
                periodGroup.querySelectorAll(".contribution-period-btn").forEach(b => {
                    const on = b.dataset.period === contributionPeriod;
                    b.classList.toggle("is-active", on);
                    b.setAttribute("aria-pressed", String(on));
                });
                loadContributionChart();
            });
        });
    }

    function loadPane(pane) {
        switch (pane) {
            case "risk": return loadRiskPane();
            case "exposure": return loadExposurePane();
            case "signals": return loadSignalsPane();
            case "markets": return loadMarketsPane();
            default: break;
        }
    }

    async function loadRiskPane() {
        await Promise.all([
            loadRiskRewardChart(),
            loadCorrelationChart(),
            loadConcentrationGauge(),
            loadDrawdownChart(),
        ]);
    }

    async function loadExposurePane() {
        await Promise.all([loadSectorTreemap(), loadGeoExposure()]);
    }

    async function loadSignalsPane() {
        await Promise.all([
            loadContributionChart(),
            loadSignalBoard(),
            loadAnalystScorecard(),
        ]);
    }

    async function loadMarketsPane() {
        await refreshMarketsFromApi();
    }

    async function loadRiskRewardChart() {
        showLoading("risk-reward-loading", true);
        showEmpty("risk-reward-empty", false);
        try {
            const [riskRes, sigRes] = await Promise.all([
                fetch("/api/portfolio/risk-metrics"),
                fetch(`/api/ai/investment-signals/all${window._forcedLocalMode ? "?force_local=true" : ""}`),
            ]);
            const data = await riskRes.json();
            const sigData = sigRes.ok ? await sigRes.json() : {};
            const signals = sigData.signals || {};

            if (!data.has_data) {
                showEmpty("risk-reward-empty", true);
                riskRewardChart?.destroy();
                riskRewardChart = null;
                return;
            }

            data.holdings.forEach(h => {
                if (!h.action && signals[h.ticker]) h.action = signals[h.ticker].action;
            });

            const theme = chartTheme();
            const scale = uiScale();
            const ctx = $("risk-reward-chart")?.getContext("2d");
            if (!ctx) return;

            const holdings = data.holdings.map(h => ({
                x: h.annual_vol_pct,
                y: h.annual_return_pct,
                r: Math.max(6, Math.min(28, h.allocation_pct * 0.55)),
                ticker: h.ticker,
                action: h.action,
            }));

            const refs = [];
            if (data.portfolio) {
                refs.push({
                    x: data.portfolio.annual_vol_pct,
                    y: data.portfolio.annual_return_pct,
                    r: 12,
                    label: data.portfolio.label,
                    kind: "portfolio",
                });
            }
            if (data.benchmark) {
                refs.push({
                    x: data.benchmark.annual_vol_pct,
                    y: data.benchmark.annual_return_pct,
                    r: 10,
                    label: data.benchmark.label,
                    kind: "benchmark",
                });
            }

            riskRewardChart?.destroy();
            riskRewardChart = new Chart(ctx, {
                type: "bubble",
                data: {
                    datasets: [
                        {
                            label: "Holdings",
                            data: holdings,
                            backgroundColor: holdings.map(h =>
                                actionColor(h.action) + "99"),
                            borderColor: holdings.map(h => actionColor(h.action)),
                            borderWidth: 1.5,
                        },
                        {
                            label: "Reference",
                            data: refs,
                            backgroundColor: refs.map(r =>
                                r.kind === "portfolio"
                                    ? token("--accent-yellow", "#ffd60a") + "cc"
                                    : token("--accent-blue", "#0a84ff") + "cc"),
                            borderColor: refs.map(r =>
                                r.kind === "portfolio"
                                    ? token("--accent-yellow", "#ffd60a")
                                    : token("--accent-blue", "#0a84ff")),
                            borderWidth: 2,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            ...tooltipOptions(),
                            callbacks: {
                                label(ctx) {
                                    const d = ctx.raw;
                                    if (d.ticker) {
                                        return `${d.ticker}: ${d.y.toFixed(1)}% return, ${d.x.toFixed(1)}% vol`;
                                    }
                                    return `${d.label}: ${d.y.toFixed(1)}% return, ${d.x.toFixed(1)}% vol`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            title: { display: true, text: "Volatility (annual %)", color: theme.tick, font: { size: 10 * scale } },
                            ticks: { color: theme.tick, font: { size: 10 * scale } },
                            grid: { color: theme.grid },
                        },
                        y: {
                            title: { display: true, text: "Return (annual %)", color: theme.tick, font: { size: 10 * scale } },
                            ticks: { color: theme.tick, font: { size: 10 * scale } },
                            grid: { color: theme.grid },
                        },
                    },
                },
            });
        } catch (err) {
            console.warn("Risk/reward chart failed:", err);
            showEmpty("risk-reward-empty", true);
        } finally {
            showLoading("risk-reward-loading", false);
        }
    }

    async function loadCorrelationChart() {
        showLoading("correlation-loading", true);
        showEmpty("correlation-empty", false);
        try {
            const res = await fetch("/api/portfolio/correlation");
            const data = await res.json();
            const tickers = data.tickers || [];

            if (tickers.length < 2) {
                showEmpty("correlation-empty", true);
                correlationChart?.destroy();
                correlationChart = null;
                return;
            }

            const matrix = data.matrix || [];
            const cells = [];
            for (let i = 0; i < tickers.length; i++) {
                for (let j = 0; j < tickers.length; j++) {
                    cells.push({
                        x: tickers[j],
                        y: tickers[i],
                        v: matrix[i]?.[j] ?? 0,
                    });
                }
            }

            const theme = chartTheme();
            const scale = uiScale();
            const ctx = $("correlation-chart")?.getContext("2d");
            const matrixPlugin = window.ChartMatrix || window["chartjs-chart-matrix"];
            if (!ctx || !matrixPlugin?.MatrixController) {
                drawCorrelationFallback(tickers, matrix);
                return;
            }

            correlationChart?.destroy();
            correlationChart = new Chart(ctx, {
                type: "matrix",
                data: {
                    datasets: [{
                        label: "Correlation",
                        data: cells,
                        backgroundColor(ctx) {
                            const v = ctx.raw?.v ?? 0;
                            if (v >= 0) {
                                const a = 0.2 + v * 0.7;
                                return `color-mix(in srgb, var(--accent-red) ${Math.round(a * 100)}%, transparent)`;
                            }
                            const a = 0.2 + Math.abs(v) * 0.7;
                            return `color-mix(in srgb, var(--accent-blue) ${Math.round(a * 100)}%, transparent)`;
                        },
                        borderColor: token("--hairline", "rgba(255,255,255,0.08)"),
                        borderWidth: 1,
                        width: ({ chart }) => (chart.chartArea?.width || 200) / tickers.length - 2,
                        height: ({ chart }) => (chart.chartArea?.height || 200) / tickers.length - 2,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            ...tooltipOptions(),
                            callbacks: {
                                title(items) {
                                    const d = items[0]?.raw;
                                    return d ? `${d.y} × ${d.x}` : "";
                                },
                                label(item) {
                                    const v = item.raw?.v ?? 0;
                                    const plain = v > 0.6 ? "move together often"
                                        : v < -0.2 ? "tend to move apart" : "weakly related";
                                    return `${(v * 100).toFixed(0)}% correlated — ${plain}`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            type: "category",
                            labels: tickers,
                            ticks: { color: theme.tick, font: { size: 9 * scale } },
                            grid: { display: false },
                        },
                        y: {
                            type: "category",
                            labels: tickers,
                            reverse: true,
                            ticks: { color: theme.tick, font: { size: 9 * scale } },
                            grid: { display: false },
                        },
                    },
                },
            });
        } catch (err) {
            console.warn("Correlation chart failed:", err);
            showEmpty("correlation-empty", true);
        } finally {
            showLoading("correlation-loading", false);
        }
    }

    function drawCorrelationFallback(tickers, matrix) {
        const canvas = $("correlation-chart");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const parent = canvas.parentElement;
        const w = parent?.clientWidth || 300;
        const h = 260;
        canvas.width = w;
        canvas.height = h;
        const n = tickers.length;
        const cell = Math.min((w - 40) / n, (h - 40) / n);
        ctx.clearRect(0, 0, w, h);
        for (let i = 0; i < n; i++) {
            for (let j = 0; j < n; j++) {
                const v = matrix[i]?.[j] ?? 0;
                ctx.fillStyle = corrColor(v);
                ctx.fillRect(30 + j * cell, 10 + i * cell, cell - 2, cell - 2);
            }
        }
    }

    async function loadConcentrationGauge() {
        showLoading("concentration-loading", true);
        showEmpty("concentration-empty", false);
        try {
            const res = await fetch("/api/ai/portfolio-exposure");
            const data = await res.json();
            const hhi = data.concentration_hhi ?? 0;
            const sectors = data.sector_exposure || [];

            if (!sectors.length) {
                showEmpty("concentration-empty", true);
                return;
            }

            const top = sectors.slice(0, 2).map(s => `${s.name} (${s.weight_pct}%)`).join(", ");
            const caption = $("concentration-caption");
            if (caption) caption.textContent = top ? `Top drivers: ${top}` : "";

            drawConcentrationGauge(hhi);
        } catch (err) {
            console.warn("Concentration gauge failed:", err);
            showEmpty("concentration-empty", true);
        } finally {
            showLoading("concentration-loading", false);
        }
    }

    function drawConcentrationGauge(hhi) {
        const canvas = $("concentration-gauge");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const W = 320;
        const H = 180;
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        canvas.style.width = `${W}px`;
        canvas.style.height = `${H}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        const cx = W / 2;
        const cy = H - 18;
        const r = 110;
        const start = Math.PI;
        const end = 0;
        const val = Math.max(0, Math.min(1, hhi));

        ctx.clearRect(0, 0, W, H);

        ctx.beginPath();
        ctx.arc(cx, cy, r, start, end);
        ctx.strokeStyle = token("--hairline", "rgba(255,255,255,0.1)");
        ctx.lineWidth = 14;
        ctx.lineCap = "round";
        ctx.stroke();

        const needleAngle = start + (end - start) * val;
        const grad = ctx.createLinearGradient(cx - r, cy, cx + r, cy);
        grad.addColorStop(0, token("--accent-green", "#30d158"));
        grad.addColorStop(0.5, token("--accent-yellow", "#ffd60a"));
        grad.addColorStop(1, token("--accent-red", "#ff453a"));

        ctx.beginPath();
        ctx.arc(cx, cy, r, start, needleAngle);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 14;
        ctx.lineCap = "round";
        ctx.stroke();

        const label = val < 0.25 ? "Well spread"
            : val < 0.5 ? "Moderate"
            : val < 0.75 ? "Concentrated" : "Very concentrated";

        ctx.fillStyle = token("--text-primary", "#f5f5f7");
        ctx.font = `600 15px -apple-system, sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(label, cx, cy - 42);

        ctx.fillStyle = token("--text-tertiary", "rgba(235,235,245,0.42)");
        ctx.font = `500 11px -apple-system, sans-serif`;
        ctx.fillText(`HHI ${(val * 100).toFixed(0)}`, cx, cy - 22);
    }

    async function loadDrawdownChart() {
        showLoading("drawdown-loading", true);
        showEmpty("drawdown-empty", false);
        try {
            const res = await fetch("/api/portfolio/drawdown");
            const data = await res.json();

            if (!data.has_data) {
                showEmpty("drawdown-empty", true);
                drawdownChart?.destroy();
                drawdownChart = null;
                return;
            }

            const ann = $("drawdown-annotation");
            if (ann && data.max_drawdown_pct < 0) {
                ann.textContent = `Max drawdown: ${data.max_drawdown_pct.toFixed(1)}%${data.max_drawdown_date ? ` on ${data.max_drawdown_date}` : ""}`;
            }

            const theme = chartTheme();
            const scale = uiScale();
            const ctx = $("drawdown-chart")?.getContext("2d");
            if (!ctx) return;

            const labels = data.series.map(s => s.date);
            const values = data.series.map(s => s.drawdown_pct);
            const red = token("--accent-red", "#ff453a");

            drawdownChart?.destroy();
            drawdownChart = new Chart(ctx, {
                type: "line",
                data: {
                    labels,
                    datasets: [{
                        label: "Drawdown %",
                        data: values,
                        borderColor: red,
                        backgroundColor: red + "33",
                        fill: true,
                        tension: 0.25,
                        pointRadius: 0,
                        borderWidth: 2,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { ...tooltipOptions() },
                    },
                    scales: {
                        x: {
                            ticks: { color: theme.tick, maxTicksLimit: 6, font: { size: 9 * scale } },
                            grid: { color: theme.grid },
                        },
                        y: {
                            ticks: { color: theme.tick, font: { size: 10 * scale }, callback: v => `${v}%` },
                            grid: { color: theme.grid },
                            max: 0,
                        },
                    },
                },
            });
        } catch (err) {
            console.warn("Drawdown chart failed:", err);
            showEmpty("drawdown-empty", true);
        } finally {
            showLoading("drawdown-loading", false);
        }
    }

    async function loadSectorTreemap() {
        showLoading("treemap-loading", true);
        showEmpty("treemap-empty", false);
        try {
            const res = await fetch("/api/ai/portfolio-exposure");
            const data = await res.json();
            const sectors = (data.sector_exposure || []).filter(s => s.weight_pct > 0);

            if (!sectors.length) {
                showEmpty("treemap-empty", true);
                treemapChart?.destroy();
                treemapChart = null;
                return;
            }

            const palette = [
                "--accent-blue", "--accent-cyan", "--accent-green",
                "--accent-yellow", "--accent-red",
            ].map((t, i) => token(t, `hsl(${i * 55}, 70%, 55%)`));

            const ctx = $("sector-treemap-chart")?.getContext("2d");
            if (!ctx) return;

            if (!window.ChartTreemap && !window["chartjs-chart-treemap"]) {
                drawTreemapFallback(sectors);
                return;
            }

            treemapChart?.destroy();
            treemapChart = new Chart(ctx, {
                type: "treemap",
                data: {
                    datasets: [{
                        label: "Sectors",
                        tree: sectors.map(s => s.weight_pct),
                        labels: sectors.map(s => s.name),
                        spacing: 2,
                        borderWidth: 1,
                        borderColor: token("--hairline", "rgba(255,255,255,0.1)"),
                        backgroundColor(ctx) {
                            const i = ctx.dataIndex % palette.length;
                            return palette[i] + "cc";
                        },
                        labels: {
                            display: true,
                            color: token("--text-primary", "#fff"),
                            font: { size: 10 * uiScale() },
                        },
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: { ...tooltipOptions() } },
                },
            });
        } catch (err) {
            console.warn("Treemap failed:", err);
            showEmpty("treemap-empty", true);
        } finally {
            showLoading("treemap-loading", false);
        }
    }

    function drawTreemapFallback(sectors) {
        const canvas = $("sector-treemap-chart");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const w = canvas.parentElement?.clientWidth || 400;
        const h = 280;
        canvas.width = w;
        canvas.height = h;
        ctx.clearRect(0, 0, w, h);
        let x = 4;
        let y = 4;
        const total = sectors.reduce((s, r) => s + r.weight_pct, 0) || 1;
        sectors.forEach((s, i) => {
            const bw = Math.max(40, (s.weight_pct / total) * (w - 8));
            const bh = 40 + (s.weight_pct / total) * 120;
            ctx.fillStyle = `hsl(${i * 50}, 55%, 45%)`;
            ctx.fillRect(x, y, bw - 4, bh);
            ctx.fillStyle = token("--text-primary", "#fff");
            ctx.font = "11px -apple-system,sans-serif";
            ctx.fillText(`${s.name} ${s.weight_pct}%`, x + 6, y + 18);
            x += bw;
            if (x > w - 60) { x = 4; y += bh + 4; }
        });
    }

    async function loadGeoExposure() {
        showLoading("geo-loading", true);
        showEmpty("geo-empty", false);
        try {
            const res = await fetch("/api/ai/portfolio-exposure");
            const data = await res.json();
            const countries = (data.country_exposure || []).slice(0, 12);

            if (!countries.length) {
                showEmpty("geo-empty", true);
                return;
            }
            drawGeoBars(countries);
        } catch (err) {
            console.warn("Geo exposure failed:", err);
            showEmpty("geo-empty", true);
        } finally {
            showLoading("geo-loading", false);
        }
    }

    function drawGeoBars(countries) {
        const canvas = $("geo-exposure-chart");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const W = canvas.parentElement?.clientWidth || 320;
        const rowH = 26;
        const H = Math.max(180, countries.length * rowH + 24);
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        canvas.style.width = `${W}px`;
        canvas.style.height = `${H}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, W, H);

        const max = Math.max(...countries.map(c => c.weight_pct), 1);
        const barMax = W - 120;

        countries.forEach((c, i) => {
            const y = 12 + i * rowH;
            ctx.fillStyle = token("--text-secondary", "#aaa");
            ctx.font = "11px -apple-system,sans-serif";
            ctx.textAlign = "left";
            const name = c.name.length > 14 ? c.name.slice(0, 13) + "…" : c.name;
            ctx.fillText(name, 0, y + 14);

            const bw = (c.weight_pct / max) * barMax;
            ctx.fillStyle = token("--accent-blue", "#0a84ff") + "99";
            if (typeof ctx.roundRect === "function") {
                ctx.beginPath();
                ctx.roundRect(108, y + 2, bw, 16, 4);
                ctx.fill();
            } else {
                ctx.fillRect(108, y + 2, bw, 16);
            }

            ctx.fillStyle = token("--text-primary", "#fff");
            ctx.textAlign = "right";
            ctx.fillText(`${c.weight_pct}%`, W - 4, y + 14);
        });
    }

    async function loadContributionChart() {
        showLoading("contribution-loading", true);
        showEmpty("contribution-empty", false);
        try {
            const res = await fetch(`/api/portfolio/contribution?period=${contributionPeriod}`);
            const data = await res.json();

            if (!data.has_data) {
                showEmpty("contribution-empty", true);
                return;
            }
            drawWaterfall(data);
        } catch (err) {
            console.warn("Contribution chart failed:", err);
            showEmpty("contribution-empty", true);
        } finally {
            showLoading("contribution-loading", false);
        }
    }

    function drawWaterfall(data) {
        const canvas = $("contribution-chart");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const holdings = data.holdings || [];
        const W = canvas.parentElement?.clientWidth || 600;
        const H = 200;
        canvas.width = W;
        canvas.height = H;
        ctx.clearRect(0, 0, W, H);

        const pad = { l: 48, r: 16, t: 16, b: 36 };
        const n = holdings.length;
        if (!n) return;

        const maxAbs = Math.max(...holdings.map(h => Math.abs(h.contribution)), 1);
        const barW = Math.min(48, (W - pad.l - pad.r) / n - 8);
        const zeroY = pad.t + (H - pad.t - pad.b) / 2;
        const scale = (H - pad.t - pad.b) / 2 / maxAbs;

        ctx.strokeStyle = token("--hairline", "rgba(255,255,255,0.1)");
        ctx.beginPath();
        ctx.moveTo(pad.l, zeroY);
        ctx.lineTo(W - pad.r, zeroY);
        ctx.stroke();

        holdings.forEach((h, i) => {
            const x = pad.l + i * ((W - pad.l - pad.r) / n) + 4;
            const bh = Math.abs(h.contribution) * scale;
            const up = h.contribution >= 0;
            const y = up ? zeroY - bh : zeroY;
            ctx.fillStyle = up ? token("--accent-green", "#30d158") : token("--accent-red", "#ff453a");
            ctx.fillRect(x, y, barW, Math.max(2, bh));

            ctx.fillStyle = token("--text-secondary", "#aaa");
            ctx.font = "10px -apple-system,sans-serif";
            ctx.textAlign = "center";
            ctx.fillText(h.ticker, x + barW / 2, H - 8);
        });

        ctx.fillStyle = token("--text-primary", "#fff");
        ctx.textAlign = "left";
        ctx.font = "600 11px -apple-system,sans-serif";
        const totalLabel = typeof formatCompact === "function"
            ? formatCompact(data.total_contribution)
            : data.total_contribution.toFixed(0);
        ctx.fillText(`Total: ${totalLabel}`, pad.l, 14);
    }

    async function loadSignalBoard() {
        showLoading("signal-board-loading", true);
        showEmpty("signal-board-empty", false);
        const grid = $("signal-board-grid");
        if (!grid) return;

        try {
            const res = await fetch(`/api/ai/investment-signals/all${window._forcedLocalMode ? "?force_local=true" : ""}`);
            if (!res.ok) throw new Error("signals unavailable");
            const data = await res.json();
            const signals = data.signals || {};
            const tickers = Object.keys(signals).filter(t => !latestHoldings.find(h => h.ticker === t && h.is_watchlist));

            if (!tickers.length) {
                showEmpty("signal-board-empty", true);
                grid.innerHTML = "";
                return;
            }

            grid.innerHTML = tickers.map(ticker => {
                const s = signals[ticker];
                const action = (s.action || "hold").toLowerCase();
                const conf = s.confidence ?? 50;
                const bg = actionColor(action);
                const alpha = 0.25 + (conf / 100) * 0.55;
                return `<div class="signal-board-tile" role="listitem" style="background: color-mix(in srgb, ${bg} ${Math.round(alpha * 100)}%, var(--surface))">
                    <span class="signal-board-ticker">${escapeHtml(ticker)}</span>
                    <span class="signal-board-action">${escapeHtml(action)}</span>
                </div>`;
            }).join("");
        } catch (err) {
            console.warn("Signal board failed:", err);
            showEmpty("signal-board-empty", true);
        } finally {
            showLoading("signal-board-loading", false);
        }
    }

    async function loadAnalystScorecard() {
        showLoading("analyst-scorecard-loading", true);
        showEmpty("analyst-scorecard-empty", false);
        try {
            const res = await fetch("/api/ai/analyst-recommendations/all");
            const data = await res.json();
            const recs = data.recommendations || {};
            const rows = Object.entries(recs)
                .filter(([, r]) => r.action !== "unavailable" && r.target_upside_pct != null)
                .map(([ticker, r]) => ({ ticker, upside: r.target_upside_pct, action: r.action }));

            if (!rows.length) {
                showEmpty("analyst-scorecard-empty", true);
                analystChart?.destroy();
                analystChart = null;
                return;
            }

            rows.sort((a, b) => b.upside - a.upside);
            const theme = chartTheme();
            const scale = uiScale();
            const ctx = $("analyst-scorecard-chart")?.getContext("2d");
            if (!ctx) return;

            analystChart?.destroy();
            analystChart = new Chart(ctx, {
                type: "bar",
                data: {
                    labels: rows.map(r => r.ticker),
                    datasets: [{
                        label: "Target upside %",
                        data: rows.map(r => r.upside),
                        backgroundColor: rows.map(r =>
                            r.upside >= 0
                                ? token("--accent-green", "#30d158") + "aa"
                                : token("--accent-red", "#ff453a") + "aa"),
                        borderRadius: 4,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: { ...tooltipOptions() } },
                    scales: {
                        x: {
                            ticks: { color: theme.tick, font: { size: 10 * scale }, callback: v => `${v}%` },
                            grid: { color: theme.grid },
                        },
                        y: {
                            ticks: { color: theme.tick, font: { size: 10 * scale } },
                            grid: { display: false },
                        },
                    },
                },
            });
        } catch (err) {
            console.warn("Analyst scorecard failed:", err);
            showEmpty("analyst-scorecard-empty", true);
        } finally {
            showLoading("analyst-scorecard-loading", false);
        }
    }

    function tapeItemHtml(m) {
        const up = (m.day_change_pct ?? 0) >= 0;
        const cls = up ? "tape-chg-up" : "tape-chg-down";
        const sign = up ? "+" : "";
        const price = typeof _marketPrice === "function" ? _marketPrice(m.price) : m.price;
        return `<span class="markets-tape-item">
            <span class="tape-flag">${m.flag || ""}</span>
            <span class="tape-name">${escapeHtml(m.name)}</span>
            <span class="tape-price">${price}</span>
            <span class="${cls}">${sign}${(m.day_change_pct ?? 0).toFixed(2)}%</span>
        </span>`;
    }

    let _tapeListenersBound = false;

    function refreshMarketsTape(markets) {
        _cachedMarkets = markets || [];
        const track = $("markets-tape-track");
        const grid = $("markets-tape-grid");
        if (!track) return;

        if (!_cachedMarkets.length) {
            track.innerHTML = `<span class="markets-tape-item" style="color:var(--text-tertiary)">Market data unavailable</span>`;
            if (grid) grid.innerHTML = "";
            return;
        }

        const items = _cachedMarkets.map(tapeItemHtml).join("");
        track.innerHTML = items + items;
        track.classList.toggle("is-animating", !prefersReducedMotion() && !_tapePaused && _tapeInView);

        if (grid) {
            grid.innerHTML = _cachedMarkets.map(m => {
                const up = (m.day_change_pct ?? 0) >= 0;
                const cls = up ? "text-success" : "text-danger";
                const sign = up ? "+" : "";
                const price = typeof _marketPrice === "function" ? _marketPrice(m.price) : m.price;
                return `<div class="markets-grid-tile">
                    <div class="market-tile-name">${m.flag || ""} ${escapeHtml(m.name)}</div>
                    <div class="market-tile-price">${price}</div>
                    <div class="${cls}" style="font-size:.72rem">${sign}${(m.day_change_pct ?? 0).toFixed(2)}%</div>
                </div>`;
            }).join("");
        }

        const wrap = $("markets-tape-wrap");
        if (wrap && !_tapeListenersBound) {
            _tapeListenersBound = true;
            wrap.addEventListener("mouseenter", () => {
                _tapePaused = true;
                track.classList.add("is-paused");
                track.classList.remove("is-animating");
            });
            wrap.addEventListener("mouseleave", () => {
                _tapePaused = false;
                if (!prefersReducedMotion() && _tapeInView) {
                    track.classList.remove("is-paused");
                    track.classList.add("is-animating");
                }
            });
            wrap.addEventListener("focusin", () => { _tapePaused = true; track.classList.add("is-paused"); });
            wrap.addEventListener("focusout", () => { _tapePaused = false; });
        }
    }

    async function refreshMarketsFromApi() {
        try {
            const res = await fetch("/api/stocks/world-markets");
            if (!res.ok) return;
            const { markets } = await res.json();
            refreshMarketsTape(markets);
        } catch (err) {
            console.warn("Markets tape failed:", err);
        }
    }

    function setupTapeObserver() {
        const wrap = $("markets-tape-wrap");
        if (!wrap || typeof IntersectionObserver === "undefined") return;
        const obs = new IntersectionObserver(entries => {
            _tapeInView = entries.some(e => e.isIntersecting);
            const track = $("markets-tape-track");
            if (!track) return;
            if (_tapeInView && !prefersReducedMotion() && !_tapePaused) {
                track.classList.add("is-animating");
            } else {
                track.classList.remove("is-animating");
            }
        }, { threshold: 0.1 });
        obs.observe(wrap);
    }

    function resizeCharts() {
        [riskRewardChart, correlationChart, drawdownChart, treemapChart, analystChart].forEach(c => {
            c?.resize?.();
            c?.update?.("none");
        });
    }

    function onThemeChange() {
        updateChartChrome(riskRewardChart);
        updateChartChrome(correlationChart);
        updateChartChrome(drawdownChart);
        updateChartChrome(treemapChart);
        updateChartChrome(analystChart);
        if (rendered.has("risk")) {
            loadConcentrationGauge();
        }
        if (rendered.has("exposure")) {
            loadGeoExposure();
        }
        if (rendered.has("signals")) {
            loadContributionChart();
        }
    }

    function onRefresh() {
        if (activePane === "risk" && rendered.has("risk")) loadRiskPane();
        if (activePane === "exposure" && rendered.has("exposure")) loadExposurePane();
        if (activePane === "signals" && rendered.has("signals")) loadSignalsPane();
        if (activePane === "markets" || rendered.has("markets")) refreshMarketsFromApi();
    }

    function onAnalyticsZoneEnter() {
        requestAnimationFrame(resizeCharts);
        if (activePane !== "performance" && !rendered.has(activePane)) {
            rendered.add(activePane);
            loadPane(activePane);
        }
    }

    function init() {
        registerPlugins();
        initSubTabs();
        setupTapeObserver();
    }

    return {
        init,
        setSubPane,
        onRefresh,
        onThemeChange,
        onAnalyticsZoneEnter,
        refreshMarketsTape,
    };
})();

window.AnalyticsCharts = AnalyticsCharts;
