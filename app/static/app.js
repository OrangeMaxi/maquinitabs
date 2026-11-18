/* Maquinitabs — interfaz */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
const api = (ruta, opciones) => fetch('/api/' + ruta, opciones).then(async (r) => {
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
  return d;
});

const COLORES = { vocals: '#f472b6', guitar: '#f5a524', piano: '#60a5fa', bass: '#a78bfa', drums: '#f87171', otros: '#34d399', other: '#34d399' };

const E = {
  id: null, c: null,            // canción abierta (app.json)
  st: 0,                        // semitonos de transporte
  vista: 'armonia', modo: 'acordes', escala: 0, diapason: 'guitarra',   // vista = pestaña (instrumento)
  geo: [],                      // por compás: {fila, x0, x1}
  compasActual: -1, acordeActual: '',
  mute: {}, solo: {}, vol: {},
};
const A = { ctx: null, buffers: {}, gains: {}, fuentes: [], tocando: false, pos: 0, t0: 0, carga: 0, listo: false };

// ================================================================= biblioteca y trabajos
async function cargarLista() {
  const lista = await api('canciones');
  $('#lista').innerHTML = lista.length ? lista.map((c) => `
    <li data-id="${esc(c.id)}" class="${c.id === E.id ? 'activa' : ''}">
      <b>${esc(c.titulo)}</b><small>${esc(c.artista)} · ${c.pistas} pistas${c.analizada ? '' : ' · <span class="pend">sin analizar</span>'}</small>
    </li>`).join('') : '<li class="vacio">Todavía no hay canciones. Pegá un link arriba.</li>';
  $$('#lista li[data-id]').forEach((li) => {
    li.onclick = async () => {
      const c = lista.find((x) => x.id === li.dataset.id);
      if (c.analizada) abrir(c.id);
      else { seguir(await api(`canciones/${encodeURIComponent(c.id)}/analizar`, { method: 'POST' })); }
    };
  });
}

let sondeo = null;
const abrirAlTerminar = new Set();
function seguir(trabajo) {
  abrirAlTerminar.add(trabajo.id);
  sondear();
}
async function sondear() {
  clearTimeout(sondeo);
  const ts = await api('trabajos').catch(() => []);
  const enCola = ts.filter((t) => t.estado === 'en cola').length;
  document.body.classList.toggle('trabajando', ts.some((t) => t.estado === 'en curso' || t.estado === 'en cola'));
  $('#trabajos').innerHTML = ts.filter((t) => t.estado === 'en curso' || t.estado === 'error').map((t) => `
    <div class="trabajo ${t.estado === 'error' ? 'error' : ''}">
      <b>${esc(t.titulo || '')}</b>
      <span>${esc(t.estado === 'error' ? 'Error: ' + t.error : t.etapa)}</span>
      ${t.estado === 'error' ? '' : `<div class="prog"><i style="width:${t.pct}%"></i></div>`}
    </div>`).join('') + (enCola ? `<div class="trabajo"><span>${enCola} ${enCola === 1 ? 'canción' : 'canciones'} en cola…</span></div>` : '');
  for (const t of ts) {
    if (t.estado === 'listo' && abrirAlTerminar.has(t.id)) {
      abrirAlTerminar.delete(t.id);
      await cargarLista();
      abrir(t.cancion);
    }
    if (t.estado === 'error') abrirAlTerminar.delete(t.id);
  }
  if (ts.some((t) => t.estado === 'en curso' || t.estado === 'en cola')) sondeo = setTimeout(sondear, 1500);
}

// subir un archivo de audio en vez de pegar un link (en un servidor en internet YouTube suele bloquear las descargas)
$('#btn-subir').onclick = () => $('#archivo').click();
$('#archivo').onchange = async () => {
  const f = $('#archivo').files[0];
  if (!f) return;
  const datos = new FormData();
  datos.append('archivo', f);
  $('#btn-subir').disabled = true;
  $('#trabajos').insertAdjacentHTML('afterbegin', `<div class="trabajo" id="subiendo"><b>${esc(f.name)}</b><span>Subiendo…</span></div>`);
  try {
    const r = await fetch('/api/canciones/subir', { method: 'POST', body: datos });
    const d = await r.json().catch(() => ({ error: r.status === 413 ? 'El archivo es muy grande (máximo 300 MB).' : 'No se pudo subir.' }));
    if (!r.ok) throw new Error(d.error || 'No se pudo subir.');
    silbato();
    seguir(d);
  } catch (e) { alert(e.message); } finally {
    $('#btn-subir').disabled = false;
    $('#archivo').value = '';
    const s = $('#subiendo'); if (s) s.remove();
  }
};
$('#form-url').onsubmit = async (ev) => {
  ev.preventDefault();
  try {
    seguir(await api('canciones', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: $('#url').value }) }));
    $('#url').value = '';
  } catch (e) { alert(e.message); }
};

// ================================================================= abrir canción
async function abrir(id) {
  pausar();
  const c = await api('canciones/' + encodeURIComponent(id));
  Object.assign(E, { id, st: 0, escala: 0, mute: {}, solo: {}, vol: {}, sel: -1, bucle: null });
  $('#repetir').checked = false;
  poner(c);
  E.vista = instrumentoPrincipal();
  c.pistas.forEach((p) => { E.vol[p.id] = 1; });
  // el metrónomo es una pista más del mezclador; prendido/apagado y volumen se recuerdan entre temas
  E.mute.metro = recordar('metro') !== '1';
  E.vol.metro = recordar('metro.vol') != null ? +recordar('metro.vol') : 0.7;
  A.pos = 0;
  $$('#lista li').forEach((li) => li.classList.toggle('activa', li.dataset.id === id));
  ['#pestanas', '#reproductor', '#panel-pistas'].forEach((s) => { $(s).hidden = false; });
  $('#t-total').textContent = mmss(c.duracion);
  document.title = `${c.titulo} · Maquinitabs`;
  pintarMezclador();
  pintar();
  cargarAudio();
}

// deja `c` (app.json) como canción abierta; también después de una corrección, sin recargar el audio
function poner(c) {
  if (!c.base) c.base = { acordes: c.compases.flatMap((x) => x.acordes.flatMap(([a, n]) => Array(n).fill(a))) };
  Object.assign(E, { c, compasActual: -1, seccionBucle: null, propios: null, detectados: null });
  E.unos = new Set(c.compases.filter((x) => !x.anacrusa).map((x) => x.beat));   // pulsos que son el "1"
  llenarBucle();
}

