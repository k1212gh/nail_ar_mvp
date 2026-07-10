// WebGL2 텍스처드-메시 렌더러 (DESIGN_WARP §3.2, 웹 고티어 consumer).
// WarpSpec(screen 정점 + uv) + atlas 텍스처 + 마스크 텍스처 → 곡면 워핑 디자인 렌더.
// 마스크 텍스처는 전체프레임 알파(union 또는 per-nail). 셰이더에서 곱 + smoothstep 페더.
// 좌표 공유: 정점은 spec.screen(픽셀). buildWarpSpec(warp_spec.mjs)와 동일 수학.

// 격자(ny,nx) → 삼각형 인덱스 (행우선 정점). 순수함수(노드 테스트 가능).
export function gridIndices(ny, nx) {
  const idx = [];
  const stride = nx + 1;
  for (let iy = 0; iy < ny; iy++) {
    for (let ix = 0; ix < nx; ix++) {
      const a = iy * stride + ix, b = a + 1, c = a + stride, d = c + 1;
      idx.push(a, b, d, a, d, c);
    }
  }
  return idx;
}

const VERT = `#version 300 es
precision highp float;
in vec2 aScreen;   // 프레임 픽셀좌표
in vec2 aUV;       // 정규 텍스처좌표
in float aShade;
uniform vec2 uRes; // 캔버스 해상도
out vec2 vUV;
out float vShade;
void main(){
  vUV = aUV; vShade = aShade;
  vec2 clip = vec2(aScreen.x / uRes.x * 2.0 - 1.0, 1.0 - aScreen.y / uRes.y * 2.0);
  gl_Position = vec4(clip, 0.0, 1.0);
}`;

const FRAG = `#version 300 es
precision highp float;
in vec2 vUV; in float vShade;
uniform sampler2D uAtlas;
uniform sampler2D uMask;   // 전체프레임 마스크(알파)
uniform float uAlpha;
uniform float uFeatherUV;
out vec4 o;
void main(){
  // uv∉[0,1] = contain 여백(투명)
  if(vUV.x < 0.0 || vUV.x > 1.0 || vUV.y < 0.0 || vUV.y > 1.0){ discard; }
  vec4 tx = texture(uAtlas, vUV);
  float m = texture(uMask, gl_FragCoord.xy / vec2(textureSize(uMask,0))).r;
  // 화면공간 대신 UV공간 페더는 atlas 알파 사전블러로 처리(엔진). 여기선 마스크 경계 smoothstep.
  float a = tx.a * uAlpha * smoothstep(0.0, 0.5, m);
  o = vec4(tx.rgb * vShade * a, a);
}`;

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
    throw new Error("shader: " + gl.getShaderInfoLog(s));
  return s;
}

export class WarpGL {
  constructor(canvas) {
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: true, alpha: true });
    if (!gl) throw new Error("WebGL2 미지원");
    this.gl = gl; this.canvas = canvas;
    const p = gl.createProgram();
    gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS))
      throw new Error("link: " + gl.getProgramInfoLog(p));
    this.prog = p;
    this.loc = {
      aScreen: gl.getAttribLocation(p, "aScreen"),
      aUV: gl.getAttribLocation(p, "aUV"),
      aShade: gl.getAttribLocation(p, "aShade"),
      uRes: gl.getUniformLocation(p, "uRes"),
      uAtlas: gl.getUniformLocation(p, "uAtlas"),
      uMask: gl.getUniformLocation(p, "uMask"),
      uAlpha: gl.getUniformLocation(p, "uAlpha"),
      uFeatherUV: gl.getUniformLocation(p, "uFeatherUV"),
    };
    this.atlasTex = gl.createTexture();
    this.maskTex = gl.createTexture();
    this.vboS = gl.createBuffer();
    this.vboU = gl.createBuffer();
    this.vboH = gl.createBuffer();
    this.ibo = gl.createBuffer();
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); // premultiplied over
  }

  setAtlas(imgOrCanvas) {
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, this.atlasTex);
    // 일부 모바일 GPU(Adreno)는 밉맵 미완성 텍스처를 '흰색'으로 샘플링 → 밉맵 없이 LINEAR.
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, imgOrCanvas);
  }

  _uploadMask(maskCanvas) {
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, this.maskTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, maskCanvas);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  // specs: [{spec, shade?}] — buildWarpSpec 결과 배열. maskCanvas: 전체프레임 마스크.
  render(specs, W, H, maskCanvas, alpha = 1.0) {
    const gl = this.gl;
    if (this.canvas.width !== W) { this.canvas.width = W; this.canvas.height = H; }
    gl.viewport(0, 0, W, H);
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.prog);
    gl.uniform2f(this.loc.uRes, W, H);
    gl.uniform1f(this.loc.uAlpha, alpha);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.atlasTex);
    gl.uniform1i(this.loc.uAtlas, 0);
    this._uploadMask(maskCanvas);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.maskTex);
    gl.uniform1i(this.loc.uMask, 1);

    for (const { spec, shade } of specs) {
      const [ny, nx] = spec.grid;
      const nV = (ny + 1) * (nx + 1);
      const sArr = new Float32Array(nV * 2);
      const uArr = new Float32Array(nV * 2);
      const hArr = new Float32Array(nV);
      for (let i = 0; i < nV; i++) {
        sArr[i * 2] = spec.screen[i][0]; sArr[i * 2 + 1] = spec.screen[i][1];
        uArr[i * 2] = spec.uv[i][0]; uArr[i * 2 + 1] = spec.uv[i][1];
        hArr[i] = shade ? shade[i] : 1.0;
      }
      const idx = new Uint16Array(gridIndices(ny, nx));
      gl.bindBuffer(gl.ARRAY_BUFFER, this.vboS); gl.bufferData(gl.ARRAY_BUFFER, sArr, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(this.loc.aScreen); gl.vertexAttribPointer(this.loc.aScreen, 2, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.vboU); gl.bufferData(gl.ARRAY_BUFFER, uArr, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(this.loc.aUV); gl.vertexAttribPointer(this.loc.aUV, 2, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.vboH); gl.bufferData(gl.ARRAY_BUFFER, hArr, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(this.loc.aShade); gl.vertexAttribPointer(this.loc.aShade, 1, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.ibo); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, idx, gl.DYNAMIC_DRAW);
      gl.drawElements(gl.TRIANGLES, idx.length, gl.UNSIGNED_SHORT, 0);
    }
  }
}
