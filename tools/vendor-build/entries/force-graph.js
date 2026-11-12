// window.ForceGraph3D compiled from the 3d-force-graph ESM sources; build.mjs binds 'three' to window.THREE,
// so the graph, three-spritetext (upstream UMD, uses global THREE) and page code share ONE three.js instance.
import ForceGraph3D from '3d-force-graph';

globalThis.ForceGraph3D = ForceGraph3D;
