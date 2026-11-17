// jp_orientation.js — keep the game's GL view in step with the window size (2026-11-09).
//
// Large-screen Android does not rotate the display for a portrait-locked app: launched while the tablet is in
// landscape, Lapis runs letterboxed (window 1471x1840 on the TB373FU). Turning the tablet upright then grows the window
// to 1840x2944 and Cocos2dxRenderer calls nativeOnSurfaceChanged, but cocos2d-x only applied the size once
// (nativeInit), so the game kept drawing into the old 1471x1840 frame and touches were mapped with the old scale.
// Fix: after every surface change whose size differs from the GL view frame, set the new frame size and re-run the
// design-resolution update (same design size and policy the game chose), which also resets the viewport/projection.
//
// Offsets from JP 11.0.0 libgame.so (unchanged original, exports present):
//   GLView::setFrameSize(float,float)        stores _screenSize at +0x24 (design size +0x2c kept unless zero)
//   GLView::setDesignResolutionSize(...)     _designResolutionSize +0x2c, _resolutionPolicy +0x68,
//                                            tail-calls GLView::updateDesignResolutionSize()
//   Director::setViewport()                  _openGLView at Director +0x110
(function () {
  const TAG_ORIENT = 'ORIENT';
  function log(s) { try { note(TAG_ORIENT + ' ' + s); } catch (e) { console.log(TAG_ORIENT + ' ' + s); } }
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const sym = (n) => { const a = m.findExportByName(n); if (!a) log('missing ' + n); return a; };
    const pGet = sym('_ZN7cocos2d8Director11getInstanceEv');
    const pFrame = sym('_ZN7cocos2d6GLView12setFrameSizeEff');
    const pUpdate = sym('_ZN7cocos2d6GLView26updateDesignResolutionSizeEv');
    const pViewport = sym('_ZN7cocos2d8Director11setViewportEv');
    const pChanged = sym('Java_org_cocos2dx_lib_Cocos2dxRenderer_nativeOnSurfaceChanged');
    if (!pGet || !pFrame || !pUpdate || !pViewport || !pChanged) return;
    const getInstance = new NativeFunction(pGet, 'pointer', []);
    const setFrameSize = new NativeFunction(pFrame, 'void', ['pointer', 'float', 'float']);
    const updateDesign = new NativeFunction(pUpdate, 'void', ['pointer']);
    const setViewport = new NativeFunction(pViewport, 'void', ['pointer']);
    Interceptor.attach(pChanged, {
      onEnter(args) { this.w = args[2].toInt32(); this.h = args[3].toInt32(); },
      onLeave() {
        try {
          const dir = getInstance(); if (dir.isNull()) return;
          const view = dir.add(0x110).readPointer(); if (view.isNull()) return;
          const fw = view.add(0x24).readFloat(), fh = view.add(0x28).readFloat();
          if (Math.round(fw) === this.w && Math.round(fh) === this.h) return;
          const dw = view.add(0x2c).readFloat(), dh = view.add(0x30).readFloat(), pol = view.add(0x68).readU32();
          setFrameSize(view, this.w, this.h);
          updateDesign(view);
          setViewport(dir);
          log('resize frame ' + fw + 'x' + fh + ' -> ' + this.w + 'x' + this.h + ' design ' + dw + 'x' + dh + ' policy ' + pol);
        } catch (e) { log('error ' + e); }
      },
    });
    log('hook installed');
  }, 20);
})();
