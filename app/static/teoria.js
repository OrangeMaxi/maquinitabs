// Teoría musical: acordes, transporte, digitaciones, escalas y sugerencias.
const T = (() => {
  const SOST = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  const BEMOL = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
  // cómo se escribe cada tonalidad (evita D#, A#, Gb mayor, etc.)
  const TON_MAYOR = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
  const TON_MENOR = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B'];
  const INTERVALOS = { '': [0, 4, 7], m: [0, 3, 7], 7: [0, 4, 7, 10], maj7: [0, 4, 7, 11], m7: [0, 3, 7, 10], sus4: [0, 5, 7], dim: [0, 3, 6],
    aug: [0, 4, 8], 6: [0, 4, 7, 9], m6: [0, 3, 7, 9], mMaj7: [0, 3, 7, 11], dim7: [0, 3, 6, 9], m7b5: [0, 3, 6, 10], sus2: [0, 2, 7] };

  const pc = (nombre) => { const i = SOST.indexOf(nombre); return i >= 0 ? i : BEMOL.indexOf(nombre); };
  const mod = (n) => ((n % 12) + 12) % 12;

  function tonalidad(ton, st) {            // ton = {tonica, modo} del análisis
    const raiz = mod(pc(ton.tonica) + st);
    const menor = ton.modo === 'menor';
    const nombre = (menor ? TON_MENOR : TON_MAYOR)[raiz];
    const bemol = nombre.includes('b') || (!menor && raiz === 5) || (menor && [2, 7, 0, 5].includes(raiz));
    return { raiz, menor, bemol, nombre: nombre + (menor ? 'm' : ''), vex: nombre + (menor ? 'm' : '') };
  }
  const nota = (n, bemol) => (bemol ? BEMOL : SOST)[mod(n)];

  function parse(acorde) {
    const m = /^([A-G][#b]?)([^/]*)(?:\/([A-G][#b]?))?$/.exec(acorde || '');
    if (!m) return null;
    return { raiz: pc(m[1]), calidad: m[2], bajo: m[3] ? pc(m[3]) : null };
  }
  function transportar(acorde, st, bemol) {
    const a = parse(acorde);
    if (!a) return acorde;
    return nota(a.raiz + st, bemol) + a.calidad + (a.bajo !== null ? '/' + nota(a.bajo + st, bemol) : '');
  }
  const notasAcorde = (a) => (INTERVALOS[a.calidad] || INTERVALOS['']).map((i) => mod(a.raiz + i));

  // ---------------------------------------------------------------- guitarra
  // cuerdas 6→1; -1 = no se toca
  const ABIERTOS = {
    'C': [-1, 3, 2, 0, 1, 0], 'D': [-1, -1, 0, 2, 3, 2], 'E': [0, 2, 2, 1, 0, 0], 'G': [3, 2, 0, 0, 0, 3], 'A': [-1, 0, 2, 2, 2, 0],
    'Am': [-1, 0, 2, 2, 1, 0], 'Em': [0, 2, 2, 0, 0, 0], 'Dm': [-1, -1, 0, 2, 3, 1],
    'C7': [-1, 3, 2, 3, 1, 0], 'D7': [-1, -1, 0, 2, 1, 2], 'E7': [0, 2, 0, 1, 0, 0], 'G7': [3, 2, 0, 0, 0, 1], 'A7': [-1, 0, 2, 0, 2, 0], 'B7': [-1, 2, 1, 2, 0, 2],
    'Cmaj7': [-1, 3, 2, 0, 0, 0], 'Dmaj7': [-1, -1, 0, 2, 2, 2], 'Emaj7': [0, 2, 1, 1, 0, 0], 'Fmaj7': [-1, -1, 3, 2, 1, 0], 'Gmaj7': [3, 2, 0, 0, 0, 2], 'Amaj7': [-1, 0, 2, 1, 2, 0],
    'Am7': [-1, 0, 2, 0, 1, 0], 'Em7': [0, 2, 0, 0, 0, 0], 'Dm7': [-1, -1, 0, 2, 1, 1],
    'Asus4': [-1, 0, 2, 2, 3, 0], 'Dsus4': [-1, -1, 0, 2, 3, 3], 'Esus4': [0, 2, 2, 2, 0, 0],
    'Asus2': [-1, 0, 2, 2, 0, 0], 'Dsus2': [-1, -1, 0, 2, 3, 0], 'A6': [-1, 0, 2, 2, 2, 2], 'E6': [0, 2, 2, 1, 2, 0], 'D6': [-1, -1, 0, 2, 0, 2], 'G6': [3, 2, 0, 0, 0, 0], 'C6': [-1, 3, 2, 2, 1, 0],
    'Am6': [-1, 0, 2, 2, 1, 2], 'Em6': [0, 2, 2, 0, 2, 0], 'Dm6': [-1, -1, 0, 2, 0, 1], 'Bm7b5': [-1, 2, 3, 2, 3, -1], 'Edim7': [0, 1, 2, 0, 2, 0], 'Adim7': [-1, 0, 1, 2, 1, 2], 'Ddim7': [-1, -1, 0, 1, 0, 1],
  };
  const FORMA_E = { '': [0, 2, 2, 1, 0, 0], m: [0, 2, 2, 0, 0, 0], 7: [0, 2, 0, 1, 0, 0], maj7: [0, -1, 1, 1, 0, -1], m7: [0, 2, 0, 0, 0, 0], sus4: [0, 2, 2, 2, 0, 0],
    dim: [0, 1, 2, 0, -1, -1], 6: [0, 2, 2, 1, 2, 0], m6: [0, 2, 2, 0, 2, 0], aug: [0, 3, 2, 1, 1, 0], sus2: [0, 2, 4, 4, 0, 0], mMaj7: [0, 2, 1, 0, 0, 0], dim7: [0, 1, 2, 0, 2, 0], m7b5: [0, 1, 0, 0, 3, 0] };
  const FORMA_A = { '': [-1, 0, 2, 2, 2, 0], m: [-1, 0, 2, 2, 1, 0], 7: [-1, 0, 2, 0, 2, 0], maj7: [-1, 0, 2, 1, 2, 0], m7: [-1, 0, 2, 0, 1, 0], sus4: [-1, 0, 2, 2, 3, 0], dim: [-1, 0, 1, 2, 1, -1],
    6: [-1, 0, 2, 2, 2, 2], m6: [-1, 0, 2, 2, 1, 2], aug: [-1, 0, 3, 2, 2, 1], sus2: [-1, 0, 2, 2, 0, 0], mMaj7: [-1, 0, 2, 1, 1, 0], dim7: [-1, 0, 1, 2, 1, 2], m7b5: [-1, 0, 1, 0, 1, -1] };

  function digitacion(acorde) {
    const a = parse(acorde);
    if (!a) return null;
    const clave = SOST[a.raiz] + a.calidad;
    if (ABIERTOS[clave]) return { trastes: ABIERTOS[clave], cejilla: 0, abierto: true };
    const q = a.calidad in FORMA_A ? a.calidad : '';
    const fe = mod(a.raiz - 4), fa = mod(a.raiz - 9);
    const usarE = FORMA_E[q] && (fe || 12) <= (fa || 12);
    const base = usarE ? fe || 12 : fa || 12;
    const forma = usarE ? FORMA_E[q] : FORMA_A[q];
    return { trastes: forma.map((x) => (x < 0 ? -1 : x + base)), cejilla: base, abierto: false };
  }

  function svgGuitarra(acorde, nombre) {
    const d = digitacion(acorde);
    if (!d) return '';
    const puestos = d.trastes.filter((x) => x > 0);
    const max = Math.max(...puestos, 1), min = Math.min(...puestos);
    const ini = max <= 4 ? 1 : min;
    const W = 86, H = 112, x0 = 16, y0 = 30, dx = 11, dy = 17;
    let s = `<svg class="diagrama" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"><text x="${W / 2}" y="13" text-anchor="middle" class="dg-nombre">${nombre}</text>`;
    for (let i = 0; i < 6; i++) s += `<line x1="${x0 + i * dx}" y1="${y0}" x2="${x0 + i * dx}" y2="${y0 + 4 * dy}" class="dg-linea"/>`;
    for (let f = 0; f <= 4; f++) s += `<line x1="${x0}" y1="${y0 + f * dy}" x2="${x0 + 5 * dx}" y2="${y0 + f * dy}" class="${f === 0 && ini === 1 ? 'dg-cejuela' : 'dg-linea'}"/>`;
    if (ini > 1) s += `<text x="${x0 + 5 * dx + 5}" y="${y0 + dy * 0.75}" class="dg-traste">${ini}</text>`;
    if (d.cejilla) {
      const cs = d.trastes.map((x, i) => (x === d.cejilla ? i : -1)).filter((i) => i >= 0);
      const y = y0 + (d.cejilla - ini + 0.5) * dy;
      s += `<line x1="${x0 + cs[0] * dx}" y1="${y}" x2="${x0 + 5 * dx}" y2="${y}" class="dg-barra"/>`;
    }
    d.trastes.forEach((t, i) => {
      const x = x0 + i * dx;
      if (t < 0) s += `<text x="${x}" y="${y0 - 5}" text-anchor="middle" class="dg-x">×</text>`;
      else if (t === 0) s += `<circle cx="${x}" cy="${y0 - 8}" r="3" class="dg-aire"/>`;
      else s += `<circle cx="${x}" cy="${y0 + (t - ini + 0.5) * dy}" r="4.3" class="dg-dedo"/>`;
    });
    return s + '</svg>';
  }

  // ---------------------------------------------------------------- teclado
  function svgTeclado(notas, raiz, nombre, octavas = 2, ancho = 150) {
    const blancas = [0, 2, 4, 5, 7, 9, 11], negras = { 1: 0, 3: 1, 6: 3, 8: 4, 10: 5 };
    const nb = octavas * 7, w = ancho / nb, h = 54, top = nombre ? 18 : 2;
    // voicing en posición fundamental: cada nota arriba de la anterior
    const marcadas = new Set();
    if (Array.isArray(notas)) { let ant = -1; notas.forEach((n) => { let k = n; while (k <= ant) k += 12; if (k >= octavas * 12) k -= 12; marcadas.add(k); ant = k; }); }
    const en = (k) => (Array.isArray(notas) ? marcadas.has(k) : notas.has(k % 12));
    const clase = (k) => (en(k) ? (k % 12 === raiz ? ' tc-raiz' : ' tc-on') : '');
    let s = `<svg class="teclado" viewBox="0 0 ${ancho + 2} ${h + top + 2}" width="${ancho + 2}" height="${h + top + 2}">`;
    if (nombre) s += `<text x="${ancho / 2}" y="13" text-anchor="middle" class="dg-nombre">${nombre}</text>`;
    for (let o = 0; o < octavas; o++) blancas.forEach((p, i) => { s += `<rect x="${1 + (o * 7 + i) * w}" y="${top}" width="${w}" height="${h}" class="tc-blanca${clase(o * 12 + p)}"/>`; });
    for (let o = 0; o < octavas; o++) Object.entries(negras).forEach(([p, i]) => { s += `<rect x="${1 + (o * 7 + i + 0.68) * w}" y="${top}" width="${w * 0.64}" height="${h * 0.62}" class="tc-negra${clase(o * 12 + +p)}"/>`; });
    return s + '</svg>';
  }

  // ---------------------------------------------------------------- diapasón
  function svgDiapason(notasEscala, raiz, bemol, bajo) {
    const cuerdas = bajo ? [43, 38, 33, 28] : [64, 59, 55, 50, 45, 40];
    const nt = 15, dx = 44, dy = 22, x0 = 34, y0 = 16;
    const W = x0 + nt * dx + 12, H = y0 + (cuerdas.length - 1) * dy + 34;
    let s = `<svg class="diapason" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMinYMin meet">`;
    for (let f = 0; f <= nt; f++) s += `<line x1="${x0 + f * dx}" y1="${y0}" x2="${x0 + f * dx}" y2="${y0 + (cuerdas.length - 1) * dy}" class="${f === 0 ? 'dg-cejuela' : 'dp-traste'}"/>`;
    [3, 5, 7, 9, 12, 15].forEach((f) => { s += `<text x="${x0 + (f - 0.5) * dx}" y="${H - 6}" text-anchor="middle" class="dp-num">${f}</text>`; });
    cuerdas.forEach((c, i) => {
      const y = y0 + i * dy;
      s += `<line x1="${x0}" y1="${y}" x2="${x0 + nt * dx}" y2="${y}" class="dp-cuerda"/>`;
      for (let f = 0; f <= nt; f++) {
        const n = mod(c + f);
        if (!notasEscala.includes(n)) continue;
        const x = f === 0 ? x0 - 16 : x0 + (f - 0.5) * dx;
        s += `<circle cx="${x}" cy="${y}" r="9.5" class="${n === raiz ? 'dp-raiz' : 'dp-nota'}"/><text x="${x}" y="${y + 3.5}" text-anchor="middle" class="dp-txt${n === raiz ? ' dp-txt-raiz' : ''}">${nota(n, bemol)}</text>`;
      }
    });
    return s + '</svg>';
  }

  // ---------------------------------------------------------------- escalas
  const ESCALAS = {
    pentMenor: { nombre: 'Pentatónica menor', ints: [0, 3, 5, 7, 10] },
    blues: { nombre: 'Escala de blues', ints: [0, 3, 5, 6, 7, 10] },
    menor: { nombre: 'Menor natural (eólica)', ints: [0, 2, 3, 5, 7, 8, 10] },
    dorica: { nombre: 'Dórica', ints: [0, 2, 3, 5, 7, 9, 10] },
    armonica: { nombre: 'Menor armónica', ints: [0, 2, 3, 5, 7, 8, 11] },
    pentMayor: { nombre: 'Pentatónica mayor', ints: [0, 2, 4, 7, 9] },
    mayor: { nombre: 'Mayor (jónica)', ints: [0, 2, 4, 5, 7, 9, 11] },
    mixolidia: { nombre: 'Mixolidia', ints: [0, 2, 4, 5, 7, 9, 10] },
    lidia: { nombre: 'Lidia', ints: [0, 2, 4, 6, 7, 9, 11] },
  };
  const escala = (raiz, id) => ESCALAS[id].ints.map((i) => mod(raiz + i));

  // acordes = [{nombre, pulsos}] ya transportados; ton = tonalidad(…)
  function sugerirEscalas(ton, acordes) {
    const r = ton.raiz, out = [];
    const hay = (grado, calidades) => acordes.some((a) => { const p = parse(a.nombre); return p && mod(p.raiz - r) === grado && calidades.includes(p.calidad); });
    const agregar = (id, raiz, porque, nivel) => out.push({ id, raiz, nombre: `${nota(raiz, ton.bemol)} ${ESCALAS[id].nombre.toLowerCase()}`, notas: escala(raiz, id), porque, nivel });
    if (ton.menor) {
      agregar('pentMenor', r, 'La apuesta segura: cinco notas que suenan bien sobre casi toda la canción.', 'segura');
      const dor = hay(5, ['', '7', 'maj7']) || hay(2, ['m', 'm7']);
      if (dor) agregar('dorica', r, `Aparece el IV mayor (${nota(r + 5, ton.bemol)}): la 6ª mayor (${nota(r + 9, ton.bemol)}) es la nota característica. Evitá la 6ª menor de la escala natural.`, 'recomendada');
      else agregar('menor', r, 'La escala de la tonalidad: agrega la 2ª y la 6ª menor a la pentatónica para frases más melódicas.', 'recomendada');
      agregar('blues', r, `Pentatónica + la “blue note” (${nota(r + 6, ton.bemol)}) como nota de paso, para un color más rockero.`, 'color');
      if (hay(7, ['', '7'])) agregar('armonica', r, `Sobre el V mayor (${nota(r + 7, ton.bemol)}) usá la sensible (${nota(r + 11, ton.bemol)}): solo en ese acorde.`, 'color');
      if (dor) agregar('menor', r, 'Sirve en los acordes que no sean el IV mayor.', 'alternativa');
    } else {
      agregar('pentMayor', r, 'La apuesta segura: cinco notas sin tensiones sobre toda la progresión.', 'segura');
      const mix = hay(10, ['', 'maj7']) || hay(0, ['7']);
      if (mix) agregar('mixolidia', r, `Aparece el bVII (${nota(r + 10, ton.bemol)}) o el I7: la 7ª menor es la nota característica.`, 'recomendada');
      else agregar('mayor', r, 'La escala de la tonalidad. Cuidado con la 4ª sobre el acorde de tónica: usala de paso.', 'recomendada');
      agregar('pentMenor', mod(r + 9), 'La pentatónica menor del relativo: mismas notas que la pentatónica mayor, en las posiciones de siempre.', 'alternativa');
      if (acordes.some((a) => (parse(a.nombre) || {}).calidad === '7')) agregar('blues', r, 'Con acordes de séptima dominante la escala de blues de la tónica da un color más sucio.', 'color');
      if (mix) agregar('mayor', r, 'Sirve en los acordes que no sean el bVII.', 'alternativa');
    }
    return out;
  }

  // escala de la tonalidad para saber qué acordes "se salen"
  function notasTonalidad(ton, acordes) {
    const s = sugerirEscalas(ton, acordes).find((e) => e.nivel === 'recomendada');
    return s.notas;
  }
  const MODO_ACORDE = { '': ['mayor', 'pentMayor'], maj7: ['lidia', 'mayor'], 7: ['mixolidia'], m: ['pentMenor', 'menor'], m7: ['dorica', 'pentMenor'], sus4: ['mixolidia'], dim: null,
    6: ['mayor', 'pentMayor'], m6: ['dorica'], sus2: ['mayor', 'pentMayor'], aug: null, mMaj7: null, dim7: null, m7b5: null };
  function consejoAcorde(nombre, ton) {
    const a = parse(nombre);
    if (!a) return '';
    const ns = notasAcorde(a).map((n) => nota(n, ton.bemol));
    const modos = MODO_ACORDE[a.calidad];
    const base = `arpegio ${ns.join('–')}`;
    if (!modos) return `${base} (acorde de paso: quedate en el arpegio)`;
    return `${base}; ${modos.map((m) => `${nota(a.raiz, ton.bemol)} ${ESCALAS[m].nombre.toLowerCase()}`).join(' o ')}`;
  }
  function notasGuia(nombre, ton) {
    const a = parse(nombre);
    if (!a) return '';
    const i = INTERVALOS[a.calidad] || INTERVALOS[''];
    const g = [i[1]].concat(i[3] !== undefined ? [i[3]] : []);
    return g.map((x) => nota(a.raiz + x, ton.bemol)).join(' y ');
  }

  // cejilla que deja más acordes en posiciones abiertas
  function sugerirCejilla(acordes) {
    const total = acordes.reduce((s, a) => s + a.pulsos, 0) || 1;
    const puntaje = (c) => acordes.reduce((s, a) => { const d = digitacion(transportar(a.nombre, -c, false)); return s + (d && d.abierto ? a.pulsos : 0); }, 0) / total;
    let mejor = 0;
    for (let c = 1; c <= 7; c++) if (puntaje(c) > puntaje(mejor) + 0.15) mejor = c;
    return { traste: mejor, abiertos: puntaje(mejor), sinCejilla: puntaje(0) };
  }

  const nombreNota = (midi, bemol) => nota(midi, bemol) + (Math.floor(midi / 12) - 1);

  return { SOST, BEMOL, pc, mod, nota, tonalidad, parse, transportar, notasAcorde, digitacion, svgGuitarra, svgTeclado, svgDiapason, ESCALAS, escala, sugerirEscalas, notasTonalidad, consejoAcorde, notasGuia, sugerirCejilla, nombreNota };
})();
