// Temporary, read-only JP summon diagnosis. Append after the normal device script.
(function () {
  const timer = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return;
    clearInterval(timer);
    const log = new NativeFunction(Module.getGlobalExportByName('__android_log_write'), 'int', ['int', 'pointer', 'pointer']);
    const tag = Memory.allocUtf8String('JP_GACHA_DIAG');
    const say = s => log(4, tag, Memory.allocUtf8String(String(s)));
    const string = p => { try { const f = p.readU8(); return f & 1 ? p.add(16).readPointer().readUtf8String(Math.min(400, p.add(8).readU64().toNumber())) : p.add(1).readUtf8String(f >> 1); } catch (_) { return '<invalid>'; } };
    let confirm = 0, detail = 0;
    const gachaId = new NativeFunction(m.getExportByName('_ZNK8GachaMst10getGachaIdEv'), 'int', ['pointer']);
    function costs(d) {
      const out = [], seen = new Set();
      function walk(n) {
        if (n.isNull() || seen.has(n.toString()) || seen.size >= 16) return;
        seen.add(n.toString()); walk(n.readPointer());
        const v = n.add(0x28).readPointer();
        out.push(n.add(0x20).readS32() + ':' + [0,4,8,12].map(o => v.add(o).readS32()).join(':'));
        walk(n.add(8).readPointer());
      }
      try { walk(d.add(0x30).readPointer()); return out.join(','); } catch (_) { return '<invalid>'; }
    }
    Interceptor.attach(m.getExportByName('_ZN19GachaPayDetailScene13initSubHeaderEv'), {
      onEnter(a) { const mst = a[0].add(0x5a0).readPointer(); say('HEADER mst=' + mst + ' id=' + gachaId(mst) + ' name=' + string(mst.add(0x28))); }
    });
    for (const [name, kind] of [['_ZN17GachaConfirmScene9setLayoutEv', 'confirm'], ['_ZN19GachaPayDetailScene9setLayoutEv', 'detail']]) {
      const p = m.getExportByName(name); say(name + ' offset=' + p.sub(m.base));
      Interceptor.attach(p, {
        onEnter(a) {
          if (kind === 'confirm') {
            confirm++;
            const mst = a[0].add(0x5a8).readPointer(), d = a[0].add(0x5b0).readPointer();
            say('CONFIRM id=' + gachaId(mst) + ' index=' + a[0].add(0x564).readS32() + ' costs=' + costs(d));
          } else detail++;
          say('ENTER ' + kind + ' self=' + a[0]);
        },
        onLeave() { say('LEAVE ' + kind); if (kind === 'confirm') confirm--; else detail--; }
      });
    }
    for (const e of m.enumerateExports()) {
      if (e.type !== 'function' || !/GachaDetailMst|TicketMstList|UserDiamondInfo|Purchase.*List|ShopMstList|TextManager/.test(e.name) || /C[12]E|D[012]E/.test(e.name)) continue;
      Interceptor.attach(e.address, {
        onEnter(a) { this.go = confirm > 0 || detail > 0; if (!this.go) return; this.text = /getText|getMstText/.test(e.name); if (this.text) this.key = string(a[1]); this.index = /getCostItemMst|isLapisGacha/.test(e.name) ? a[1].toInt32() : undefined; },
        onLeave(r) { if (this.go) say(e.name + (this.index !== undefined ? ' index=' + this.index : '') + (this.key ? ' key=' + this.key : '') + ' -> ' + r + (/getGachaName/.test(e.name) || this.text ? ' text=' + string(r) : '')); }
      });
    }
    // Off by default: Android/ART uses handled SIGSEGV internally; observe real crashes in logcat.
    if (false) Process.setExceptionHandler(e => {
      const c = e.context;
      if (c.pc.compare(m.base) < 0 || c.pc.compare(m.base.add(m.size)) >= 0) return false;
      say('EXCEPTION ' + e.type + ' pc=' + c.pc + ' offset=' + c.pc.sub(m.base) + ' memory=' + JSON.stringify(e.memory));
      for (const r of ['x0','x1','x8','x19','x20','x21','x22','x23','x24','x25','x26','x27','x28','lr']) say(r + '=' + c[r]);
      try { for (let i = -4; i <= 3; i++) say(Instruction.parse(c.pc.add(i * 4))); } catch (_) {}
      say('BACKTRACE ' + Thread.backtrace(c, Backtracer.ACCURATE).map(p => DebugSymbol.fromAddress(p)).join(' < '));
      return false;
    });
    say('READY');
  }, 20);
})();
