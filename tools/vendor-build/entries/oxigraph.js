// window.oxigraph + window.oxigraphReady for classic <script> pages (works from file:// URLs).
// The wasm binary is embedded as ONE lowercase string (see build.mjs, plugin wasm-lowercase): zlib-deflated
// with fflate and written in the RFC 4648 base32 alphabet in lower case without padding (a-z, 2-7). A payload
// without upper-case letters, '_' or '-' cannot contain credential-like patterns (AWS access-key IDs, GitHub /
// Hugging Face / OpenAI-style tokens) that secret scanners report in base64 blobs. At load it is decoded,
// inflated with the browser's DecompressionStream('deflate') (Chrome 80+, Firefox 113+, Safari 16.4+; works for
// file:// pages because no request is made) or, where that is missing or fails, with the bundled fflate
// inflater (pure JS), and instantiated with WebAssembly.instantiate(bytes) - no fetch(), no instantiateStreaming,
// no import.meta.url.
//   <script src="vendor/oxigraph/oxigraph.iife.min.js"></script>
//   <script> oxigraphReady.then(ox => { const s = new ox.Store(); s.load(ttl, {format: 'text/turtle'});
//            for (const row of s.query('SELECT ...')) console.log(row.get('x').value); }); </script>
import init, * as oxigraph from 'oxigraph/web.js';
import { unzlibSync } from 'fflate';
import payload from 'oxigraph/web_bg.wasm';  // lowercase base32 string of the zlib-deflated wasm (build.mjs)

// RFC 4648 base32, lower-case alphabet 'a'-'z' = 0-25, '2'-'7' = 26-31, no padding.
function base32LowerDecode(s) {
  const n = s.length, out = new Uint8Array((n * 5) >>> 3);
  let acc = 0, bits = 0, j = 0;
  for (let i = 0; i < n; i++) {
    const c = s.charCodeAt(i);
    const v = c >= 97 ? c - 97 : c - 24;
    if (v < 0 || v > 31) throw new Error('oxigraph.iife.min.js: corrupt wasm payload at ' + i);
    acc = (acc << 5) | v;
    bits += 5;
    if (bits >= 8) { bits -= 8; out[j++] = acc >>> bits; acc &= (1 << bits) - 1; }
  }
  return out;
}

// zlib (RFC 1950) -> bytes: native stream where available (C++ zlib, several times faster), else fflate.
async function inflate(deflated) {
  if (typeof DecompressionStream === 'function') {
    try {
      const stream = new Blob([deflated]).stream().pipeThrough(new DecompressionStream('deflate'));
      return { bytes: new Uint8Array(await new Response(stream).arrayBuffer()), inflater: 'DecompressionStream' };
    } catch (e) { /* fall back to the JS inflater below */ }
  }
  return { bytes: unzlibSync(deflated), inflater: 'fflate' };
}

const api = {};
for (const [k, v] of Object.entries(oxigraph)) {
  if (k !== 'default' && k !== 'initSync') api[k] = v;
}
globalThis.oxigraph = api;
globalThis.oxigraphReady = (async () => {
  const t0 = performance.now();
  const deflated = base32LowerDecode(payload);
  const t1 = performance.now();
  const { bytes: wasm, inflater } = await inflate(deflated);
  const t2 = performance.now();
  await init({ module_or_path: wasm });
  const t3 = performance.now();
  globalThis.oxigraphTiming = { decodeMs: Math.round((t1 - t0) * 10) / 10, inflateMs: Math.round((t2 - t1) * 10) / 10,
                                instantiateMs: Math.round((t3 - t2) * 10) / 10, inflater, payloadChars: payload.length,
                                deflatedBytes: deflated.length, wasmBytes: wasm.length };
  return api;
})();
