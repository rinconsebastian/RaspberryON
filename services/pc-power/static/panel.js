(() => {
  "use strict";

  const POLL_MS = 2000;          // sondeo del estado mientras la página está visible
  const OFFLINE_AFTER_MS = 10000; // sin respuesta durante este tiempo => "Sin conexión"
  const HOLD_MS = 2000;           // tiempo que hay que mantener pulsado el apagado forzado

  const $ = (id) => document.getElementById(id);
  const el = {
    status: $("status"), text: $("state-text"), age: $("state-age"), notice: $("notice"),
    on: $("btn-on"), soft: $("btn-soft"), force: $("btn-force"), force2: $("btn-force2"),
    feedback: $("feedback"), logout: $("btn-logout"), logoutAll: $("btn-logout-all"),
  };

  const LABEL = {
    checking: "Comprobando…", on: "Encendido", off: "Apagado",
    starting: "Encendiendo…", stopping: "Apagando…", offline: "Sin conexión",
  };
  const NOTICE = {
    power_on: "El PC no encendió. Revisa y vuelve a intentarlo.",
    soft_off: "El PC no se apagó.",
    force_off: "El PC no se apagó con el apagado forzado.",
  };

  let last = null;               // última respuesta válida de ./api/status
  let lastOk = performance.now();
  let pending = false;           // hay una petición de acción en vuelo
  let timer = 0;
  let feedbackTimer = 0;

  function say(msg) {
    el.feedback.textContent = msg;
    clearTimeout(feedbackTimer);
    if (msg) feedbackTimer = setTimeout(() => { el.feedback.textContent = ""; }, 5000);
  }

  function fmtAge(sec) {
    sec = Math.max(0, Math.floor(sec));
    if (sec < 60) return "hace unos segundos";
    const m = Math.floor(sec / 60);
    if (m < 60) return `hace ${m} min`;
    const h = Math.floor(m / 60);
    const rest = m % 60;
    if (h < 24) return rest ? `hace ${h} h ${rest} min` : `hace ${h} h`;
    const d = Math.floor(h / 24);
    return `hace ${d} d ${h % 24} h`;
  }

  function render() {
    const now = performance.now();
    const offline = now - lastOk > OFFLINE_AFTER_MS;
    const state = offline ? "offline" : (last ? last.state : "checking");

    el.status.dataset.state = state;
    el.text.textContent = LABEL[state] || state;

    if (!offline && last && (state === "on" || state === "off")) {
      const elapsed = (last.now - last.since) + (now - last.at) / 1000;
      el.age.textContent = (state === "on" ? "Encendido " : "Apagado ") + fmtAge(elapsed);
    } else {
      el.age.textContent = "";
    }

    // Las acciones se muestran según el último estado conocido; se deshabilitan si no son fiables.
    const known = last ? last.state : "checking";
    el.on.hidden = known !== "off";
    el.soft.hidden = known !== "on";
    el.force.hidden = known !== "on";
    el.force2.hidden = !(known === "off" || known === "stopping");

    const enabled = !offline && !pending && last && !last.busy;
    for (const b of [el.on, el.soft, el.force, el.force2]) b.disabled = !enabled;

    if (!offline && last && last.notice && NOTICE[last.notice.action]) {
      el.notice.textContent = NOTICE[last.notice.action];
      el.notice.hidden = false;
    } else {
      el.notice.hidden = true;
    }

    renderSchedule(known, offline);
  }

  // ---- Programación de encendido / apagado únicos ---------------------------
  const sch = {
    onRow: $("sch-on"), onText: $("sch-on-text"), onCancel: $("sch-on-cancel"),
    offRow: $("sch-off"), offText: $("sch-off-text"), offCancel: $("sch-off-cancel"),
    onForm: $("sch-on-form"), offForm: $("sch-off-form"), clock: $("clock"),
  };

  function renderSchedule(known, offline) {
    const s = last && last.schedule;
    if (!s) { for (const e of [sch.onRow, sch.offRow, sch.onForm, sch.offForm]) e.hidden = true; return; }

    sch.onRow.hidden = !s.on;
    if (s.on) sch.onText.textContent = `Encendido programado: ${s.on}`;

    const waiting = !!s.off_wait;
    sch.offRow.hidden = !(s.off || waiting);
    if (waiting) sch.offText.textContent = `Esperando a que se apague (fuerza a las ${s.off_wait.force_label})`;
    else if (s.off) sch.offText.textContent = `Apagado programado: ${s.off}`;

    sch.onForm.hidden = !(known === "off" && !s.on);
    sch.offForm.hidden = !(known === "on" && !s.off && !waiting);

    const dis = offline || pending;
    for (const e of [sch.onCancel, sch.offCancel, ...sch.onForm.elements, ...sch.offForm.elements]) e.disabled = dis;

    try {
      const t = new Date((s.now + (performance.now() - last.at) / 1000) * 1000)
        .toLocaleTimeString("es", { timeZone: s.tz, hour: "2-digit", minute: "2-digit" });
      sch.clock.textContent = `Hora del equipo: ${t}`;
    } catch (_) { sch.clock.textContent = ""; }
  }

  async function scheduleCall(method, kind, time) {
    try {
      const res = await fetch(`api/schedule/${kind}`, {
        method,
        headers: time ? { "Content-Type": "application/json" } : {},
        credentials: "same-origin",
        body: time ? JSON.stringify({ time }) : undefined,
      });
      if (res.status === 404) { location.reload(); return; }
      if (res.status === 409) say("El estado cambió; no se pudo programar.");
      else if (res.status === 400) say("Hora no válida.");
      else if (!res.ok) say("No se pudo guardar la programación.");
      else say(method === "PUT" ? "Programado." : "Cancelado.");
    } catch (_) {
      say("No se pudo guardar la programación.");
    }
    poll();
  }

  sch.onForm.addEventListener("submit", (e) => { e.preventDefault(); scheduleCall("PUT", "on", $("sch-on-time").value); });
  sch.offForm.addEventListener("submit", (e) => { e.preventDefault(); scheduleCall("PUT", "off", $("sch-off-time").value); });
  sch.onCancel.addEventListener("click", () => scheduleCall("DELETE", "on"));
  sch.offCancel.addEventListener("click", () => scheduleCall("DELETE", "off"));

  async function poll() {
    clearTimeout(timer);
    try {
      const res = await fetch("api/status", { cache: "no-store", credentials: "same-origin" });
      if (res.status === 404) { location.reload(); return; } // sesión caducada o revocada
      if (res.ok) {
        last = { ...(await res.json()), at: performance.now() };
        lastOk = performance.now();
      }
    } catch (_) { /* sin red: render() mostrará "Sin conexión" pasado el plazo */ }
    render();
    if (document.visibilityState === "visible") timer = setTimeout(poll, POLL_MS);
  }

  async function send(type) {
    if (pending) return;
    pending = true;
    render();
    try {
      const res = await fetch("api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ type }),
      });
      if (res.status === 404) { location.reload(); return; }
      if (res.status === 202) {
        say("Pulso enviado.");
        if (last) last.busy = true;
      } else if (res.status === 409) {
        const data = await res.json().catch(() => ({}));
        say(data.reason === "busy" ? "Hay una acción en curso." : "El estado cambió; se ha actualizado.");
      } else {
        say("No se pudo enviar la acción.");
      }
    } catch (_) {
      say("No se pudo enviar la acción.");
    } finally {
      pending = false;
      poll(); // refresca ya, para mostrar la transición
    }
  }

  // "Forzar apagado": hay que mantener pulsado HOLD_MS; un toque breve no acciona nada.
  function bindHold(btn) {
    const fill = btn.querySelector(".fill");
    let t0 = 0, raf = 0, fired = false;

    const tick = () => {
      const p = Math.min(1, (performance.now() - t0) / HOLD_MS);
      fill.style.width = `${p * 100}%`;
      if (p >= 1) { fired = true; stop(false); send("force_off"); } else raf = requestAnimationFrame(tick);
    };
    const start = () => { if (btn.disabled || t0) return; fired = false; t0 = performance.now(); tick(); };
    const stop = (aborted) => {
      if (!t0) return;
      cancelAnimationFrame(raf);
      t0 = 0;
      fill.style.width = "0";
      if (aborted && !fired) say("Mantén pulsado 2 segundos para forzar el apagado.");
    };

    btn.addEventListener("pointerdown", (e) => {
      try { btn.setPointerCapture(e.pointerId); } catch (_) { /* no crítico */ }
      start();
    });
    for (const ev of ["pointerup", "pointercancel", "lostpointercapture"]) {
      btn.addEventListener(ev, () => stop(true));
    }
    btn.addEventListener("keydown", (e) => {
      if ((e.key === " " || e.key === "Enter") && !e.repeat) { e.preventDefault(); start(); }
    });
    btn.addEventListener("keyup", (e) => {
      if (e.key === " " || e.key === "Enter") stop(true);
    });
    btn.addEventListener("click", (e) => e.preventDefault());
    btn.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  async function logout(all) {
    try {
      await fetch(all ? "api/logout-all" : "api/logout", { method: "POST", credentials: "same-origin" });
    } finally {
      location.reload();
    }
  }

  // ---- Actividad: se carga al abrir la sección, no en cada sondeo ----------
  const activity = $("activity");
  async function loadActivity() {
    try {
      const res = await fetch("api/events?limit=50", { cache: "no-store", credentials: "same-origin" });
      if (res.status === 404) { location.reload(); return; }
      if (!res.ok) return;
      const items = await res.json();
      const list = $("activity-list");
      list.textContent = "";
      const skew = last ? last.now - Date.now() / 1000 : 0; // corrige la diferencia de reloj con el servidor
      for (const e of items) {
        const li = document.createElement("li");
        const when = document.createElement("span");
        when.className = "when";
        when.textContent = fmtAge(Date.now() / 1000 + skew - e.ts);
        const what = document.createElement("span");
        what.className = "what";
        what.textContent = e.text;
        li.append(when, what);
        list.append(li);
      }
      $("activity-empty").hidden = items.length > 0;
    } catch (_) { /* sin red: se reintentará al volver a abrir */ }
  }
  activity.addEventListener("toggle", () => { if (activity.open) loadActivity(); });

  el.on.addEventListener("click", () => send("power_on"));
  el.soft.addEventListener("click", () => send("soft_off"));
  bindHold(el.force);
  bindHold(el.force2);
  el.logout.addEventListener("click", () => logout(false));
  el.logoutAll.addEventListener("click", () => logout(true));

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poll(); else clearTimeout(timer);
  });

  render();
  poll();
})();