const ton = () => T.tonalidad(E.c.tonalidad, E.st);
const nom = (a) => (a === 'N.C.' ? 'N.C.' : T.transportar(a, E.st, ton().bemol));
const finCompas = (i) => (i + 1 < E.c.compases.length ? E.c.compases[i + 1].t : E.c.beats[E.c.beats.length - 1]);
// ¿Qué toca esta pista en cada pulso? Sale de SUS notas (la transcripción de esa pista), no de la armonía
// del tema, que sale de la mezcla y ahí el bajo pesa: un paseo de bajo C–G–A no es C–Gm–Am7 en la guitarra.
// Por tramo (un acorde del tema dentro de un compás) se juntan las notas de la pista:
//   - si encajan con el acorde del tema (y suenan su fundamental o su tercera) se escribe ese acorde;
//   - si no, se nombra el acorde que forman esas notas (tres notas distintas, o fundamental y quinta = power chord);
//   - si son notas sueltas que no arman acorde, es una línea (♪, está en la partitura);
//   - si la pista no suena, silencio (–). Nunca se rellena con lo de otro instrumento.
const LINEA = '♪';
const CALIDADES_PROPIAS = ['', 'm', '5', '7', 'm7', 'maj7', 'sus4', 'sus2', 'dim'];
const CLAVE_NOTAS = { guitar: 'guitarra', piano: 'piano', otros: 'otros' };
const ID_INST = { guitarra: 'guitar', piano: 'piano', otros: 'otros' };
// La pista «otros» de demucs junta lo que no es voz, guitarra, piano, bajo ni batería (sintes, vientos,
// cuerdas…). Se nombra con los créditos de la grabación (MusicBrainz) cuando los hay; los de la ficha del
// disco (Wikipedia) solo se mencionan, porque pueden no sonar en este tema.
const nombreOtros = () => ((E.c.creditos || {}).otros || 'Otros');
const hayOtros = () => (E.c.notas.otros || []).length > 0;     // sin notas = casi no suena: ni pestaña ni hoja
function avisoOtros() {
  const c = E.c.creditos || {};
  const fuentes = (c.fuentes || []).map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${u.includes('wikipedia') ? 'Wikipedia' : 'MusicBrainz'}</a>`).join(' y ');
  if (c.otros) return `Instrumentos según los créditos de la grabación (${fuentes}).`;
  if (c.en_el_disco) return `En el disco${c.disco ? ` «${esc(c.disco)}»` : ''} figuran: ${esc(c.en_el_disco.toLowerCase())} (${fuentes}); no todos tienen por qué sonar en este tema.`;
  return 'Lo que no es voz, guitarra, piano, bajo ni batería (sintes, vientos, cuerdas…).';
}
function nombrarNotas(w) {               // w[12] = peso de cada nota -> nombre de acorde o null
  const total = w.reduce((s, x) => s + x, 0);
  const hay = w.map((x) => x > 0.08 * total);
  let mejor = null;
  for (let r = 0; r < 12; r++) {
    if (!hay[r]) continue;
    CALIDADES_PROPIAS.forEach((q, orden) => {
      const tonos = T.notasAcorde({ raiz: r, calidad: q });
      const dentro = tonos.reduce((s, t) => s + w[t], 0) / total;
      const faltan = tonos.filter((t) => !hay[t]).length;
      const extra = hay.filter((h, t) => h && !tonos.includes(t)).length;
      if (q === '5' ? faltan > 0 || extra > 0 : faltan > (tonos.length > 3 ? 1 : 0) || tonos.length - faltan < 3) return;
      const p = dentro - 0.06 * faltan - 0.01 * orden + 0.03 * w[r] / total;
      if (dentro >= 0.8 && (!mejor || p > mejor.p)) mejor = { p, nombre: T.nota(r, T.tonalidad(E.c.tonalidad, 0).bemol) + q };
    });
  }
  return mejor && mejor.nombre;
}
function encaja(a, w) {                  // ¿las notas w son de ese acorde del tema?
  const x = T.parse(a);
  if (!x) return false;
  const tonos = T.notasAcorde(x);
  const total = w.reduce((s, v) => s + v, 0);
  const presentes = tonos.filter((t) => w[t] > 0.08 * total);
  return tonos.reduce((s, t) => s + w[t], 0) >= 0.8 * total && presentes.length >= 2
    && (presentes.includes(tonos[0]) || presentes.includes(tonos[1]));
}
// por pulso: acorde | LINEA | '' ; null si el tema no tiene esa pista. Lo detectado más lo corregido a mano.
function propios(p) {
  const det = detectados(p);
  if (!det) return null;
  E.propios = E.propios || {};
  if (!E.propios[p.id]) {
    const out = det.slice();
    (((E.c.correcciones || {}).pistas || {})[p.id] || []).forEach(([t, a]) => { out[pulsoEn(t)] = a; });
    E.propios[p.id] = out;
  }
  return E.propios[p.id];
}
function detectados(p) {
  const notas = p && E.c.notas[CLAVE_NOTAS[p.id]];
  if (!notas) return null;
  E.detectados = E.detectados || {};
  if (E.detectados[p.id]) return E.detectados[p.id];
  const nb = E.c.beats.length - 1;
  const w = Array.from({ length: nb }, () => new Array(12).fill(0));
  notas.forEach((n) => {
    for (let s = n.i; s < n.i + n.d; s++) { const k = s >> 2; if (k < nb) w[k][((n.m % 12) + 12) % 12] += 1; }
  });
  const suena = (k) => (!p.pulsos || p.pulsos[k]) && w[k].some((x) => x > 0);
  const out = new Array(nb).fill('');
  E.c.compases.forEach((c) => {
    let k = c.beat;
    c.acordes.forEach(([a, n]) => {
      const ks = Array.from({ length: n }, (_, j) => k + j).filter((j) => j < nb && suena(j));
      k += n;
      if (!ks.length) return;
      const suma = new Array(12).fill(0);
      ks.forEach((j) => w[j].forEach((x, t) => { suma[t] += x; }));
      const x = a !== 'N.C.' && encaja(a, suma) ? a : nombrarNotas(suma) || LINEA;
      ks.forEach((j) => { out[j] = x; });
    });
  });
  E.detectados[p.id] = out;
  return out;
}
// acordes de un compás tal como los toca una pista (p = null: la armonía completa del tema)
function acordesDe(c, p) {
  if (!p) return c.acordes;
  const pr = propios(p) || [];
  const out = [];
  for (let k = c.beat; k < c.beat + c.pulsos; k++) {
    const x = pr[k] || '';
    if (out.length && out[out.length - 1][0] === x) out[out.length - 1][1] += 1; else out.push([x, 1]);
  }
  // un pulso suelto de silencio entre dos tramos del mismo acorde es un respiro, no un corte
  for (let j = 1; j + 1 < out.length; j++) {
    if (out[j][0] === '' && out[j][1] === 1 && out[j - 1][0] === out[j + 1][0]) { out[j - 1][1] += 1 + out[j + 1][1]; out.splice(j, 2); j--; }
  }
  return out;
}
// la hoja que se muestra al abrir un tema: la pista que más pulsos toca en acordes; si ninguna, la armonía
function instrumentoPrincipal() {
  let mejor = 'armonia', max = 0;
  ['guitarra', 'piano', 'otros'].forEach((i) => {
    const p = pista(ID_INST[i]);
    if (!p || p.nivel < 0.04 || (i === 'otros' && !hayOtros())) return;
    const n = (propios(p) || []).filter((x) => x && x !== LINEA && x !== 'N.C.').length;
    if (n > max) { max = n; mejor = i; }
  });
  return mejor;
}
function acordesUsados(p) {           // [{nombre (transportado), pulsos}] por orden de uso; p = solo lo que toca esa pista
  const m = new Map();
  E.c.compases.forEach((c) => acordesDe(c, p).forEach(([a, n]) => { if (a && a !== 'N.C.' && a !== LINEA) m.set(a, (m.get(a) || 0) + n); }));
  return [...m].sort((a, b) => b[1] - a[1]).map(([a, n]) => ({ nombre: nom(a), pulsos: n }));
}

// ================================================================= audio
function ctxAudio() {
  if (!A.ctx) A.ctx = new (window.AudioContext || window.webkitAudioContext)();
  return A.ctx;
}
async function cargarAudio() {
  const turno = ++A.carga;
  const estabaTocando = A.tocando;
  pausar();
  A.listo = false;
  $('#btn-play').disabled = true;
  const ctx = ctxAudio();
  const pistas = E.c.pistas;
  let hechas = 0;
  const estado = () => { $('#estado-audio').textContent = `${E.st ? 'transportando' : 'cargando'} ${hechas}/${pistas.length}…`; };
  estado();
  const nuevos = {};
  try {
    await Promise.all(pistas.map(async (p) => {
      const r = await fetch(`/api/canciones/${encodeURIComponent(E.id)}/audio/${p.id}?st=${E.st}`);
      if (!r.ok) throw new Error('No pude cargar la pista ' + p.nombre);
      const buf = await ctx.decodeAudioData(await r.arrayBuffer());
      if (turno !== A.carga) return;
      nuevos[p.id] = buf;
      hechas++; estado();
    }));
  } catch (e) {
    if (turno === A.carga) $('#estado-audio').textContent = e.message;
    return;
  }
  if (turno !== A.carga) return;
  A.buffers = nuevos;
  pistas.forEach((p) => { if (!A.gains[p.id]) { A.gains[p.id] = ctx.createGain(); A.gains[p.id].connect(ctx.destination); } });
  aplicarMezcla();
  A.listo = true;
  $('#btn-play').disabled = false;
  $('#estado-audio').textContent = '';
  if (estabaTocando) tocar();
}
function tiempo() {
  if (!A.tocando) return A.pos;
  return Math.min(E.c.duracion, A.pos + Math.max(0, A.ctx.currentTime - A.t0));
}
function tocar(sinCuenta) {
  if (!A.listo || A.tocando) return;
  const ctx = ctxAudio();
  ctx.resume();
  if (A.pos >= E.c.duracion - 0.2) A.pos = 0;
  let cuando = ctx.currentTime + 0.06;
  if ($('#cuenta').checked && !sinCuenta) cuando += cuentaPrevia(cuando);
  M.sig = primerPulsoDesde(A.pos);
  M.reloj = setInterval(programarMetro, 50);
  A.fuentes = E.c.pistas.map((p) => {
    const f = ctx.createBufferSource();
    f.buffer = A.buffers[p.id];
    f.connect(A.gains[p.id]);
    f.start(cuando, A.pos);
    return f;
  });
  A.t0 = cuando;
  A.tocando = true;
  $('#btn-play').textContent = '❚❚';
}
function pausar() {
  if (!A.tocando) return;
  A.pos = tiempo();
  pararMetro();
  A.fuentes.forEach((f) => { try { f.stop(); } catch (e) { /* ya parada */ } });
  A.fuentes = [];
  A.tocando = false;
  $('#btn-play').textContent = '▶';
}
function ir(t) {
  const era = A.tocando;
  E.pararEn = null;
  pausar();
  A.pos = Math.max(0, Math.min(E.c.duracion, t));
  const b = repitiendo();
  saltoManual = !!(b && A.pos >= finCompas(b.fin));   // fue más allá del tramo a repetir (clic en otro compás)
  if (era) tocar(true);         // al saltar o repetir una sección no se vuelve a contar
  refrescar(true);
}
// íconos de las pistas (trazo con el color de la pista)
const ICONOS = {
  vocals: '<svg viewBox="0 0 24 24"><rect x="9" y="2.5" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21.5M8.5 21.5h7"/></svg>',
  guitar: '<svg viewBox="0 0 24 24"><path d="M13.6 10.4 20 4"/><path d="M18.6 2.6l2.8 2.8"/><path d="M10.4 8.6c1.6-.4 3.3.4 3.6 1.9.3 1.3-.6 2.2-1.2 2.9.9.6 1.4 1.7 1.2 2.9-.4 2.8-3.6 4.6-6.6 3.8-3.4-.9-5.1-4.6-3.6-7.6.8-1.5 2.1-2.4 3.4-2.6.8-.1 1.4-1 3.2-1.3z"/><circle cx="8.8" cy="15.2" r="1.3"/></svg>',
  piano: '<svg viewBox="0 0 24 24"><rect x="2.5" y="5" width="19" height="14" rx="1.5"/><path d="M7.25 12.5V19M12 12.5V19M16.75 12.5V19"/><path d="M6 5v7.5h2.5V5M10.75 5v7.5h2.5V5M15.5 5v7.5H18V5" fill="currentColor"/></svg>',
  bass: '<svg viewBox="0 0 24 24"><path d="M11.6 12.4 21 3"/><path d="M19.6 1.6l2.8 2.8M18 4.6l1.4 1.4"/><path d="M8.6 10.6c1.4-.3 2.9.4 3.1 1.7.2 1.1-.5 1.9-1 2.5.8.5 1.2 1.5 1 2.5-.3 2.5-3.1 4-5.7 3.3-2.9-.8-4.4-4-3.1-6.6.7-1.3 1.8-2.1 2.9-2.3.7-.1 1.2-.9 2.8-1.1z"/></svg>',
  drums: '<svg viewBox="0 0 24 24"><path d="M4 20 17.5 6.5M20 20 6.5 6.5"/><circle cx="18.6" cy="5.4" r="1.6" fill="currentColor"/><circle cx="5.4" cy="5.4" r="1.6" fill="currentColor"/><ellipse cx="12" cy="18.5" rx="7" ry="2.3"/></svg>',
  otros: '<svg viewBox="0 0 24 24"><path d="M2.5 11h3v2h-3zM5.5 12h8.5"/><path d="M14 9.5 21.5 6v12L14 14.5z"/><path d="M8 12V9M10.5 12V9M13 12V9"/><path d="M7.5 15.5c1.5 1.6 4.5 1.6 6 0"/></svg>',
  other: '<svg viewBox="0 0 24 24"><path d="M9 18V6l11-2.5v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="15.5" r="2.5"/></svg>',
  metro: '<svg viewBox="0 0 24 24"><path d="M9.5 3h5l4 18h-13z"/><path d="M6.5 16.5h11M12 16.5 17 6"/><circle cx="15.6" cy="9" r="1.2" fill="currentColor"/></svg>',
};
function recordar(clave, valor) {
  try {
    if (valor === undefined) return localStorage.getItem('maquinitabs.' + clave);
    localStorage.setItem('maquinitabs.' + clave, String(valor));
  } catch (e) { /* sin almacenamiento */ }
  return null;
}
function gananciaMetro() {             // a esta van los clics del metrónomo (la cuenta previa va directo)
  const ctx = ctxAudio();
  if (!A.gMetro) { A.gMetro = ctx.createGain(); A.gMetro.connect(ctx.destination); }
  return A.gMetro;
}
function aplicarMezcla() {
  const haySolo = Object.values(E.solo).some(Boolean);
  E.c.pistas.map((p) => p.id).concat('metro').forEach((id) => {
    const suena = haySolo ? E.solo[id] : !E.mute[id];
    const g = id === 'metro' ? gananciaMetro() : A.gains[id];
    if (g) g.gain.value = suena ? E.vol[id] : 0;
    const fila = $(`.pista[data-id="${id}"]`);
    if (fila) fila.classList.toggle('apagada', !suena);
  });
}
function pintarMezclador() {
  const fila = (id, nombre, color, extra, vol) => `
    <div class="pista" data-id="${id}">
      <span class="icono" style="color:${color}" aria-hidden="true">${ICONOS[id] || ICONOS.otros}</span>
      <div class="nombre">${nombre}${extra}</div>
      <button class="m${E.mute[id] ? ' on' : ''}" title="${id === 'metro' ? 'Prender o apagar el metrónomo' : 'Mutear'}">M</button><button class="s" title="Solo">S</button>
      <input type="range" min="0" max="1.5" step="0.01" value="${vol}" title="Volumen">
    </div>`;
  $('#mezclador').innerHTML = E.c.pistas.map((p) => fila(p.id, p.nombre, COLORES[p.id],
    p.nivel < 0.04 ? '<small>casi no suena en este tema</small>'
      : p.id === 'otros' && nombreOtros() !== 'Otros' ? `<small>${esc(nombreOtros().toLowerCase())}</small>` : '', 1)).join('')
    + fila('metro', 'Metrónomo', '#9ca3af', '', E.vol.metro);
  $$('.pista').forEach((f) => {
    const id = f.dataset.id;
    $('.m', f).onclick = (ev) => {
      E.mute[id] = !E.mute[id]; ev.target.classList.toggle('on', E.mute[id]); aplicarMezcla();
      if (id === 'metro') recordar('metro', E.mute.metro ? '0' : '1');
    };
    $('.s', f).onclick = (ev) => { E.solo[id] = !E.solo[id]; ev.target.classList.toggle('on', E.solo[id]); aplicarMezcla(); };
    $('input', f).oninput = (ev) => { E.vol[id] = +ev.target.value; aplicarMezcla(); if (id === 'metro') recordar('metro.vol', E.vol.metro); };
  });
  aplicarMezcla();
}

// ================================================================= vistas
function pintar() {
  if (!E.c) return;
  E.geo = []; E.compasActual = -1;
  const t = ton();
  $('#tonalidad').textContent = t.nombre;
  $('#st-valor').textContent = E.st ? `${E.st > 0 ? '+' : ''}${E.st} semitono${Math.abs(E.st) === 1 ? '' : 's'}` : 'original';
  // pestaña de la pista «otros»: solo si el análisis la transcribió, con el nombre de sus instrumentos
  const tabOtros = $('#pestanas [data-vista="otros"]');
  tabOtros.hidden = !hayOtros();
  tabOtros.textContent = nombreOtros();
  if (E.vista === 'otros' && tabOtros.hidden) E.vista = 'armonia';
  if (!MODOS[E.vista].includes(E.modo)) E.modo = MODOS[E.vista][0];
  // solo se corrigen a mano las hojas de acordes: la partitura es la transcripción y la improvisación sale de los acordes
  const sinPista = E.vista !== 'armonia' && !propios(pista(ID_INST[E.vista]));
  const editable = E.modo === 'acordes' && !sinPista;
  if (!editable) E.edicion = false;
  $$('#pestanas [data-vista]').forEach((b) => b.classList.toggle('activa', b.dataset.vista === E.vista));
  $('#btn-editar').classList.toggle('on', !!E.edicion);
  $('#btn-editar').disabled = !editable;
  $('#btn-editar').title = editable ? 'Corregir la hoja de acordes de esta pestaña escuchando el tema'
    : E.modo === 'partitura' ? `La partitura no se edita a mano${MODOS[E.vista].includes('acordes') ? ': se corrigen los acordes, en «Acordes»' : ''}`
    : E.modo === 'impro' ? `La improvisación se arma sola a partir de los acordes del tema: corregilos en «Acordes»${MODOS[E.vista].includes('acordes') ? '' : ' de «Tema completo»'}`
    : 'Este tema no tiene pista propia de este instrumento';
  const v = $('#vista');
  const arriba = v.scrollTop;
  v.innerHTML = `<div class="hoja ${E.modo} ${E.vista}">${cabecera()}${E.edicion ? '' : selectorModos()}<div id="contenido"></div></div>`;
  $$('#sel-modo button', v).forEach((b) => {
    b.classList.toggle('on', b.dataset.m === E.modo);
    b.onclick = () => { E.modo = b.dataset.m; pintar(); };
  });
  ({ acordes: vistaAcordes, partitura: () => vistaPartitura(E.vista), impro: vistaImpro })[E.modo]($('#contenido'));
  v.scrollTop = arriba;
  refrescar(true);
  marcarBucle();
}
// qué se puede ver de cada pestaña: el bajo y la voz tocan una nota por vez (no tienen hoja de acordes) y
// la armonía es el resumen de todas las pistas (no tiene partitura)
const MODOS = {
  armonia: ['acordes', 'impro'],
  guitarra: ['acordes', 'partitura', 'impro'], piano: ['acordes', 'partitura', 'impro'], otros: ['acordes', 'partitura', 'impro'],
  bajo: ['partitura', 'impro'], voz: ['partitura', 'impro'],
};
const NOMBRE_MODO = { acordes: 'Acordes', partitura: 'Partitura', impro: 'Improvisación' };
function selectorModos() {
  const partitura = E.vista === 'guitarra' || E.vista === 'bajo' ? 'Partitura y tablatura' : 'Partitura';
  return `<div class="no-imprimir" style="margin-top:12px"><div class="selector" id="sel-modo">${MODOS[E.vista].map((m) =>
    `<button data-m="${m}">${m === 'partitura' ? partitura : NOMBRE_MODO[m]}</button>`).join('')}</div></div>`;
}
function cabecera() {
  const c = E.c;
  return `<header><h2>${esc(c.titulo)}</h2><span class="artista">${esc(c.artista)}</span>
    <span class="datos">${Math.round(c.tempo)} BPM · ${c.compas}/4 · Tonalidad <b>${ton().nombre}</b>${E.st ? ` (original ${T.tonalidad(c.tonalidad, 0).nombre})` : ''}</span></header>`;
}
function tituloSeccion(s) {
  const c = E.c.compases[s.ini];
  return `<h3><span>${esc(s.nombre)}</span><small>${mmss(c.t)} · ${s.fin - s.ini} compases</small></h3>`;
}
const seccionDe = (i) => E.c.secciones.find((s) => i >= s.ini && i < s.fin);
const pista = (id) => E.c.pistas.find((p) => p.id === id);

// ----------------------------------------------------------------- acordes y estructura
function vistaAcordes(el) {
  const ed = E.edicion;
  const armonia = E.vista === 'armonia';
  const pInst = armonia ? null : pista(ID_INST[E.vista]);
  const usados = acordesUsados(pInst);
  const tocados = new Set(correccionesDe(pInst).map(([t]) => pulsoEn(t)));
  const el_inst = { guitarra: 'la guitarra', piano: 'el piano', otros: `la pista ${nombreOtros()}` }[E.vista];
  let h = ed ? barraEdicion(usados, pInst, el_inst) : `<p class="aviso no-imprimir">${armonia
    ? 'La armonía completa del tema, sacada de la mezcla de todas las pistas. Para corregirla, «Editar hoja».'
    : !propios(pInst)
    ? `Este tema se separó sin pista de ${E.vista}: volvé a bajarlo desde el link para tener su hoja. La armonía completa está en la pestaña «Tema completo».`
    : pInst.nivel < 0.04
      ? `En esta grabación casi no suena ${el_inst}. La armonía completa del tema está en la pestaña «Tema completo».`
      : `Solo lo que toca ${el_inst}, sacado de su pista: – no suena, ${LINEA} toca una línea o notas sueltas (ver «Partitura»).${
        E.vista === 'otros' ? ' ' + avisoOtros() : ''}`}</p>`;
  h += `<div class="diagramas">${usados.map((a) => `<div class="cont" data-acorde="${esc(a.nombre)}">${
    E.vista === 'guitarra' || armonia ? T.svgGuitarra(a.nombre, a.nombre) : T.svgTeclado(T.notasAcorde(T.parse(a.nombre)), T.parse(a.nombre).raiz, a.nombre)}</div>`).join('')}</div>`;
  E.c.secciones.forEach((s) => {
    h += tituloSeccion(s) + '<div class="fila-compases">';
    let previo = null;
    for (let i = s.ini; i < s.fin; i++) {
      const c = E.c.compases[i];
      const acs = acordesDe(c, pInst);
      const firma = JSON.stringify(acs);
      const calla = acs.every(([a]) => !a || a === 'N.C.') ? ' calla' : '';
      const repite = !ed && firma === previo && acs.length === 1 && !calla && (i - s.ini) % 4 !== 0;
      const metro = !c.anacrusa && c.pulsos !== E.c.compas ? `<span class="metro">${c.pulsos}/4</span>` : '';
      let clases = calla;
      if (ed && i === E.sel) clases += ' sel';
      if (ed && Array.from({ length: c.pulsos }, (_, j) => c.beat + j).some((k) => tocados.has(k))) clases += ' corregido';
      h += `<div class="compas${clases}" data-c="${i}" style="grid-template-columns:${acs.map(([, n]) => n + 'fr').join(' ')}"><sup>${i + 1}</sup>${metro}${
        repite ? '<span class="rep">%</span>' : acs.map(([a]) => (a === LINEA ? `<span class="linea" title="Toca una línea o notas sueltas: ver la partitura">${LINEA}</span>` : a ? `<span>${esc(nom(a))}</span>` : '<span class="silencio">–</span>')).join('')}</div>`;
      previo = firma;
    }
    h += '</div>';
  });
  h += `<p class="aviso">Generado automáticamente a partir del audio — revisar de oído. ${ed ? '' : 'Hacé clic en un compás para saltar ahí; con «Editar hoja» podés corregir acordes y compases.'}</p>`;
  el.innerHTML = h;
  $$('.compas', el).forEach((d) => {
    const i = +d.dataset.c;
    E.geo[i] = { fila: d.parentElement, celda: d };
    d.onclick = () => {
      ir(E.c.compases[i].t);
      if (E.edicion) { E.sel = i; pintar(); const p = $('#ed-pulsos input'); if (p) { p.focus(); p.select(); } }
    };
  });
  if (ed) conectarEdicion(el);
}

// ================================================================= edición de la hoja (acordes y compases)
// Las correcciones se guardan en el servidor por tiempo: {compas, acordes: [[t, nombre]…], unos: [t…]}.
function pulsoEn(t) {
  const bs = E.c.beats;
  let m = 0;
  for (let k = 1; k < bs.length - 1; k++) if (Math.abs(bs[k] - t) < Math.abs(bs[m] - t)) m = k;
  return m;
}
const pulsosDe = (c) => c.acordes.flatMap(([a, n]) => Array(n).fill(a));     // acorde de cada pulso del compás
const SOLFEO = { do: 'C', re: 'D', mi: 'E', fa: 'F', sol: 'G', la: 'A', si: 'B' };
// "lam7", "Sib", "A-7", "CM7", "nc"… -> nombre como los usa la app; '' = vacío; null = no se entiende
function normalizarAcorde(txt) {
  let s = txt.trim().replace(/\s+/g, '');
  if (!s) return '';
  if (/^(n\.?c\.?|-|–|x)$/i.test(s)) return 'N.C.';
  s = s.replace(/^(do|re|mi|fa(?!dd|ug)|sol|la|si)/i, (x) => SOLFEO[x.toLowerCase()]);
  s = s[0].toUpperCase() + s.slice(1);
  const m = /^([A-G][#b]?)([^/]*)(?:\/([A-Ga-g][#b]?))?$/.exec(s);
  if (!m) return null;
  const q = m[2].replace(/^(min|-)/, 'm').replace(/^(M7|Maj7|MAJ7|Δ7?)/, 'maj7').replace(/^(M|maj)$/, '')
    .replace(/^°7/, 'dim7').replace(/^°/, 'dim').replace(/^\+/, 'aug').replace(/^ø7?/, 'm7b5').replace(/^mmaj7$/i, 'mMaj7');
  if (/[^A-Za-z0-9#+()]/.test(q) || q.length > 9) return null;
  return m[1] + q + (m[3] ? '/' + m[3][0].toUpperCase() + m[3].slice(1) : '');
}

// p = pista cuya hoja se corrige (null: la armonía del tema)
const correccionesDe = (p) => (p ? ((E.c.correcciones || {}).pistas || {})[p.id] : (E.c.correcciones || {}).acordes) || [];
const pulsosHoja = (cp, p) => (p ? (propios(p) || []).slice(cp.beat, cp.beat + cp.pulsos) : pulsosDe(cp));
// lo que muestra una casilla del editor: en la hoja de un instrumento '' es «no toca»
const casilla = (a, p) => (p && !a ? '–' : a === LINEA ? LINEA : nom(a));
// texto de una casilla -> valor sin transportar; undefined = vacía (sigue el anterior); null = no se entiende.
// En la hoja de un instrumento «–» es '' (no toca) y «♪» una línea.
function leerCasilla(txt, p) {
  if (p && /^\s*(♪|linea|línea)\s*$/i.test(txt)) return LINEA;
  const v = normalizarAcorde(txt);
  if (v === '') return undefined;
  if (v === null || v === 'N.C.') return v === 'N.C.' && p ? '' : v;
  return E.st ? T.transportar(v, -E.st, T.tonalidad(E.c.tonalidad, 0).bemol) : v;
}

function barraEdicion(usados, p, el_inst) {
  const c = E.c, k = c.correcciones || {};
  const n = correccionesDe(p).length;
  const hechas = [n ? `${n} ${n === 1 ? 'pulso corregido' : 'pulsos corregidos'}` : '', k.unos ? 'compases cambiados a mano' : ''].filter(Boolean).join(' · ');
  let h = `<div class="editor no-imprimir"><div class="ed-linea">
      <b>${p ? `Editando la hoja de ${esc(el_inst.replace(/^la pista /, ''))}` : 'Editando la armonía del tema'}</b>
      <span>Compás del tema <span class="selector" id="ed-metro">${[3, 4].map((x) => `<button data-n="${x}" class="${c.compas === x ? 'on' : ''}">${x}/4</button>`).join('')}</span></span>
      <span class="hueco"></span>
      ${hechas ? `<small>${hechas}</small><button id="ed-deshacer" title="${p ? `Borra las correcciones de la hoja de ${esc(el_inst)}` : 'Borra todas las correcciones de acordes y compases'}">Volver a lo detectado</button>` : ''}
      <button id="ed-salir" class="primario">Listo</button></div>`;
  const cp = c.compases[E.sel];
  if (!cp) {
    h += '<div class="ed-linea"><span class="aviso" style="margin:0">Hacé clic en un compás para corregir sus acordes o su cantidad de pulsos. Todo se guarda solo.</span></div>';
  } else {
    const ps = pulsosHoja(cp, p);
    h += `<div class="ed-linea"><b>Compás ${E.sel + 1}</b><small>${mmss(cp.t)}</small>
      <span id="ed-pulsos">${ps.map((a, j) => `<label><small>${j + 1}</small><input data-j="${j}" list="ed-lista" autocomplete="off" spellcheck="false"
        placeholder="sigue" value="${j === 0 || a !== ps[j - 1] ? esc(casilla(a, p)) : ''}"></label>`).join('')}</span>
      <button id="ed-ok" class="primario" title="Guarda y pasa al compás siguiente (Enter)">Guardar ↵</button>
      <button id="ed-oir" title="Reproduce solo este compás">▶ Escuchar</button></div>
      <div class="ed-linea"><span>Pulsos del compás <button id="ed-menos" title="Un pulso menos: los compases siguientes se corren">−</button>
        <b>${cp.pulsos}</b> <button id="ed-mas" title="Un pulso más: los compases siguientes se corren">+</button></span>
      <button id="ed-partir"${cp.pulsos < 2 ? ' disabled' : ''}>Partir en dos</button>
      <button id="ed-unir"${E.sel + 1 >= c.compases.length ? ' disabled' : ''}>Unir con el siguiente</button>
      <span class="aviso" style="margin:0">Un acorde por pulso; vacío = sigue el anterior. ${p
        ? `«–» = no toca, «${LINEA}» = línea o notas sueltas. Los pulsos de un compás cambian en todas las hojas.`
        : '«nc» = sin acorde.'}</span></div>
      <datalist id="ed-lista">${usados.map((a) => `<option value="${esc(a.nombre)}">`).join('')}</datalist>`;
  }
  return h + '</div>';
}

async function enviarCorrecciones(cambio) {
  const k = E.c.correcciones || {};
  const cuerpo = { compas: k.compas || null, acordes: k.acordes || [], unos: k.unos || null, pistas: k.pistas || {}, ...cambio };
  try {
    const r = await api(`canciones/${encodeURIComponent(E.id)}/correcciones`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
    if (r.trabajo) { E.sel = -1; seguir(r.trabajo); return false; }
    poner(r.cancion);
    return true;
  } catch (e) { alert(e.message); return false; }
}

async function guardarCompas() {
  const c = E.c, cp = c.compases[E.sel];
  if (!cp) return;
  const inst = E.vista === 'armonia' ? null : pista(ID_INST[E.vista]);
  const antes = pulsosHoja(cp, inst);
  let actual = cp.beat > 0 ? pulsosHoja(c.compases[E.sel - 1], inst).slice(-1)[0] : inst ? '' : 'N.C.';
  const nuevos = [];
  for (const inp of $$('#ed-pulsos input')) {
    const v = leerCasilla(inp.value, inst);
    inp.classList.toggle('mal', v === null);
    if (v === null) { inp.focus(); return; }
    if (v !== undefined) actual = v;
    nuevos.push(actual);
  }
  if (nuevos.some((a, j) => a !== antes[j])) {
    const detectado = inst ? detectados(inst) : c.base.acordes;
    const m = new Map(correccionesDe(inst).map(([t, a]) => [pulsoEn(t), a]));
    nuevos.forEach((a, j) => { if (a === detectado[cp.beat + j]) m.delete(cp.beat + j); else m.set(cp.beat + j, a); });
    const lista = [...m].map(([k, a]) => [c.beats[k], a]);
    if (!await enviarCorrecciones(inst ? { pistas: { ...(c.correcciones || {}).pistas, [inst.id]: lista } } : { acordes: lista })) return;
  }
  E.sel = Math.min(E.sel + 1, E.c.compases.length - 1);
  pintar();
  const sel = $('.compas.sel');
  if (sel) seguirCursor(sel, true);
  const p = $('#ed-pulsos input');
  if (p) { p.focus(); p.select(); }
}

// mueve las barras de compás: `fn` recibe el pulso inicial de cada compás y devuelve la lista nueva
async function cambiarCompases(fn) {
  const total = E.c.beats.length - 1;
  const ini = [...new Set(fn(E.c.compases.map((x) => x.beat)).filter((b) => b >= 0 && b < total))].sort((a, b) => a - b);
  if (await enviarCorrecciones({ unos: ini.map((k) => E.c.beats[k]) })) { E.sel = Math.min(E.sel, E.c.compases.length - 1); pintar(); }
}

function conectarEdicion(el) {
  const i = E.sel, cp = E.c.compases[i];
  const al = (id, fn) => { const b = $(id, el); if (b) b.onclick = fn; };
  al('#ed-salir', () => { E.edicion = false; pintar(); });
  al('#ed-deshacer', async () => {
    const p = E.vista === 'armonia' ? null : pista(ID_INST[E.vista]);
    const ok = p
      ? confirm('¿Borrar las correcciones de esta hoja y volver a lo que detectó la app? La armonía del tema y las otras hojas no cambian.')
        && await enviarCorrecciones({ pistas: { ...(E.c.correcciones || {}).pistas, [p.id]: [] } })
      : confirm('¿Borrar todas las correcciones de acordes y compases de este tema y volver a lo que detectó la app?') && await enviarCorrecciones({ acordes: [], unos: null });
    if (ok) { E.sel = -1; pintar(); }
  });
  $$('#ed-metro button', el).forEach((b) => {
    b.onclick = () => {
      const n = +b.dataset.n;
      if (n === E.c.compas) return;
      if (confirm(`¿Pasar el tema a ${n}/4? Se vuelve a analizar (menos de un minuto). Los acordes que corregiste se conservan; los compases que cambiaste a mano se vuelven a calcular.`)) enviarCorrecciones({ compas: n });
    };
  });
  if (!cp) return;
  al('#ed-ok', guardarCompas);
  al('#ed-oir', () => { ir(cp.t); E.pararEn = finCompas(i); E.volverA = cp.t; if (!A.tocando) tocar(true); });
  al('#ed-menos', () => { if (cp.pulsos > 1) cambiarCompases((ini) => ini.map((b, j) => (j > i ? b - 1 : b))); });
  al('#ed-mas', () => cambiarCompases((ini) => ini.map((b, j) => (j > i ? b + 1 : b))));
  al('#ed-partir', () => cambiarCompases((ini) => ini.concat(cp.beat + Math.ceil(cp.pulsos / 2))));
  al('#ed-unir', () => cambiarCompases((ini) => ini.filter((_, j) => j !== i + 1)));
  $$('#ed-pulsos input', el).forEach((inp) => {
    inp.onkeydown = (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); guardarCompas(); }
      if (ev.key === 'Escape') { E.sel = -1; pintar(); }
    };
    inp.oninput = () => inp.classList.remove('mal');
  });
}

// ----------------------------------------------------------------- partitura (bajo / voz)
const DURS = [[16, 'w'], [12, 'hd'], [8, 'h'], [6, 'qd'], [4, 'q'], [3, '8d'], [2, '8'], [1, '16']];
function partir(p, L) {               // posición y largo en semicorcheas -> [[casillas, duración vex]]
  const out = [];
  while (L > 0) {
    const r = p % 4;
    let d;
    if (r === 0) {
      if (L >= 16 && p % 16 === 0) d = 16; else if (L >= 12 && p % 8 === 0) d = 12; else if (L >= 8 && p % 8 === 0) d = 8;
      else if (L >= 6) d = 6; else if (L >= 4) d = 4; else d = L;
    } else if (r === 2) d = L >= 2 ? 2 : 1;
    else d = 1;
    out.push([d, DURS.find((x) => x[0] === d)[1]]);
    p += d; L -= d;
  }
  return out;
}
function notasTransportadas(tipo) {
  let ns = E.c.notas[tipo].map((n) => ({ ...n, m: n.m + E.st }));
  let octava = 0;
  if (tipo === 'bajo') ns.forEach((n) => { while (n.m < 28) n.m += 12; while (n.m > 60) n.m -= 12; });
  else if (ns.length) {
    // semicorchea suelta, sin notas pegadas: casi siempre una respiración o una consonante
    ns = ns.filter((n, k) => n.d > 1 || (k > 0 && ns[k - 1].i + ns[k - 1].d === n.i) || (k + 1 < ns.length && ns[k + 1].i === n.i + 1));
    // la voz no canta semicorcheas sueltas: un adorno de una casilla se lo queda la nota vecina
    // (salvo que sea la misma nota repetida, que sí es una sílaba nueva)
    const suave = [];
    ns.forEach((n, k) => {
      const ant = suave[suave.length - 1], sig = ns[k + 1];
      const pegaAnt = ant && ant.i + ant.d === n.i, pegaSig = sig && sig.i === n.i + n.d;
      if (n.d === 1 && pegaAnt && Math.abs(ant.m - n.m) <= 2 && ant.m !== n.m) ant.d += 1;
      else if (n.d === 1 && pegaSig && Math.abs(sig.m - n.m) <= 2 && sig.m !== n.m) { sig.i -= 1; sig.d += 1; }
      else suave.push(n);
    });
    ns = suave;
    const orden = ns.map((n) => n.m).sort((a, b) => a - b);
    if (orden[orden.length >> 1] < 60) octava = 12;       // voz grave: se escribe una 8ª arriba (clave de sol 8vb)
  }
  return { ns, octava };
}
// notas polifónicas (guitarra, piano) -> acordes con un solo ritmo: cada ataque dura hasta el siguiente
function agrupar(ns) {
  const porInicio = new Map();
  ns.forEach((n) => { if (!porInicio.has(n.i)) porInicio.set(n.i, []); porInicio.get(n.i).push(n); });
  const inicios = [...porInicio.keys()].sort((a, b) => a - b);
  return inicios.map((i, k) => {
    const g = porInicio.get(i);
    const sig = k + 1 < inicios.length ? inicios[k + 1] : Infinity;
    return { i, d: Math.min(Math.max(...g.map((n) => n.d)), sig - i), ms: [...new Set(g.map((n) => n.m))].sort((a, b) => a - b) };
  });
}
function notasPoli(tipo) {
  const lo = tipo === 'guitarra' ? 40 : 21, hi = tipo === 'guitarra' ? 88 : 108;
  return agrupar((E.c.notas[tipo] || []).map((n) => {
    let m = n.m + E.st;
    while (m < lo) m += 12;
    while (m > hi) m -= 12;
    return { ...n, m };
  }));
}
function eventosCompas(ns, c) {       // -> [{d, dur, ms|null, liga (con la siguiente), entra (viene ligada)}]
  const s0 = c.beat * 4, s1 = s0 + c.pulsos * 4, ev = [];
  let p = s0;
  const silencio = (hasta) => { if (hasta > p) partir(p - s0, hasta - p).forEach(([d, dur]) => ev.push({ d, dur, ms: null })); p = hasta; };
  for (const n of ns) {
    if (n.i + n.d <= s0) continue;
    if (n.i >= s1) break;
    const a = Math.max(n.i, s0), b = Math.min(n.i + n.d, s1);
    if (a < p) continue;
    silencio(a);
    const trozos = partir(a - s0, b - a);
    trozos.forEach(([d, dur], k) => ev.push({ d, dur, ms: n.ms, entra: k === 0 && n.i < s0, liga: k < trozos.length - 1 || n.i + n.d > s1 }));
    p = b;
  }
  if (!ev.length) return [{ d: c.pulsos * 4, dur: 'w', ms: null, entero: true }];
  silencio(s1);
  return ev;
}
const CUERDAS_BAJO = [43, 38, 33, 28];
function posBajo(m) {
  let mejor = { str: 4, fret: Math.max(0, m - 28) };
  CUERDAS_BAJO.forEach((ab, k) => { const f = m - ab; if (f >= 0 && f < mejor.fret) mejor = { str: k + 1, fret: f }; });
  return mejor;
}
// guitarra: reparte las notas de un acorde en cuerdas distintas buscando la posición más cómoda
const CUERDAS_GUITARRA = [64, 59, 55, 50, 45, 40];
const memoGuitarra = new Map();
function posGuitarra(ms) {
  const clave = ms.join(',');
  if (memoGuitarra.has(clave)) return memoGuitarra.get(clave);
  const opciones = ms.map((m) => CUERDAS_GUITARRA.map((ab, k) => ({ str: k + 1, fret: m - ab, m })).filter((o) => o.fret >= 0 && o.fret <= 19));
  let mejor = null;
  const probar = (k, elegidas) => {
    if (k === opciones.length) {
      const pisadas = elegidas.filter((o) => o.fret > 0).map((o) => o.fret);
      const tramo = pisadas.length ? Math.max(...pisadas) - Math.min(...pisadas) : 0;
      const costo = (ms.length - elegidas.length) * 100 + (tramo > 4 ? 60 : 0) + tramo * 3 + elegidas.reduce((s, o) => s + o.fret, 0) * 0.4;
      if (!mejor || costo < mejor.costo) mejor = { costo, pos: elegidas.slice() };
      return;
    }
    opciones[k].forEach((o) => { if (!elegidas.some((e) => e.str === o.str)) { elegidas.push(o); probar(k + 1, elegidas); elegidas.pop(); } });
    probar(k + 1, elegidas);                       // o dejar esta nota afuera (cuesta 100)
  };
  probar(0, []);
  const pos = mejor.pos.sort((a, b) => b.str - a.str);
  memoGuitarra.set(clave, pos);
  return pos;
}

const PARTITURAS = {
  bajo: { nombre: 'línea de bajo', clave: 'bass', sube: 12, tab: 4, alto: 262 },
  voz: { nombre: 'melodía de voz', clave: 'treble', sube: 0, alto: 140 },
  guitarra: { nombre: 'guitarra', clave: 'treble', sube: 12, tab: 6, alto: 296, poli: true },
  piano: { nombre: 'piano', clave: 'treble', sube: 0, manoIzq: true, alto: 262, poli: true },
  otros: { nombre: 'otros instrumentos', clave: 'treble', sube: 0, manoIzq: true, alto: 262, poli: true },
};

function vistaPartitura(tipo, el = $('#contenido')) {
  const VF = Vex.Flow;
  const t = ton();
  const P = PARTITURAS[tipo];
  let ns, octava = 0;
  if (P.poli) ns = notasPoli(tipo);
  else { const r = notasTransportadas(tipo); octava = r.octava; ns = r.ns.map((n) => ({ i: n.i, d: n.d, ms: [n.m] })); }
  const nombres = (t.bemol ? T.BEMOL : T.SOST).map((x) => x.toLowerCase());
  const key = (m) => { const w = m + P.sube + octava; return `${nombres[T.mod(w)]}/${Math.floor(w / 12) - 1}`; };

  let intro = '';
  if (P.poli && !E.c.notas[tipo]) intro = `<p class="aviso">Esta canción se separó en 4 pistas (sin ${P.nombre} aparte). Volvé a analizarla desde el link para tener la partitura de ${P.nombre}.</p>`;
  else if (!ns.length) intro = `<p class="aviso">${tipo === 'voz' && E.c.instrumental ? 'Tema instrumental: no hay voz para transcribir.' : `No encontré ${P.nombre} en esta canción.`}</p>`;
  else if (tipo === 'bajo') intro = '<p class="aviso">Bajo de 4 cuerdas (EADG). Las notas por debajo del Mi grave se subieron una octava. Cuantizado a semicorcheas.</p>';
  else if (tipo === 'guitarra') intro = '<p class="aviso">Lo que toca la guitarra en la grabación, transcripto automáticamente de su pista y cuantizado a semicorcheas. Afinación estándar; escrito una octava arriba de como suena, como se lee en guitarra. Las digitaciones de la tablatura son una propuesta: revisalas de oído.</p>';
  else if (tipo === 'piano') intro = '<p class="aviso">Lo que toca el piano o teclado en la grabación, transcripto automáticamente de su pista y cuantizado a semicorcheas. Arriba la mano derecha (desde el Do central), abajo la izquierda. Revisalo de oído.</p>';
  else if (tipo === 'otros') intro = `<p class="aviso">${esc(nombreOtros())}: lo que suena en la pista «otros», transcripto automáticamente y cuantizado a semicorcheas, en sistema de dos pentagramas (arriba desde el Do central). Si hay varios instrumentos (por ejemplo sinte y vientos) aparecen juntos. ${avisoOtros()}</p>`;
  else {
    const orden = ns.filter((n) => n.d >= 2).map((n) => n.ms[0]).sort((a, b) => a - b);
    const lo = orden[Math.floor(orden.length * 0.03)], hi = orden[Math.floor(orden.length * 0.97)];
    intro = `<p class="aviso">Melodía de la voz, cuantizada a semicorcheas${octava ? ' y escrita una octava arriba de como suena (como se lee en guitarra)' : ''}.
      Rango: <b>${T.nombreNota(lo, t.bemol)} – ${T.nombreNota(hi, t.bemol)}</b>. Si queda incómoda para cantar, probá transportar.</p>`;
  }
  el.innerHTML = intro + '<div id="filas"></div>';
  const cont = $('#filas', el);
  const ancho = cont.clientWidth;
  const porFila = ancho < 640 ? 2 : ancho < 900 ? 3 : 4;
  const extra = 78;
  const w = (ancho - extra - 2) / porFila;
  const y2 = P.tab === 6 ? 122 : P.manoIzq ? 124 : 128;

  // pentagramas de la fila: el de arriba y, según el instrumento, mano izquierda o tablatura
  const manos = [{ clave: P.clave, sel: P.manoIzq ? (ms) => ms.filter((m) => m >= 60) : (ms) => ms, silencio: P.clave === 'bass' ? 'd/3' : 'b/4' }];
  if (P.manoIzq) manos.push({ clave: 'bass', sel: (ms) => ms.filter((m) => m < 60), silencio: 'd/3' });

  let metroPrevio = null;
  E.c.secciones.forEach((s) => {
    cont.insertAdjacentHTML('beforeend', tituloSeccion(s));
    for (let ini = s.ini; ini < s.fin; ini += porFila) {
      const fila = document.createElement('div');
      fila.className = 'fila-partitura';
      cont.appendChild(fila);
      const r = new VF.Renderer(fila, VF.Renderer.Backends.SVG);
      r.resize(ancho, P.alto);
      const ctx = r.getContext();
      let x = 1;
      const anteriores = manos.map(() => null);
      const ligas = [];
      for (let i = ini; i < Math.min(ini + porFila, s.fin); i++) {
        const c = E.c.compases[i];
        const primero = i === ini;
        const aw = w + (primero ? extra : 0);
        const conMetro = !c.anacrusa && c.pulsos !== metroPrevio;
        if (conMetro) metroPrevio = c.pulsos;
        const staves = manos.map((mano, k) => {
          const st = new VF.Stave(x, k ? y2 : 34, aw);
          if (primero) st.addClef(mano.clave).addKeySignature(t.vex);
          if (conMetro) st.addTimeSignature(`${c.pulsos}/4`);
          return st;
        });
        let tab = null;
        if (P.tab) {
          tab = new VF.TabStave(x, y2, aw, { num_lines: P.tab });
          if (primero) tab.addClef('tab');
        }
        const todos = staves.concat(tab ? [tab] : []);
        const nx = Math.max(...todos.map((st) => st.getNoteStartX()));
        todos.forEach((st) => { st.setNoteStartX(nx); st.setContext(ctx).draw(); });
        if (primero && todos.length > 1) {
          new VF.StaveConnector(todos[0], todos[1]).setType(P.manoIzq ? 'brace' : 'singleLeft').setContext(ctx).draw();
          if (P.manoIzq) new VF.StaveConnector(todos[0], todos[1]).setType('singleLeft').setContext(ctx).draw();
        }

        const evs = eventosCompas(ns, c);
        const voces = [], dibujos = [];
        manos.forEach((mano, k) => {
          const notas = [];
          // los silencios seguidos de esta mano se juntan (si no, quedan ristras de silencios de semicorchea)
          const propios = [];
          let pos = 0, hueco = 0;
          const cerrar = () => { if (hueco) partir(pos - hueco, hueco).forEach(([d, dur]) => propios.push({ d, dur, ms: null })); hueco = 0; };
          evs.forEach((e) => {
            if (e.entero) { propios.push(e); return; }
            if (!e.ms || !mano.sel(e.ms).length) hueco += e.d; else { cerrar(); propios.push(e); }
            pos += e.d;
          });
          cerrar();
          propios.forEach((e) => {
            const ms = e.ms ? mano.sel(e.ms) : [];
            let n;
            if (!ms.length) {
              n = new VF.StaveNote({ keys: [mano.silencio], duration: e.dur + 'r', clef: mano.clave });
              anteriores[k] = null;
            } else {
              n = new VF.StaveNote({ keys: ms.map(key), duration: e.dur, clef: mano.clave, auto_stem: true });
              const ant = anteriores[k];
              const idx = ms.map((_, j) => j);
              if (ant && ant.n === ms.length) ligas.push(new VF.StaveTie({ first_note: ant.nota, last_note: n, first_indices: idx, last_indices: idx }));
              else if (!ant && e.entra) ligas.push(new VF.StaveTie({ first_note: null, last_note: n, first_indices: idx, last_indices: idx }));
              anteriores[k] = e.liga ? { nota: n, n: ms.length } : null;
            }
            if (e.dur.endsWith('d')) VF.Dot.buildAndAttach([n], { all: true });
            notas.push(n);
          });
          const voz = new VF.Voice({ num_beats: c.pulsos, beat_value: 4 }).setMode(VF.Voice.Mode.SOFT).addTickables(notas);
          VF.Accidental.applyAccidentals([voz], t.vex);
          voces.push(voz);
          dibujos.push({ voz, stave: staves[k], haces: VF.Beam.generateBeams(notas, { beam_rests: false }) });
        });
        if (tab) {
          const tabs = evs.map((e) => {
            if (!e.ms) return new VF.GhostNote({ duration: e.dur });
            const pos = P.tab === 4 ? [posBajo(e.ms[0])] : posGuitarra(e.ms).map((o) => ({ str: o.str, fret: o.fret }));
            return pos.length ? new VF.TabNote({ positions: pos, duration: e.dur }) : new VF.GhostNote({ duration: e.dur });
          });
          const vt = new VF.Voice({ num_beats: c.pulsos, beat_value: 4 }).setMode(VF.Voice.Mode.SOFT).addTickables(tabs);
          voces.push(vt);
          dibujos.push({ voz: vt, stave: tab, haces: [] });
        }
        const fmt = new VF.Formatter();
        voces.forEach((v) => fmt.joinVoices([v]));
        const x0 = staves[0].getNoteStartX(), x1 = staves[0].getNoteEndX();
        fmt.format(voces, Math.max(40, x1 - x0 - 14));
        dibujos.forEach((d) => { d.voz.draw(ctx, d.stave); d.haces.forEach((b) => b.setContext(ctx).draw()); });

        // cifrado, zona clicable y geometría para el cursor
        let pulso = 0, h = `<div class="zona" data-c="${i}" style="left:${x}px;width:${aw}px"></div>`;
        if (primero) h += `<span class="numero" style="left:${x + 2}px">${i + 1}</span>`;
        c.acordes.forEach(([a, n]) => {
          const previo = pulso === 0 && i > 0 ? E.c.compases[i - 1].acordes.slice(-1)[0][0] : null;
          if (a !== 'N.C.' && (a !== previo || primero)) h += `<span class="cifrado" style="left:${x0 + (pulso / c.pulsos) * (x1 - x0)}px">${esc(nom(a))}</span>`;
          pulso += n;
        });
        fila.insertAdjacentHTML('beforeend', h);
        E.geo[i] = { fila, x0, x1 };
        x += aw;
      }
      anteriores.forEach((ant) => {
        if (ant) { const idx = Array.from({ length: ant.n }, (_, j) => j); ligas.push(new VF.StaveTie({ first_note: ant.nota, last_note: null, first_indices: idx, last_indices: idx })); }
      });
      ligas.forEach((l) => { try { l.setContext(ctx).draw(); } catch (e) { /* liga suelta */ } });
    }
  });
  $$('.zona', cont).forEach((z) => { z.onclick = () => ir(E.c.compases[+z.dataset.c].t); });
}

// ----------------------------------------------------------------- improvisación y arreglos
function vistaImpro(el) {
  const c = E.c, t = ton();
  const usados = acordesUsados();
  const escalas = T.sugerirEscalas(t, usados);
  const sel = escalas[Math.min(E.escala, escalas.length - 1)];
  const enTono = T.notasTonalidad(t, usados);
  const fuera = (a) => { const p = T.parse(a); return p && T.notasAcorde(p).some((n) => !enTono.includes(n)); };

  let h = `<h3>Escalas para improvisar en ${t.nombre}</h3>
    <div class="tarjetas">${escalas.map((e, k) => `
      <div class="tarjeta ${k === E.escala ? 'on' : ''}" data-k="${k}"><span class="nivel ${e.nivel}">${e.nivel}</span><b>${e.nombre}</b>
        <div class="notas">${e.notas.map((n) => T.nota(n, t.bemol)).join(' · ')}</div><p>${e.porque}</p></div>`).join('')}</div>
    <div class="dos" style="margin-top:14px"><b>${sel.nombre}</b>
      <div class="selector" id="sel-diap"><button data-i="guitarra">Guitarra</button><button data-i="bajo">Bajo</button><button data-i="piano">Piano</button></div></div>
    ${E.diapason === 'piano' ? `<div style="margin:12px 0">${T.svgTeclado(new Set(sel.notas), sel.raiz, '', 2, 420)}</div>`
      : T.svgDiapason(sel.notas, sel.raiz, t.bemol, E.diapason === 'bajo')}
    <p class="aviso">En naranja la tónica. Mientras suena la canción, muteá la voz o la guitarra desde “Pistas” y tocá encima.</p>

    <h3>Qué tocar en cada sección</h3>
    <table><tr><th>Sección</th><th>Acordes</th><th>Notas guía (3ª y 7ª)</th><th>Sugerencia</th></tr>`;
  const vistas = new Set();
  c.secciones.forEach((s) => {
    const acs = [...new Set(c.compases.slice(s.ini, s.fin).flatMap((x) => x.acordes.map(([a]) => a)).filter((a) => a !== 'N.C.'))].map(nom);
    const firma = s.nombre.replace(/\s*\d+$/, '') + '|' + acs.join(' ');
    if (vistas.has(firma) || !acs.length) return;
    vistas.add(firma);
    const raros = acs.filter(fuera);
    h += `<tr><td class="ac">${esc(s.nombre)}</td>
      <td class="ac">${acs.map((a) => (fuera(a) ? `<span class="fuera">${a}</span>` : a)).join(' – ')}</td>
      <td>${acs.map((a) => `${a}: ${T.notasGuia(a, t)}`).join('<br>')}</td>
      <td>${raros.length ? `Sale de la tonalidad en ${raros.map((a) => `<span class="fuera">${a}</span>`).join(', ')}: ahí cambiá de escala.<br>${raros.map((a) => `<b>${a}</b> → ${T.consejoAcorde(a, t)}`).join('<br>')}`
        : `Todo dentro de ${escalas.find((e) => e.nivel === 'recomendada').nombre}. Apuntá a las notas guía en cada cambio de acorde.`}</td></tr>`;
  });
  h += `</table><h3>Ideas de arreglo</h3><ul>${ideasArreglo(t, usados).map((x) => `<li>${x}</li>`).join('')}</ul>
    <p class="aviso">Sugerencias generadas con reglas de armonía a partir del análisis automático: tomalas como punto de partida.</p>`;
  el.innerHTML = h;
  $$('.tarjeta', el).forEach((d) => { d.onclick = () => { E.escala = +d.dataset.k; pintar(); }; });
  $$('#sel-diap button', el).forEach((b) => {
    b.classList.toggle('on', b.dataset.i === E.diapason);
    b.onclick = () => { E.diapason = b.dataset.i; pintar(); };
  });
}

function ideasArreglo(t, usados) {
  const c = E.c, ideas = [];
  // cejilla
  const cej = T.sugerirCejilla(usados);
  if (cej.traste) {
    const formas = usados.slice(0, 5).map((a) => T.transportar(a.nombre, -cej.traste, false)).join(', ');
    ideas.push(`<b>Guitarra:</b> con cejilla en el traste ${cej.traste} casi todo sale con acordes abiertos (${formas}…), que suenan más llenos que las cejillas.`);
  } else if (cej.sinCejilla > 0.6) ideas.push('<b>Guitarra:</b> la mayoría de los acordes sale en posiciones abiertas, sin cejilla.');
  else ideas.push('<b>Guitarra:</b> hay muchos acordes con cejilla; una segunda guitarra puede tocar tríadas en las tres cuerdas agudas para no duplicar el mismo registro.');
  // rango de voz
  const vz = c.notas.voz.filter((n) => n.d >= 2).map((n) => n.m + E.st).sort((a, b) => a - b);
  if (vz.length > 20) {
    const lo = vz[Math.floor(vz.length * 0.03)], hi = vz[Math.floor(vz.length * 0.97)];
    ideas.push(`<b>Voz:</b> la melodía va de ${T.nombreNota(lo, t.bemol)} a ${T.nombreNota(hi, t.bemol)} (${hi - lo} semitonos). Si a quien canta le queda alta o baja, usá el transporte de abajo: los acordes, la tablatura y el audio se mueven juntos.`);
  }
  // bajo: cuánto se queda en la fundamental
  let enRaiz = 0, total = 0;
  const raizEn = new Map();
  c.compases.forEach((cp) => { let p = cp.beat * 4; cp.acordes.forEach(([a, n]) => { const pa = T.parse(a); for (let k = 0; k < n * 4; k++) raizEn.set(p + k, pa ? pa.raiz : null); p += n * 4; }); });
  c.notas.bajo.forEach((n) => { const r = raizEn.get(n.i); if (r === null || r === undefined) return; total += n.d; if (T.mod(n.m) === r) enRaiz += n.d; });
  if (total > 40) {
    const f = enRaiz / total;
    ideas.push(f > 0.7
      ? `<b>Bajo:</b> en la grabación toca la fundamental el ${Math.round(f * 100)}% del tiempo. Para darle movimiento: quinta u octava en el tiempo 3 y una nota de aproximación (medio tono abajo o arriba) antes de cada cambio de acorde.`
      : `<b>Bajo:</b> la línea se mueve bastante (solo ${Math.round(f * 100)}% en la fundamental): conviene aprenderla de la tablatura. Si la simplifican, que la fundamental caiga siempre en el 1.`);
  }
  // quién toca en cada parte
  const nombresPista = { vocals: 'voz', guitar: 'guitarra', piano: 'piano', bass: 'bajo', drums: 'batería', otros: 'otros', other: 'guitarras/teclados' };
  const instr = c.pistas.filter((p) => p.id !== 'vocals' && p.nivel >= 0.04);
  const partes = [];
  const yaVista = new Set();
  c.secciones.forEach((s) => {
    const base = s.nombre.replace(/\s*\d+$/, '');
    if (yaVista.has(base)) return;
    yaVista.add(base);
    const callan = instr.filter((p) => p.activa.slice(s.ini, s.fin).reduce((a, b) => a + b, 0) / Math.max(1, s.fin - s.ini) < 0.3);
    if (callan.length && callan.length < instr.length) partes.push(`${s.nombre} sin ${callan.map((p) => nombresPista[p.id]).join(' ni ')}`);
  });
  if (partes.length) ideas.push(`<b>Dinámica:</b> en la grabación ${partes.join('; ')}. Respetar esos silencios hace que las otras partes crezcan.`);
  else ideas.push('<b>Dinámica:</b> en la grabación todos tocan casi todo el tiempo. Para que el coro levante, prueben bajar el verso: guitarra en arpegios o apagada, batería en el aro o el hi-hat cerrado.');
  const pp = pista('piano');
  if (pp && pp.nivel >= 0.04) ideas.push('<b>Sin tecladista:</b> la guitarra puede cubrir el piano tocando los acordes en arpegio en las partes donde el piano lleva la armonía (mutealo y escuchá qué falta).');
  // color armónico
  const p0 = usados[0] && T.parse(usados[0].nombre);
  if (p0 && (p0.calidad === '' || p0.calidad === 'm')) {
    const rel = p0.calidad === '' ? T.nota(p0.raiz + 9, t.bemol) + 'm' : T.nota(p0.raiz + 3, t.bemol);
    const esc7 = T.notasTonalidad(t, usados);     // la séptima que cae dentro de la escala de la tonalidad
    const con7 = usados.slice(0, 3).map((a) => {
      const p = T.parse(a.nombre);
      if (p.calidad === 'm') return a.nombre + '7';
      if (p.calidad !== '') return a.nombre;
      return a.nombre + (esc7.includes(T.mod(p.raiz + 11)) ? 'maj7' : '7');
    }).join(', ');
    ideas.push(`<b>Color:</b> probá agregar séptimas (${con7}) en teclado o segunda guitarra, y en una repetición reemplazar ${usados[0].nombre} por su relativo ${rel} para variar sin cambiar la melodía.`);
  }
  ideas.push(`<b>Final:</b> si el tema termina en fade-out, acuerden un cierre: repetir la última frase del coro y cortar todos juntos en ${t.nombre}.`);
  return ideas;
}

// ================================================================= cursor y reproducción
function compasEn(t) {
  const cs = E.c.compases;
  let a = 0, b = cs.length - 1;
  while (a < b) { const m = (a + b + 1) >> 1; if (cs[m].t <= t) a = m; else b = m - 1; }
  return a;
}
function acordeEn(i, t) {
  const c = E.c.compases[i];
  let pulso = 0;
  while (pulso + 1 < c.pulsos && E.c.beats[c.beat + pulso + 1] <= t) pulso++;
  let acum = 0;
  for (const [a, n] of c.acordes) { acum += n; if (pulso < acum) return a; }
  return c.acordes[c.acordes.length - 1][0];
}
const cursor = document.createElement('div');
cursor.className = 'cursor';

// La hoja sigue al cursor, pero SOLO dentro de #vista (nunca mueve la página ni el panel de pistas)
// y no pelea con el usuario: si acaba de scrollear a mano, espera unos segundos.
let scrollManual = 0;
['wheel', 'touchmove', 'mousedown', 'keydown'].forEach((ev) => $('#vista').addEventListener(ev, () => { scrollManual = performance.now(); }, { passive: true }));
function seguirCursor(el, ya) {
  if (!ya && performance.now() - scrollManual < 4000) return;
  const v = $('#vista');
  const r = el.getBoundingClientRect(), rv = v.getBoundingClientRect();
  if (r.top < rv.top + 30 || r.bottom > rv.bottom - 50) v.scrollTo({ top: v.scrollTop + r.top - rv.top - rv.height * 0.3, behavior: 'smooth' });
}

// ================================================================= metrónomo y cuenta previa
const M = { nodos: new Set(), esperas: [], sig: 0, reloj: null };
function clic(cuando, fuerte, cuenta) {
  const ctx = A.ctx, o = ctx.createOscillator(), g = ctx.createGain();
  o.type = 'square';
  o.frequency.value = fuerte ? 1760 : 1175;
  g.gain.setValueAtTime(0.0001, cuando);
  g.gain.exponentialRampToValueAtTime(fuerte ? 0.32 : 0.2, cuando + 0.002);
  g.gain.exponentialRampToValueAtTime(0.0001, cuando + 0.05);
  // la cuenta previa suena aunque el metrónomo esté apagado, con su mismo volumen
  if (cuenta) { const v = ctx.createGain(); v.gain.value = Math.max(E.vol.metro, 0.3); o.connect(g).connect(v).connect(ctx.destination); }
  else o.connect(g).connect(gananciaMetro());
  o.start(cuando); o.stop(cuando + 0.07);
  M.nodos.add(o);
  o.onended = () => M.nodos.delete(o);
}
const primerPulsoDesde = (t) => { const bs = E.c.beats; let j = 0; while (j < bs.length - 1 && bs[j] < t - 0.001) j++; return j; };
function periodoEn(t) {
  const bs = E.c.beats, j = Math.min(primerPulsoDesde(t), bs.length - 2), k = Math.min(bs.length - 1, j + 4);
  return k > j ? (bs[k] - bs[j]) / (k - j) : 60 / E.c.tempo;
}
// Cuenta de un compás antes de arrancar, alineada con la grilla de pulsos. Devuelve cuánto dura.
function cuentaPrevia(desde) {
  const n = E.c.compas, p = periodoEn(A.pos);
  const j = primerPulsoDesde(A.pos);
  const desfase = j < E.c.beats.length - 1 ? (E.c.beats[j] - A.pos) % p : 0;
  for (let k = 0; k < n; k++) {
    const cuando = desde + desfase + k * p;
    clic(cuando, k === 0, true);
    M.esperas.push(setTimeout(() => { $('#acorde-actual').textContent = k + 1; $('#seccion-actual').textContent = 'cuenta'; }, (cuando - A.ctx.currentTime) * 1000));
  }
  M.esperas.push(setTimeout(() => refrescar(true), n * p * 1000 + 40));
  return n * p;
}
function programarMetro() {
  if (!A.tocando) return;      // se programa siempre: prenderlo o apagarlo en el mezclador es instantáneo
  const bs = E.c.beats, hasta = tiempo() + 0.25;
  while (M.sig < bs.length - 1 && bs[M.sig] < hasta) {
    if (bs[M.sig] >= A.pos - 0.001) clic(A.t0 + (bs[M.sig] - A.pos), E.unos.has(M.sig));
    M.sig++;
  }
}
function pararMetro() {
  clearInterval(M.reloj);
  M.esperas.forEach(clearTimeout); M.esperas = [];
  M.nodos.forEach((o) => { try { o.onended = null; o.stop(); o.disconnect(); } catch (e) { /* ya sonó */ } });
  M.nodos.clear();
}

function refrescar(forzar) {
  if (!E.c) return;
  const t = tiempo();
  if (E.pararEn != null && A.tocando && t >= E.pararEn) { const v = E.volverA; pausar(); ir(v); return; }   // «Escuchar» un compás
  $('#t-actual').textContent = mmss(t);
  if (!arrastrando) $('#barra').value = Math.round((t / E.c.duracion) * 1000);
  const i = compasEn(t);
  const c = E.c.compases[i];
  const s = seccionDe(i);
  if (vigilarBucle()) return;
  if (A.tocando && t >= E.c.duracion - 0.05) { pausar(); A.pos = 0; }
  const a = nom(acordeEn(i, t));
  if (a !== E.acordeActual || forzar) {
    E.acordeActual = a;
    $('#acorde-actual').textContent = a;
    $$('.diagramas .cont').forEach((d) => d.classList.toggle('actual', d.dataset.acorde === a));
  }
  $('#seccion-actual').textContent = s ? s.nombre : ' ';
  const g = E.geo[i];
  if (i !== E.compasActual || forzar) {
    $$('.actual[data-c]').forEach((d) => d.classList.remove('actual'));
    $$(`[data-c="${i}"]`).forEach((d) => d.classList.add('actual'));
    if (g && (g.celda || g.fila !== (E.geo[E.compasActual] || {}).fila || forzar)) {
      (g.celda || g.fila).appendChild(cursor);
      if (A.tocando) seguirCursor(g.celda || g.fila);
    }
    E.compasActual = i;
  }
  if (g) {
    const frac = Math.max(0, Math.min(1, (t - c.t) / Math.max(0.05, finCompas(i) - c.t)));
    const x0 = g.celda ? 0 : g.x0, x1 = g.celda ? g.celda.offsetWidth : g.x1;
    cursor.style.left = `${x0 + frac * (x1 - x0)}px`;
  } else cursor.remove();
}
(function bucle() { if (A.tocando) refrescar(false); requestAnimationFrame(bucle); })();

// ================================================================= controles
let arrastrando = false;
$('#btn-play').onclick = () => { E.pararEn = null; if (A.tocando) pausar(); else tocar(); };
$('#barra').oninput = () => { arrastrando = true; $('#t-actual').textContent = mmss(($('#barra').value / 1000) * E.c.duracion); };
$('#barra').onchange = () => {
  arrastrando = false;
  const t = ($('#barra').value / 1000) * E.c.duracion, b = repitiendo();
  saltoManual = !!(b && t >= finCompas(b.fin));      // saltó más allá del tramo a repetir: se lo deja seguir
  ir(t);
};
['cuenta'].forEach((id) => {
  const el = $('#' + id);
  el.checked = recordar(id) === '1';
  el.onchange = () => { recordar(id, el.checked ? '1' : '0'); };
});
// ----------------------------------------------------------------- repetir desde / hasta
const repitiendo = () => ($('#repetir').checked && E.bucle ? E.bucle : null);
// al llegar al final del compás «hasta» vuelve al «desde». Corre con su propio reloj (no solo con el
// refresco de pantalla, que el navegador frena si la pestaña no está a la vista). Si uno salta a mano
// más allá del tramo, no lo trae de vuelta.
let saltoManual = false;
function vigilarBucle() {
  const b = repitiendo();
  if (!b || !A.tocando || !E.c) return false;
  const t = tiempo(), fin = Math.min(finCompas(b.fin), E.c.duracion - 0.05);
  if (t < fin - 0.01) { saltoManual = false; return false; }
  if (saltoManual) return false;
  ir(E.c.compases[b.ini].t);
  return true;
}
setInterval(vigilarBucle, 30);
function llenarBucle() {                // un <option> por compás, agrupados por sección
  const op = E.c.secciones.map((s) => `<optgroup label="${esc(s.nombre)}">${
    Array.from({ length: s.fin - s.ini }, (_, j) => s.ini + j).map((i) => `<option value="${i}">${esc(s.nombre)} · c. ${i + 1}</option>`).join('')}</optgroup>`).join('');
  $('#bucle-ini').innerHTML = op; $('#bucle-fin').innerHTML = op;
  const n = E.c.compases.length;
  if (!E.bucle || E.bucle.fin >= n) { const s = seccionDe(compasEn(A.pos)) || { ini: 0, fin: n }; E.bucle = { ini: s.ini, fin: s.fin - 1 }; }
  $('#bucle-ini').value = E.bucle.ini; $('#bucle-fin').value = E.bucle.fin;
  marcarBucle();
}
function marcarBucle() {
  const b = repitiendo();
  $('.bucle').classList.toggle('on', !!b);
  $$('.en-bucle[data-c]').forEach((d) => d.classList.remove('en-bucle'));
  if (b) $$('[data-c]').forEach((d) => { const i = +d.dataset.c; if (i >= b.ini && i <= b.fin) d.classList.add('en-bucle'); });
}
function cambiarBucle(cual) {
  let ini = +$('#bucle-ini').value, fin = +$('#bucle-fin').value;
  if (fin < ini) { if (cual === 'ini') fin = ini; else ini = fin; }   // «hasta» nunca antes que «desde»
  E.bucle = { ini, fin };
  $('#bucle-ini').value = ini; $('#bucle-fin').value = fin;
  if (!$('#repetir').checked) { $('#repetir').checked = true; }       // elegir un tramo ya lo activa
  marcarBucle();
  const t = tiempo();
  if (t < E.c.compases[ini].t - 0.01 || t >= finCompas(fin)) ir(E.c.compases[ini].t);
}
$('#bucle-ini').onchange = () => cambiarBucle('ini');
$('#bucle-fin').onchange = () => cambiarBucle('fin');
$('#repetir').onchange = () => {
  if ($('#repetir').checked) {          // al prender, por defecto la sección que está sonando
    const s = seccionDe(compasEn(tiempo()));
    if (s) { E.bucle = { ini: s.ini, fin: s.fin - 1 }; $('#bucle-ini').value = s.ini; $('#bucle-fin').value = s.fin - 1; }
  }
  marcarBucle();
};

// ----------------------------------------------------------------- volver al principio
$('#btn-inicio').onclick = () => { E.pararEn = null; ir(0); $('#vista').scrollTo({ top: 0 }); };

// ----------------------------------------------------------------- panel lateral: visible u oculto
function ponerPanel(visible) {
  document.body.classList.toggle('panel-oculto', !visible);
  $('#btn-panel').classList.toggle('on', visible);
  recordar('panel', visible ? 'fijo' : 'oculto');
  if (E.c && E.modo === 'partitura') pintar();          // la partitura se re-acomoda al ancho nuevo
}
const panelVisible = () => !document.body.classList.contains('panel-oculto');
$('#btn-panel').onclick = () => ponerPanel(!panelVisible());
// por defecto: visible en pantallas anchas, oculto en tablets y celulares
ponerPanel(recordar('panel') ? recordar('panel') === 'fijo' : window.innerWidth >= 1100);

// ----------------------------------------------------------------- silbato de tren (al tocar Analizar)
// en el clic (y no en el envío) para que suene siempre que se toca la locomotora; Enter en el campo también
// dispara un clic en el botón
$('.locomotora').addEventListener('click', () => silbato());
// Silbato de tren de madera sintetizado, afinado con la grabación de referencia de Maxi («Wooden Train
// Whistle»): cuatro tubos casi pegados, Fa5–Sol5–La5–Si5 (683, 773, 874, 980 Hz), sonido de flauta (pocos
// armónicos: onda triangular), arranca un poco abajo y sube, más el soplido (ruido alrededor de 1,5 kHz).
// Dos pitadas: una corta y una larga.
function silbato() {
  try {
    const ctx = ctxAudio();
    ctx.resume();
    const sal = ctx.createGain(); sal.gain.value = 0.3; sal.connect(ctx.destination);
    const filtro = ctx.createBiquadFilter(); filtro.type = 'lowpass'; filtro.frequency.value = 3500; filtro.connect(sal);
    const ruido = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    ruido.getChannelData(0).forEach((_, i, d) => { d[i] = Math.random() * 2 - 1; });
    const pitada = (t0, dur) => {
      const env = ctx.createGain(); env.connect(filtro);
      env.gain.setValueAtTime(0.0001, t0);
      env.gain.exponentialRampToValueAtTime(1, t0 + 0.08);
      env.gain.setValueAtTime(1, t0 + dur - 0.12);
      env.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      const vib = ctx.createOscillator(), vibG = ctx.createGain();
      vib.frequency.value = 5; vibG.gain.value = 5; vib.connect(vibG); vib.start(t0); vib.stop(t0 + dur);
      [683, 773, 874, 980].forEach((f, k) => {          // Fa5, Sol5, La5, Si5 (como la referencia)
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = 'triangle';
        o.frequency.setValueAtTime(f * 0.9, t0);           // arranca un poco abajo y sube, como el soplido
        o.frequency.exponentialRampToValueAtTime(f, t0 + 0.15);
        vibG.connect(o.frequency);
        g.gain.value = [0.2, 0.22, 0.18, 0.13][k];
        o.connect(g).connect(env); o.start(t0); o.stop(t0 + dur);
      });
      const n = ctx.createBufferSource(), bp = ctx.createBiquadFilter(), ng = ctx.createGain();
      n.buffer = ruido; bp.type = 'bandpass'; bp.frequency.value = 1550; bp.Q.value = 0.9; ng.gain.value = 0.22;
      n.connect(bp).connect(ng).connect(env); n.start(t0); n.stop(t0 + dur);
    };
    const t = ctx.currentTime + 0.03;
    pitada(t, 0.38);
    pitada(t + 0.5, 1.15);
  } catch (e) { /* sin audio: no pasa nada */ }
}

// ----------------------------------------------------------------- engranajes del logo
$$('[data-engranaje]').forEach((p) => {
  const [cx, cy, re, ri, n] = p.dataset.engranaje.split(',').map(Number);
  const pts = [];
  for (let k = 0; k < n; k++) {         // cada diente: sube, meseta, baja, valle
    const a = (k / n) * 2 * Math.PI, d = (2 * Math.PI) / n;
    [[ri, 0], [re, 0.18], [re, 0.42], [ri, 0.6]].forEach(([r, f]) => pts.push([cx + r * Math.cos(a + f * d), cy + r * Math.sin(a + f * d)]));
  }
  p.setAttribute('d', 'M' + pts.map(([x, y]) => `${x.toFixed(2)} ${y.toFixed(2)}`).join('L') + 'Z');
});
document.addEventListener('keydown', (ev) => {
  if (ev.code === 'Space' && E.c && !/INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) { ev.preventDefault(); $('#btn-play').click(); }
  if (ev.code === 'Home' && E.c && !/INPUT|TEXTAREA|SELECT/.test(ev.target.tagName)) { ev.preventDefault(); $('#btn-inicio').click(); }
});
$$('#pestanas [data-vista]').forEach((b) => {
  b.onclick = () => {
    E.vista = b.dataset.vista; E.edicion = false;
    E.diapason = { guitarra: 'guitarra', piano: 'piano', bajo: 'bajo' }[E.vista] || E.diapason;   // escalas en su instrumento
    $('#vista').scrollTop = 0; pintar();
  };
});
// se edita la hoja de acordes de la pestaña abierta: la armonía del tema o lo que toca ese instrumento
$('#btn-editar').onclick = () => { E.edicion = !E.edicion; E.sel = -1; pintar(); };
function transportar(d) {
  const st = Math.max(-6, Math.min(6, E.st + d));
  if (st === E.st) return;
  E.st = st;
  pintar();
  cargarAudio();
}
$('#st-menos').onclick = () => transportar(-1);
$('#st-mas').onclick = () => transportar(1);
$('#btn-imprimir').onclick = () => window.print();

const dlg = $('#dlg-estructura');
$('#btn-estructura').onclick = async () => {
  $('#txt-estructura').value = (await api(`canciones/${encodeURIComponent(E.id)}/estructura`)).texto;
  dlg.showModal();
};
$('#est-cancelar').onclick = () => dlg.close();
$('#est-guardar').onclick = async () => {
  const t = await api(`canciones/${encodeURIComponent(E.id)}/estructura`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ texto: $('#txt-estructura').value }) });
  dlg.close();
  seguir(t);
};

let redibujo = null;
window.addEventListener('resize', () => { clearTimeout(redibujo); redibujo = setTimeout(() => { if (E.c && E.modo === 'partitura') pintar(); }, 250); });

cargarLista();
sondear();
