// build.mjs - classic-script (IIFE) bundles for VLOnto pages that must work from file:// URLs.
// Run by tools/vendor_build.py with cwd = the npm work dir (node_modules installed by `npm ci`):
//   node build.mjs <outDir>
// Outputs (all plain <script src> files, no ES modules, no fetch):
//   three/three.iife.min.js                 -> window.THREE (three r187 core + OrbitControls, TrackballControls,
//                                              CSS2DRenderer, CSS2DObject). Load it first.
//   3d-force-graph/3d-force-graph.iife.min.js -> window.ForceGraph3D, compiled from the ESM sources with every
//                                              `import ... from "three"` bound to window.THREE (one THREE instance)
//   oxigraph/oxigraph.iife.min.js           -> window.oxigraph (API) and window.oxigraphReady (Promise); the
//                                              4.3 MB WebAssembly binary is embedded as a lowercase-only string
//                                              (zlib via fflate, RFC 4648 base32 in lower case, no padding: a-z2-7,
//                                              so no credential-like pattern can occur in it), decoded + inflated at
//                                              load and instantiated with WebAssembly.instantiate(bytes) - no fetch.
import * as esbuild from 'esbuild';
import { zlibSync } from 'fflate';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const outDir = path.resolve(process.argv[2] || 'out');
const meta = { esbuild: esbuild.version, bundles: {} };

// 'three' and 'three/webgpu' -> the global THREE created by three.iife.min.js.
// (three-render-objects imports 'three/webgpu' only for its optional WebGPU renderer; VLOnto uses WebGL.)
const threeGlobal = {
  name: 'three-global',
  setup(build) {
    build.onResolve({ filter: /^three(\/webgpu)?$/ }, (args) => ({ path: args.path, namespace: 'three-global' }));
    build.onLoad({ filter: /.*/, namespace: 'three-global' }, () => ({
      contents:
        'if (typeof globalThis.THREE !== "object" || !globalThis.THREE.REVISION) {\n' +
        '  throw new Error("3d-force-graph.iife.min.js: load vendor/three/three.iife.min.js first (window.THREE is missing)");\n' +
        '}\nmodule.exports = globalThis.THREE;\n',
      loader: 'js',
    }));
  },
};

// *.wasm -> `export default "<payload>"`: zlib-deflated with fflate (pure JS, so the bytes do not depend on the
// CPU or on Node's zlib build) and encoded as RFC 4648 base32 in lower case without padding. Upper-case letters,
// '_' and '-' never occur, so credential patterns (AWS access-key IDs, Google API keys, GitHub / Hugging Face /
// OpenAI-style / Slack tokens) cannot appear by chance the way they do in base64.
const B32 = 'abcdefghijklmnopqrstuvwxyz234567';
function base32Lower(bytes) {
  const parts = new Array(Math.ceil((bytes.length * 8) / 5));
  let acc = 0, bits = 0, k = 0;
  for (let i = 0; i < bytes.length; i++) {
    acc = (acc << 8) | bytes[i];
    bits += 8;
    while (bits >= 5) { bits -= 5; parts[k++] = B32[(acc >>> bits) & 31]; }
    acc &= (1 << bits) - 1;
  }
  if (bits > 0) parts[k++] = B32[(acc << (5 - bits)) & 31];
  return parts.join('');
}
const sha256hex = (b) => crypto.createHash('sha256').update(b).digest('hex');
const wasmLowercase = {
  name: 'wasm-lowercase',
  setup(build) {
    build.onLoad({ filter: /\.wasm$/ }, async (args) => {
      const raw = new Uint8Array(await fs.promises.readFile(args.path));
      const deflated = zlibSync(raw, { level: 9, mem: 12 });
      const text = base32Lower(deflated);
      if (!/^[a-z2-7]+$/.test(text)) throw new Error('wasm payload is not lowercase base32');
      meta.wasm = {
        file: args.path.slice(args.path.lastIndexOf('node_modules/') + 'node_modules/'.length),
        wasm_bytes: raw.length, wasm_sha256: sha256hex(raw),
        deflated_bytes: deflated.length, payload_chars: text.length,
        encoding: 'zlib (fflate level 9, mem 12) + RFC 4648 base32, lower case, no padding (a-z2-7)',
      };
      return { contents: `export default ${JSON.stringify(text)};\n`, loader: 'js' };
    });
  },
};

const common = {
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: ['es2020'],
  minify: true,
  legalComments: 'eof',
  metafile: true,
  logLevel: 'warning',
  logOverride: { 'empty-import-meta': 'silent' },
};

async function bundle(name, opts) {
  const r = await esbuild.build({ ...common, ...opts });
  const inputs = Object.keys(r.metafile.inputs);
  const pkgs = new Set();
  for (const f of inputs) {
    const m = f.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//g);
    if (m) pkgs.add(m[m.length - 1].replace(/^node_modules\//, '').replace(/\/$/, ''));
  }
  meta.bundles[name] = { outfile: path.relative(outDir, opts.outfile), inputs: inputs.length, packages: [...pkgs].sort() };
  for (const w of r.warnings) console.log(`[${name}] warning: ${w.text}`);
}

await bundle('three', {
  entryPoints: ['entries/three.js'],
  globalName: 'THREE',
  outfile: path.join(outDir, 'three/three.iife.min.js'),
});
await bundle('3d-force-graph', {
  entryPoints: ['entries/force-graph.js'],
  outfile: path.join(outDir, '3d-force-graph/3d-force-graph.iife.min.js'),
  plugins: [threeGlobal],
});
await bundle('oxigraph', {
  entryPoints: ['entries/oxigraph.js'],
  outfile: path.join(outDir, 'oxigraph/oxigraph.iife.min.js'),
  plugins: [wasmLowercase],
});
if (!meta.wasm) throw new Error('oxigraph bundle: the wasm-lowercase plugin did not run');
meta.bundles.oxigraph.embedded_wasm = meta.wasm;
delete meta.wasm;
fs.writeFileSync(path.join(outDir, 'build-meta.json'), JSON.stringify(meta, null, 1) + '\n');
console.log(`esbuild ${esbuild.version}: built ${Object.keys(meta.bundles).join(', ')}`);
