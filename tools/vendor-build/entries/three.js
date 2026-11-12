// window.THREE for classic <script> pages: three r187 core + the addons VLOnto pages use.
// Addons are exposed on the same namespace (THREE.OrbitControls, ...), like the old examples/js builds.
export * from 'three';
export { OrbitControls } from 'three/addons/controls/OrbitControls.js';
export { TrackballControls } from 'three/addons/controls/TrackballControls.js';
export { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
