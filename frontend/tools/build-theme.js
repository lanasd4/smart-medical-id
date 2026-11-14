/*
 * Builds assets/vendor from a licensed Vuexy template: brand colour, minified CSS/JS, official library builds.
 *   node tools/build-theme.js <vuexy-template-dir> [output-dir]
 */
const fs = require('fs');
const path = require('path');

const TEMPLATE = path.resolve(process.argv[2] || '../../Vuexy-Original-Template');
const OUT = path.resolve(process.argv[3] || path.join(__dirname, '..', 'assets', 'vendor'));
const req = name => require(path.join(TEMPLATE, 'node_modules', name));
const CleanCSS = req('clean-css');
const { minify } = req('terser');

const BRAND = { light: '#0B7F7B', dark: '#2BB3AD' };
const VUEXY_PRIMARY = { h: 245, s: 82, l: 67 };

// colour helpers ----------
function hexToRgb(hex) {
  hex = hex.replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  return [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
}
function rgbToHex([r, g, b]) {
  return '#' + [r, g, b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
}
function rgbToHsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0; const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
  }
  return { h, s: s * 100, l: l * 100 };
}
function hslToRgb({ h, s, l }) {
  s /= 100; l /= 100;
  const k = n => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0) * 255, f(8) * 255, f(4) * 255];
}
function makeRecolor(brandHex) {
  const B = rgbToHsl(hexToRgb(brandHex));
  const P = VUEXY_PRIMARY;
  return rgb => {
    const c = rgbToHsl(rgb);
    if (!(c.h >= 236 && c.h <= 256 && c.s >= 45)) return null; // not a primary-derived colour
    const l = c.l <= P.l ? (c.l * B.l) / P.l : B.l + ((c.l - P.l) * (100 - B.l)) / (100 - P.l);
    const s = Math.min(100, (c.s * B.s) / P.s);
    return hslToRgb({ h: B.h, s, l });
  };
}

