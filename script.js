/*
 * TERRA ESPELHO | REDFRONTIER
 * Versão offline: os dados fornecidos para Challapata ficam armazenados
 * neste arquivo. Não há fetch(), API automática, polling ou conexão contínua.
 *
 * Local: Challapata, departamento de Oruro, Bolívia.
 * Coordenadas recebidas: -19.0148, -66.9865.
 * Score lunar preliminar da equipe: 0.6760 (não é um dado NASA).
 *
 * Os indicadores são apresentados exatamente como recebidos da equipe.
 * A identificação detalhada de coleção/data/granule/QA deve acompanhar
 * o projeto como metadado científico; não é inventada pelo sistema.
 */

(() => {
  'use strict';

  const LOCATIONS = [
    {
      id: 'challapata',
      name: 'Challapata',
      region: 'Oruro',
      country: 'Bolívia',
      latitude: -19.0148,
      longitude: -66.9865,
      target: 'Lua',
      rank: 1,
      score: 0.6760,

      description: 'Ponto de análise selecionado pela equipe RedFrontier em Oruro, Bolívia. As coordenadas representam o ponto geográfico utilizado no conjunto de dados recebido.',

      indicators: [
        {
          id: 'thermal-amplitude',
          code: 'AMPLITUDE TÉRMICA',
          name: 'Amplitude térmica (diurna/noite ou 3h)',
          pillar: 'Temperatura e albedo',
          value: 41.93,
          display: '41,93',
          unit: 'K',
          note: 'Amplitude informada no conjunto recebido.'
        },
        {
          id: 'bsa',
          code: 'BSA',
          name: 'Albedo de ondas curtas (Black-Sky Albedo)',
          pillar: 'Temperatura e albedo',
          value: 0.1500,
          display: '0,1500',
          unit: 'fração',
          note: 'Referência indicada pela equipe: ideal < 0,12.'
        },
        {
          id: 'surface-moisture',
          code: 'SFMC',
          name: 'Umidade superficial (0–5 cm)',
          pillar: 'Solo e secura',
          value: 0.05864,
          display: '0,05864',
          unit: 'm³/m³',
          note: 'Umidade volumétrica superficial.'
        },
        {
          id: 'root-moisture',
          code: 'RZMC',
          name: 'Umidade na zona raiz (0–100 cm)',
          pillar: 'Solo e secura',
          value: 0.11150,
          display: '0,11150',
          unit: 'm³/m³',
          note: 'Umidade volumétrica na zona de raízes.'
        },
        {
          id: 'deep-moisture',
          code: 'PRMC',
          name: 'Umidade no perfil profundo',
          pillar: 'Solo e secura',
          value: 0.11473,
          display: '0,11473',
          unit: 'm³/m³',
          note: 'Umidade volumétrica no perfil profundo.'
        },
        {
          id: 'wilting',
          code: 'FRAÇÃO DE MURCHAMENTO',
          name: 'Fração de ponto de murcha (aridez)',
          pillar: 'Solo e secura',
          value: 0.8682,
          display: '0,8682',
          unit: 'fração',
          note: 'Índice informado pela equipe.'
        },
        {
          id: 'ndvi',
          code: 'NDVI',
          name: 'Índice de vegetação',
          pillar: 'Solo e secura',
          value: 0.2000,
          display: '0,2000',
          unit: 'índice',
          note: 'Referência indicada pela equipe: ideal próximo de 0,0.'
        },
        {
          id: 'omps',
          code: 'OMPS / AERDB',
          name: 'Índice de aerossóis UV',
          pillar: 'Poeira e mineralogia',
          value: 0.2236,
          display: '0,2236',
          unit: 'índice',
          note: 'Índice de aerossóis UV informado.'
        },
        {
          id: 'aod',
          code: 'AOD',
          name: 'Espessura óptica de aerossóis',
          pillar: 'Poeira e mineralogia',
          value: 0.1220,
          display: '0,1220',
          unit: 'índice',
          note: 'AOD informado no conjunto recebido.'
        },
        {
          id: 'emit',
          code: 'EMIT',
          name: 'Abundância mineral máfica',
          pillar: 'Poeira e mineralogia',
          value: 0.3138,
          display: '0,3138',
          unit: 'fração/índice',
          note: 'Abundância mineral máfica informada.'
        }
      ]
    }
  ];

  const PILLARS = [
    {
      name: 'Temperatura e albedo',
      short: 'PILAR 1',
      ids: ['thermal-amplitude', 'bsa'],
      color: '#72d8cb'
    },
    {
      name: 'Solo e secura',
      short: 'PILAR 2',
      ids: [
        'surface-moisture',
        'root-moisture',
        'deep-moisture',
        'wilting',
        'ndvi'
      ],
      color: '#71a9f7'
    },
    {
      name: 'Poeira e mineralogia',
      short: 'PILAR 3',
      ids: ['omps', 'aod', 'emit'],
      color: '#f3c879'
    }
  ];

  const $ = (id) => document.getElementById(id);

  const state = {
    selectedLocationId: 'challapata',
    selectedPlanet: 'moon',
    rotation: -66.9865,
    tilt: -8,
    zoom: 1,
    canvas: null,
    ctx: null,
    marker: null,
    frame: 0,
    drag: null,
    charts: Object.create(null)
  };

  function locationNow() {
    return LOCATIONS.find(
      (x) => x.id === state.selectedLocationId
    ) || LOCATIONS[0];
  }

  function fmt(value, digits = 4) {
    return new Intl.NumberFormat('pt-BR', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    }).format(value);
  }

  function toast(message) {
    const node = $('toast');

    if (!node) return;

    node.textContent = message;
    node.classList.add('is-visible');

    clearTimeout(toast.timer);

    toast.timer = setTimeout(() => {
      node.classList.remove('is-visible');
    }, 2600);
  }

  function setStatus() {
    const message =
      'Dados locais carregados · sem conexão contínua';

    ['sidebarStatus', 'data-status'].forEach((id) => {
      if ($(id)) {
        $(id).textContent = message;
      }
    });

    const status = $('apiStatus');

    if (status) {
      status.className = 'api-status is-success';

      status.textContent =
        '✓ Base local carregada. Os indicadores estão armazenados no projeto; nenhuma consulta externa será realizada.';
    }
  }

  function findIndicator(id) {
    return locationNow().indicators.find(
      (item) => item.id === id
    );
  }

  function updateLocationPanel() {
    const loc = locationNow();

    const scoreText = fmt(loc.score, 4);
    const percent = fmt(loc.score * 100, 1);

    const text = (id, value) => {
      if ($(id)) {
        $(id).textContent = value;
      }
    };

    text('total-locations', String(LOCATIONS.length));
    text('selected-source', 'NASA');
    text('total-criteria', String(loc.indicators.length));
    text('overview-score', scoreText);

    text('location-name', loc.name);
    text('location-country', `${loc.region}, ${loc.country}`);
    text('location-description', loc.description);

    text(
      'locationCoords',
      `${loc.latitude.toFixed(4)}°, ${loc.longitude.toFixed(4)}°`
    );

    text(
      'globeSelectedLabel',
      `${loc.name}, ${loc.region}, ${loc.country}`
    );

    text(
      'globeLocationCount',
      `${LOCATIONS.length} LOCAL NO MAPA`
    );

    text(
      'location-rank',
      `ANÁLOGO ${loc.target.toUpperCase()} #${loc.rank}`
    );

    text(
      'location-symbol',
      loc.target === 'Marte' ? '🔴' : '🌙'
    );

    text('panel-score', scoreText);
    text('panel-score-label', 'SCORE LUNAR PRELIMINAR REDFRONTIER');
    text('scoreChartCenter', scoreText);

    text(
      'queryCoordinates',
      `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`
    );

    text(
      'queryPeriod',
      'Período original dos dados não informado'
    );

    text(
      'powerRecordCount',
      `${loc.indicators.length} indicadores armazenados`
    );

    text(
      'powerMetadata',
      'Conjunto fornecido à equipe: Challapata, Oruro, Bolívia. Coordenadas do ponto: -19.0148, -66.9865. Data/período, versão, granule e flags QA não foram incluídos no material recebido.'
    );

    if ($('panelDisclaimer')) {
      $('panelDisclaimer').textContent =
        'Score 0,6760 informado pela equipe como resultado preliminar. Não é um indicador NASA e não é recalculado automaticamente.';
    }

    if ($('scoreRing')) {
      $('scoreRing').style.background =
        `conic-gradient(var(--accent) 0 ${loc.score * 100}%, rgba(114,216,203,.12) ${loc.score * 100}% 100%)`;

      $('scoreRing').setAttribute(
        'aria-label',
        `Score preliminar ${percent} por cento`
      );

      const span = $('scoreRing').querySelector('span');

      if (span) {
        span.textContent = `${percent}%`;
      }
    }

    if ($('selectionHint')) {
      $('selectionHint').textContent =
        `ⓘ Marcador selecionado: ${loc.name}. Clique em qualquer outro marcador cadastrado para carregar o respectivo conjunto de dados.`;
    }

    const worldView = new URL(
      'https://worldview.earthdata.nasa.gov/'
    );

    worldView.searchParams.set(
      'v',
      `${loc.longitude - 1.5},${loc.latitude - 1.5},${loc.longitude + 1.5},${loc.latitude + 1.5}`
    );

    if ($('worldviewLink')) {
      $('worldviewLink').href = worldView.toString();
    }

    if ($('worldviewSourceLink')) {
      $('worldviewSourceLink').href = worldView.toString();
    }
  }

  function renderMetrics() {
    const mapping = [
      ['metricT2M', 'thermal-amplitude', 2],
      ['metricAmplitude', 'bsa', 4],
      ['metricSFMC', 'surface-moisture', 5],
      ['metricPrecip', 'root-moisture', 5],
      ['metricRZMC', 'deep-moisture', 5],
      ['metricPRMC', 'wilting', 4],
      ['metricSolar', 'ndvi', 4],
      ['metricDays', 'omps', 4]
    ];

    mapping.forEach(([elementId, indicatorId, digits]) => {
      const item = findIndicator(indicatorId);

      if ($(elementId)) {
        $(elementId).textContent = item
          ? fmt(item.value, digits)
          : '—';
      }
    });
  }

  function renderTable() {
    const body = $('powerTableBody');

    if (!body) return;

    body.replaceChildren();

    locationNow().indicators.forEach((item) => {
      const row = document.createElement('tr');

      [
        item.code,
        item.name,
        item.pillar,
        item.display,
        item.unit
      ].forEach((value) => {
        const cell = document.createElement('td');

        cell.textContent = value;
        row.appendChild(cell);
      });

      row.title = item.note;
      body.appendChild(row);
    });
  }

  function canvasContext(id) {
    const canvas = $(id);

    if (!canvas) return null;

    const rect = canvas.getBoundingClientRect();

    const width = Math.max(
      220,
      Math.round(
        rect.width ||
        canvas.parentElement?.clientWidth ||
        320
      )
    );

    const height = Math.max(
      130,
      Math.round(
        rect.height ||
        canvas.parentElement?.clientHeight ||
        180
      )
    );

    const ratio = Math.min(
      window.devicePixelRatio || 1,
      2
    );

    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);

    const ctx = canvas.getContext('2d');

    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

    return {
      canvas,
      ctx,
      width,
      height
    };
  }

  function drawBarChart(id, entries, color, maxValue) {
    const c = canvasContext(id);

    if (!c) return;

    const { ctx, width, height } = c;

    ctx.clearRect(0, 0, width, height);

    const left = 116;
    const right = 18;
    const top = 12;
    const bottom = 12;

    const plotWidth = Math.max(
      40,
      width - left - right
    );

    const rowHeight =
      (height - top - bottom) / entries.length;

    ctx.font = '10px Arial';

    entries.forEach((entry, i) => {
      const y = top + i * rowHeight;

      ctx.fillStyle = '#91a3b9';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';

      ctx.fillText(
        entry.label,
        left - 9,
        y + rowHeight / 2
      );

      ctx.fillStyle = 'rgba(151,179,211,.10)';

      ctx.fillRect(
        left,
        y + rowHeight * .25,
        plotWidth,
        Math.min(13, rowHeight * .5)
      );

      const ratio = Math.max(
        0,
        Math.min(1, Math.abs(entry.value) / (maxValue || 1))
      );

      ctx.fillStyle = color;

      ctx.fillRect(
        left,
        y + rowHeight * .25,
        plotWidth * ratio,
        Math.min(13, rowHeight * .5)
      );

      ctx.fillStyle = '#dce9f4';
      ctx.textAlign = 'left';

      ctx.fillText(
        entry.display,
        Math.min(
          width - 45,
          left + plotWidth * ratio + 6
        ),
        y + rowHeight / 2
      );
    });
  }

  function renderCharts() {
    const loc = locationNow();

    const byId = Object.fromEntries(
      loc.indicators.map((x) => [x.id, x])
    );

    drawBarChart(
      'temperatureChart',
      [
        {
          label: 'Amplitude térmica',
          value: byId['thermal-amplitude'].value,
          display: '41,93 K'
        },
        {
          label: 'Albedo BSA',
          value: byId.bsa.value,
          display: '0,1500'
        }
      ],
      '#72d8cb',
      45
    );

    drawBarChart(
      'precipitationChart',
      [
        {
          label: 'Umidade 0–5 cm',
          value: byId['surface-moisture'].value,
          display: '0,05864'
        },
        {
          label: 'Zona raiz',
          value: byId['root-moisture'].value,
          display: '0,11150'
        },
        {
          label: 'Perfil profundo',
          value: byId['deep-moisture'].value,
          display: '0,11473'
        },
        {
          label: 'Ponto de murcha',
          value: byId.wilting.value,
          display: '0,8682'
        },
        {
          label: 'NDVI',
          value: byId.ndvi.value,
          display: '0,2000'
        }
      ],
      '#71a9f7',
      1
    );

    drawBarChart(
      'moistureChart',
      [
        {
          label: 'Aerossóis UV',
          value: byId.omps.value,
          display: '0,2236'
        },
        {
          label: 'AOD',
          value: byId.aod.value,
          display: '0,1220'
        },
        {
          label: 'Minerais máficos',
          value: byId.emit.value,
          display: '0,3138'
        }
      ],
      '#f3c879',
      0.4
    );

    drawScore();
  }

  function drawScore() {
    const c = canvasContext('scoreChart');

    if (!c) return;

    const { ctx, width, height } = c;

    ctx.clearRect(0, 0, width, height);

    const x = width / 2;
    const y = height / 2;
    const radius = Math.min(width, height) * .37;

    ctx.lineWidth = 15;
    ctx.strokeStyle = 'rgba(114,216,203,.13)';

    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = '#72d8cb';
    ctx.lineCap = 'round';

    ctx.beginPath();

    ctx.arc(
      x,
      y,
      radius,
      -Math.PI / 2,
      -Math.PI / 2 + Math.PI * 2 * locationNow().score
    );

    ctx.stroke();
  }
    /* Globo ortográfico local: não baixa mapas, texturas ou bibliotecas. */

  function project(lat, lon, cx, cy, radius) {
    const toRad = Math.PI / 180;

    const phi = lat * toRad;
    const lambda = (lon - state.rotation) * toRad;
    const tilt = state.tilt * toRad;

    const x = Math.cos(phi) * Math.sin(lambda);

    const y =
      Math.sin(phi) * Math.cos(tilt) -
      Math.cos(phi) * Math.cos(lambda) * Math.sin(tilt);

    const z =
      Math.sin(phi) * Math.sin(tilt) +
      Math.cos(phi) * Math.cos(lambda) * Math.cos(tilt);

    return {
      x: cx + radius * state.zoom * x,
      y: cy - radius * state.zoom * y,
      visible: z >= 0,
      z
    };
  }

  function drawGlobe() {
    const canvas = state.canvas;
    const ctx = state.ctx;

    if (!canvas || !ctx) return;

    const rect = canvas.getBoundingClientRect();

    const w = Math.max(260, rect.width);
    const h = Math.max(250, rect.height);

    const dpr = Math.min(
      window.devicePixelRatio || 1,
      2
    );

    if (
      canvas.width !== Math.round(w * dpr) ||
      canvas.height !== Math.round(h * dpr)
    ) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(w * .39, h * .43) * state.zoom;

    const glow = ctx.createRadialGradient(
      cx - r * .28,
      cy - r * .35,
      r * .08,
      cx,
      cy,
      r * 1.15
    );

    glow.addColorStop(0, '#286b83');
    glow.addColorStop(.65, '#123b59');
    glow.addColorStop(1, '#071728');

    ctx.save();

    ctx.shadowColor = 'rgba(79,188,220,.28)';
    ctx.shadowBlur = 26;

    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = glow;
    ctx.fill();

    ctx.restore();

    ctx.save();

    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.clip();

    // Linhas de latitude e longitude projetadas sobre a esfera.

    ctx.strokeStyle = 'rgba(153,220,230,.18)';
    ctx.lineWidth = 1;

    for (let lat = -60; lat <= 60; lat += 30) {
      ctx.beginPath();

      for (let lon = -180; lon <= 180; lon += 3) {
        const p = project(
          lat,
          lon,
          cx,
          cy,
          r / state.zoom
        );

        if (p.visible) {
          if (lon === -180) {
            ctx.moveTo(p.x, p.y);
          } else {
            ctx.lineTo(p.x, p.y);
          }
        }
      }

      ctx.stroke();
    }

    for (let lon = -180; lon < 180; lon += 30) {
      ctx.beginPath();

      let started = false;

      for (let lat = -88; lat <= 88; lat += 2) {
        const p = project(
          lat,
          lon,
          cx,
          cy,
          r / state.zoom
        );

        if (p.visible) {
          if (!started) {
            ctx.moveTo(p.x, p.y);
            started = true;
          } else {
            ctx.lineTo(p.x, p.y);
          }
        }
      }

      ctx.stroke();
    }

    // Silhuetas continentais simplificadas para orientação visual.
    // Não representam dados GIS ou cartografia de precisão.

    const land = [
      [
        [72, -160], [60, -145], [55, -125],
        [48, -123], [40, -115], [30, -110],
        [20, -105], [12, -92], [8, -82],
        [18, -76], [28, -80], [32, -80],
        [45, -60], [52, -55], [60, -65],
        [68, -90], [72, -120]
      ],
      [
        [12, -81], [5, -77], [-5, -80],
        [-15, -75], [-25, -70], [-40, -72],
        [-55, -68], [-50, -55], [-35, -48],
        [-15, -40], [-2, -50], [8, -62]
      ],
      [
        [72, -10], [68, 25], [60, 40],
        [55, 65], [45, 80], [35, 75],
        [25, 60], [15, 45], [5, 35],
        [-10, 40], [-20, 30], [-35, 20],
        [-35, 5], [-20, -5], [0, 5],
        [10, -10], [30, -10], [45, -5],
        [60, -10]
      ],
      [
        [55, 100], [50, 120], [45, 140],
        [35, 150], [25, 135], [15, 120],
        [5, 105], [10, 90], [25, 80],
        [40, 85]
      ],
      [
        [-10, 112], [-20, 115], [-35, 130],
        [-40, 145], [-25, 153], [-12, 135]
      ],
      [
        [80, -45], [70, -35], [60, -45],
        [62, -55], [75, -60]
      ]
    ];

    ctx.fillStyle = 'rgba(89,151,126,.52)';
    ctx.strokeStyle = 'rgba(164,216,178,.45)';
    ctx.lineWidth = 1;

    land.forEach((poly) => {
      ctx.beginPath();

      let started = false;

      poly.forEach(([lat, lon]) => {
        const p = project(
          lat,
          lon,
          cx,
          cy,
          r / state.zoom
        );

        if (p.visible) {
          if (!started) {
            ctx.moveTo(p.x, p.y);
            started = true;
          } else {
            ctx.lineTo(p.x, p.y);
          }
        }
      });

      if (started) {
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    });

    ctx.restore();

    ctx.strokeStyle = 'rgba(115,209,218,.55)';
    ctx.lineWidth = 1.2;

    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    const loc = locationNow();

    const point = project(
      loc.latitude,
      loc.longitude,
      cx,
      cy,
      r / state.zoom
    );

    const marker = state.marker;

    if (marker && point.visible) {
      marker.hidden = false;
      marker.style.left = `${point.x}px`;
      marker.style.top = `${point.y}px`;
    } else if (marker) {
      marker.hidden = true;
    }
  }

  function initGlobe() {
    const host = $('globeViz');

    if (!host) return;

    host.replaceChildren();

    const canvas = document.createElement('canvas');

    canvas.setAttribute('role', 'img');

    canvas.setAttribute(
      'aria-label',
      'Globo terrestre esquemático interativo com marcador em Challapata'
    );

    host.appendChild(canvas);

    const marker = document.createElement('button');

    marker.type = 'button';
    marker.className = 'globe-marker is-selected';
    marker.textContent = 'CHALLAPATA';

    marker.setAttribute(
      'aria-label',
      'Selecionar Challapata, Oruro, Bolívia'
    );

    marker.addEventListener('click', (event) => {
      event.stopPropagation();
      selectLocation('challapata');
    });

    host.appendChild(marker);

    state.canvas = canvas;
    state.ctx = canvas.getContext('2d');
    state.marker = marker;

    canvas.addEventListener('pointerdown', (event) => {
      state.drag = {
        x: event.clientX,
        y: event.clientY,
        rotation: state.rotation,
        tilt: state.tilt
      };

      canvas.setPointerCapture(event.pointerId);
    });

    canvas.addEventListener('pointermove', (event) => {
      if (!state.drag) return;

      const rect = canvas.getBoundingClientRect();

      state.rotation =
        state.drag.rotation -
        (event.clientX - state.drag.x) / rect.width * 180;

      state.tilt = Math.max(
        -65,
        Math.min(
          65,
          state.drag.tilt +
          (event.clientY - state.drag.y) / rect.height * 100
        )
      );

      drawGlobe();
    });

    const endDrag = () => {
      state.drag = null;
    };

    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);

    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();

      state.zoom = Math.max(
        .82,
        Math.min(
          1.55,
          state.zoom + (event.deltaY < 0 ? .06 : -.06)
        )
      );

      drawGlobe();
    }, { passive: false });

    marker.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        selectLocation('challapata');
      }
    });

    $('loading')?.classList.add('is-hidden');

    if ($('globeFallback')) {
      $('globeFallback').hidden = true;
    }

    drawGlobe();

    window.addEventListener(
      'resize',
      drawGlobe,
      { passive: true }
    );
  }

  function selectLocation(id) {
    const item = LOCATIONS.find((x) => x.id === id);

    if (!item) return;

    state.selectedLocationId = id;

    updateLocationPanel();
    renderMetrics();
    renderTable();
    renderCharts();
    drawGlobe();

    openPanel();

    toast(`${item.name} selecionado. Dados locais carregados.`);
  }

  function openPanel() {
    $('explorerLayout')?.classList.add('is-open');

    $('infoPanel')?.setAttribute(
      'aria-hidden',
      'false'
    );

    $('selectionHint')?.setAttribute('hidden', '');

    drawGlobe();
  }

  function closePanel() {
    $('explorerLayout')?.classList.remove('is-open');

    $('infoPanel')?.setAttribute(
      'aria-hidden',
      'true'
    );

    $('selectionHint')?.removeAttribute('hidden');
  }

  function setupNavigation() {
    const links = [
      ...document.querySelectorAll('.menu-link')
    ];

    links.forEach((link) => {
      link.addEventListener('click', () => {
        links.forEach((x) => {
          x.classList.toggle('active', x === link);
        });

        if ($('breadcrumbCurrent')) {
          $('breadcrumbCurrent').textContent =
            link.textContent.trim();
        }

        $('sidebar')?.classList.remove('is-open');

        $('mobileMenuButton')?.setAttribute(
          'aria-expanded',
          'false'
        );
      });
    });
  }

  async function copyCoordinates() {
    const loc = locationNow();

    const value =
      `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`;

    try {
      if (
        navigator.clipboard &&
        window.isSecureContext
      ) {
        await navigator.clipboard.writeText(value);
      } else {
        const field = document.createElement('textarea');

        field.value = value;

        document.body.appendChild(field);

        field.select();

        const ok = document.execCommand('copy');

        field.remove();

        if (!ok) {
          throw new Error('copy failed');
        }
      }

      toast('Coordenadas copiadas.');

    } catch {
      toast(`Coordenadas: ${value}`);
    }
  }

  function setupEvents() {
    $('closePanel')?.addEventListener(
      'click',
      closePanel
    );

    $('focusLocation')?.addEventListener('click', () => {
      state.rotation = locationNow().longitude;
      state.tilt = locationNow().latitude;
      state.zoom = 1.25;

      drawGlobe();
      openPanel();
    });

    $('copyCoordinates')?.addEventListener(
      'click',
      copyCoordinates
    );

    $('viewIndicators')?.addEventListener('click', () => {
      $('dados-nasa')?.scrollIntoView({
        behavior: 'smooth'
      });
    });

    $('retryGlobe')?.addEventListener(
      'click',
      initGlobe
    );

    $('planet')?.addEventListener('change', (event) => {
      state.selectedPlanet = event.target.value;

      toast(
        `Alvo de estudo selecionado: ${state.selectedPlanet === 'moon' ? 'Lua' : 'Marte'}. O score cadastrado continua sendo lunar.`
      );
    });

    $('mobileMenuButton')?.addEventListener('click', () => {
      const open =
        $('sidebar')?.classList.toggle('is-open') || false;

      $('mobileMenuButton')?.setAttribute(
        'aria-expanded',
        String(open)
      );
    });
  }

  function init() {
    setStatus();

    updateLocationPanel();
    renderMetrics();
    renderTable();

    setupEvents();
    setupNavigation();

    initGlobe();

    requestAnimationFrame(() => {
      renderCharts();
      drawGlobe();
    });

    console.info(
      'Terra Espelho | RedFrontier: modo offline inicializado.',
      {
        local: locationNow().name,
        coordinates: [
          locationNow().latitude,
          locationNow().longitude
        ],
        indicators: locationNow().indicators.length,
        networkRequests: 0
      }
    );
  }

  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      init,
      { once: true }
    );
  } else {
    init();
  }

})();