function recolorCss(css, brandHex) {
  const map = makeRecolor(brandHex);
  let n = 0;
  const swapHex = (m, hex) => { const out = map(hexToRgb(hex)); if (!out) return m; n++; return rgbToHex(out); };
  css = css.replace(/#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b/g, (m, hex) => swapHex(m, hex));
  css = css.replace(/%23([0-9a-fA-F]{6})\b/g, (m, hex) => { const r = swapHex(m, hex); return r === m ? m : '%23' + r.slice(1); });
  css = css.replace(/rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/g, (m, r, g, b) => {
    const out = map([+r, +g, +b]); if (!out) return m; n++;
    return m.replace(/\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}/, '(' + out.map(Math.round).join(', '));
  });
  css = css.replace(/(--[\w-]*rgb\s*:\s*)(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/g, (m, pre, r, g, b) => {
    const out = map([+r, +g, +b]); if (!out) return m; n++;
    return pre + out.map(Math.round).join(', ');
  });
  return { css, n };
}

function write(rel, content) {
  const file = path.join(OUT, rel);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
  return file;
}

// CSS ----------
const SRC_VENDOR = path.join(TEMPLATE, 'assets', 'vendor');
const cssFiles = [
  ['css/rtl/core.css', 'light'], ['css/rtl/core-dark.css', 'dark'],
  ['css/rtl/theme-default.css', 'light'], ['css/rtl/theme-default-dark.css', 'dark'],
  ['libs/flatpickr/flatpickr.css', 'light'], ['libs/sweetalert2/sweetalert2.css', 'light'],
  ['libs/apex-charts/apex-charts.css', 'light'], ['libs/fullcalendar/fullcalendar.css', 'light'],
  ['libs/perfect-scrollbar/perfect-scrollbar.css', 'light'], ['libs/node-waves/node-waves.css', 'light'],
  ['fonts/tabler-icons.css', null],
];
const cleaner = new CleanCSS({ level: 1, rebase: false });
for (const [rel, mode] of cssFiles) {
  let css = fs.readFileSync(path.join(SRC_VENDOR, rel), 'utf8');
  const before = css.length;
  let n = 0;
  if (mode) ({ css, n } = recolorCss(css, BRAND[mode]));
  if (rel === 'fonts/tabler-icons.css') {
    // modern browsers only need woff2/woff; show icons only once the font is ready
    css = css.replace(/,\s*url\("tabler\/tabler-icons\.ttf[^)]*\)\s*format\("truetype"\)/, '')
             .replace(/font-weight:\s*400;\s*src:/, 'font-weight:400;font-display:block;src:');
  }
  const out = cleaner.minify(css);
  if (out.errors.length) throw new Error(rel + ': ' + out.errors.join(', '));
  write(rel, out.styles);
  console.log(`css  ${rel.padEnd(45)} ${(before / 1024).toFixed(0)}KB -> ${(out.styles.length / 1024).toFixed(0)}KB, ${n} colours`);
}

// Vuexy JS (from source, minified) ----------
(async () => {
  for (const name of ['helpers', 'menu']) {
    const src = fs.readFileSync(path.join(TEMPLATE, 'js', name + '.js'), 'utf8').replace(/^export\s*\{[^}]*\}\s*;?\s*$/m, '');
    const res = await minify(src, { ecma: 2020, compress: true, mangle: true, format: { comments: false } });
    write(`js/${name}.js`, res.code);
    console.log(`js   js/${name}.js ${(src.length / 1024).toFixed(0)}KB -> ${(res.code.length / 1024).toFixed(0)}KB`);
  }
  // FullCalendar official production build ----------
  const fc = path.join(TEMPLATE, 'node_modules', '@fullcalendar');
  const parts = ['core/index.global.min.js', 'daygrid/index.global.min.js', 'timegrid/index.global.min.js',
    'interaction/index.global.min.js', 'list/index.global.min.js', 'core/locales/ar.global.min.js'];
  const bundle = parts.map(p => fs.readFileSync(path.join(fc, p), 'utf8')).join('\n;\n');
  write('libs/fullcalendar/fullcalendar.js', bundle);
  console.log(`js   libs/fullcalendar/fullcalendar.js -> ${(bundle.length / 1024).toFixed(0)}KB (official build)`);

  // other libraries: official minified builds instead of dev (eval) bundles ----------
  const nm = p => fs.readFileSync(path.join(TEMPLATE, 'node_modules', p), 'utf8');
  const official = {
    'libs/bootstrap/bootstrap.bundle.js': ['bootstrap/dist/js/bootstrap.bundle.min.js'],  // includes Popper
    'libs/perfect-scrollbar/perfect-scrollbar.js': ['perfect-scrollbar/dist/perfect-scrollbar.min.js'],
    'libs/flatpickr/flatpickr.js': ['flatpickr/dist/flatpickr.min.js', 'flatpickr/dist/l10n/ar.js'],
    'libs/sweetalert2/sweetalert2.js': ['sweetalert2/dist/sweetalert2.min.js'],
    'libs/hammer/hammer.js': ['hammerjs/hammer.min.js'],
    'libs/node-waves/node-waves.js': ['node-waves/dist/waves.min.js'],
  };
  for (const [rel, srcs] of Object.entries(official)) {
    const code = srcs.map(nm).join('\n;\n');
    write(rel, code);
    console.log(`js   ${rel.padEnd(45)} -> ${(code.length / 1024).toFixed(0)}KB (official build)`);
  }

  // files copied as they are ----------
  for (const rel of ['fonts/tabler/tabler-icons.woff2', 'fonts/tabler/tabler-icons.woff', 'libs/apex-charts/apexcharts.js']) {
    const dest = path.join(OUT, rel);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(path.join(SRC_VENDOR, rel), dest);
    console.log(`copy ${rel}`);
  }

  // one core bundle loaded by every page (fewer requests) ----------
  const core = ['libs/bootstrap/bootstrap.bundle.js', 'libs/perfect-scrollbar/perfect-scrollbar.js',
    'libs/hammer/hammer.js', 'libs/node-waves/node-waves.js', 'js/menu.js']
    .map(rel => fs.readFileSync(path.join(OUT, rel), 'utf8')).join('\n;\n');
  write('core.bundle.js', core);
  console.log(`js   core.bundle.js -> ${(core.length / 1024).toFixed(0)}KB`);
})().catch(e => { console.error(e); process.exit(1); });
