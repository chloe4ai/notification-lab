/* Notification Lab — renders the simulated data in docs/data/. No framework. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (x, d = 1) => Number(x).toFixed(d);
  const pct = (x) => Math.round(x * 100) + "%";

  const S = { persona: "minimalist", day: 1, timer: null };
  let D = null;

  Promise.all(["meta", "recommendations", "cohort", "lived"].map((n) =>
    fetch(`data/${n}.json`).then((r) => { if (!r.ok) throw new Error(n); return r.json(); })))
    .then(([meta, recs, cohort, lived]) => {
      D = { meta, recs, cohort, lived };
      const typeLabel = {};
      meta.types.forEach((t) => (typeLabel[t.key] = t.label));
      D.typeLabel = typeLabel;
      let hash = (location.hash || "").replace("#", "");
      if (D.meta.personas[hash]) S.persona = hash;
      bind();
      renderAll();
    })
    .catch((e) => {
      $("persona-blurb").textContent = "The data files did not load (" + e.message + "). Serve the docs/ folder over HTTP, for example: python3 -m http.server -d docs";
    });

  function bind() {
    document.querySelectorAll("[data-persona]").forEach((b) =>
      b.addEventListener("click", () => {
        S.persona = b.dataset.persona; S.day = 1; stop();
        try { history.replaceState(null, "", "#" + S.persona); } catch (e) { /* ignore */ }
        renderAll();
      }));
    $("day").addEventListener("input", (e) => { S.day = +e.target.value; renderDay(); });
    $("play").addEventListener("click", () => (S.timer ? stop() : play()));
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderCharts);
    window.addEventListener("hashchange", () => {
      const h = (location.hash || "").replace("#", "");
      if (D.meta.personas[h] && h !== S.persona) { S.persona = h; S.day = 1; stop(); renderAll(); }
    });
  }
  /* ---------- shared hover tooltip: any element with data-tip ---------- */
  const tip = $("tip");
  document.addEventListener("mousemove", (e) => {
    const t = e.target.closest && e.target.closest("[data-tip]");
    if (!t) { tip.hidden = true; return; }
    tip.innerHTML = t.dataset.tip; tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + w > innerWidth - 8) x = e.clientX - w - 14;
    if (y + h > innerHeight - 8) y = e.clientY - h - 14;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  });
  document.addEventListener("mouseleave", () => (tip.hidden = true));
  document.addEventListener("scroll", () => (tip.hidden = true), { passive: true });
  const PN = { minimalist: "Notification minimalist", casual: "Casual browser", contributor: "Active contributor" };
  const cum = (arr) => { let a = 0; return arr.map((v) => (a += v / 100)); };
  const reach = (arr) => arr.reduce((a, b) => a + b, 0);

  function play() {
    if (S.day >= 30) S.day = 0;
    $("play").textContent = "❚❚ Pause";
    S.timer = setInterval(() => {
      if (S.day >= 30) return stop();
      S.day += 1; $("day").value = S.day; renderDay();
    }, 850);
  }
  function stop() { clearInterval(S.timer); S.timer = null; $("play").textContent = "▶ Play"; }

  function renderAll() {
    document.querySelectorAll("[data-persona]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.persona === S.persona)));
    const p = D.meta.personas[S.persona];
    $("persona-blurb").textContent = p.blurb;
    $("gen-at").textContent = "Data generated " + D.meta.generated_at.replace("T", " ").replace("+00:00", " UTC");
    $("day").value = S.day;
    renderKpis(); renderDashboard(); renderLivedStatic(); renderDay(); renderVolume(); renderMix(); renderLongrun(); renderCharts(); renderData();
  }

  /* ---------- KPIs ---------- */
  function renderKpis() {
    const v = D.recs[S.persona].validation, sq = v.status_quo, rc = v.recommended, days = D.meta.horizon_days;
    const tile = (k, a, b, note) => `<div class="kpi"><div class="k">${k}</div><div class="pair">
      <div><span class="who">Today's default</span><span class="num sq">${a}</span></div>
      <div><span class="who">Recommended</span><span class="num rec">${b}</span></div></div><p class="n">${note}</p></div>`;
    const diff = rc.incremental_active_days - sq.incremental_active_days;
    const fewer = Math.round((1 - rc.sends_per_user_day / Math.max(0.01, sq.sends_per_user_day)) * 100);
    const tied = Math.abs(diff) <= rc.ci95 + sq.ci95;
    const liftNote = tied
      ? `<b>Same lift</b> within the 95% interval, with <b>${fewer}%</b> fewer pushes (${fmt(rc.sends_per_user_day)} a day instead of ${fmt(sq.sends_per_user_day)}).`
      : `<b>${diff > 0 ? "+" : ""}${Math.round((diff / Math.max(0.01, sq.incremental_active_days)) * 100)}%</b> lift, with <b>${fewer}%</b> fewer pushes (${fmt(rc.sends_per_user_day)} a day instead of ${fmt(sq.sends_per_user_day)}).`;
    $("kpis").innerHTML =
      tile(`Extra active days per user · ${days} days`, "+" + fmt(sq.incremental_active_days), "+" + fmt(rc.incremental_active_days), liftNote) +
      tile(`Push still on at day ${days}`, pct(sq.push_on_end), pct(rc.push_on_end),
        `Measured on a fresh cohort of ${D.meta.validation_users.toLocaleString("en-US")} people the optimiser never saw.`) +
      tile(`Do Not Disturb days per user`, fmt(sq.dnd_days_per_user, 0), fmt(rc.dnd_days_per_user, 1),
        `Days the person muted everything after too many ignored pushes.`);
  }

  /* ---------- Lived experience ---------- */
  const POLS = ["status_quo", "recommended"];
  function renderLivedStatic() {
    const L = D.lived[S.persona], rp = D.recs[S.persona].recommended_policy;
    $("sub-status_quo").textContent = "up to 5 a day, ranked by relevance";
    $("sub-recommended").textContent = `fatigue-aware, never more than ${rp.cap} a day`;
    POLS.forEach((k) => {
      const days = L[k].days;
      $("strip-" + k).innerHTML = days.map((d) => {
        const n = d.notifications.length, op = d.notifications.some((x) => x.outcome === "opened");
        const off = !d.push_on && !d.revoked_today;
        const h = Math.min(100, n * 20);
        const cls = [op ? "op" : "", d.dnd ? "dnd" : "", off ? "off" : ""].join(" ");
        const label = `Day ${d.day}: ${n} push${n === 1 ? "" : "es"}${op ? ", opened one" : ""}${d.dnd ? ", Do Not Disturb" : ""}${off ? ", push off" : ""}`;
        return `<button type="button" class="${cls}" data-day="${d.day}" aria-label="${label}" title="${label}"><i style="height:${h}%"></i></button>`;
      }).join("");
      $("strip-" + k).querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        stop(); S.day = +b.dataset.day; $("day").value = S.day; renderDay();
      }));
    });
    const pop = (k) => L[k].population;
    $("pop").innerHTML = `<p style="margin:0 0 6px">Across <b>${pop("status_quo").people}</b> simulated people like this, first 30 days:</p>
      ${row("Turned push off", pct(pop("status_quo").share_revoked), pct(pop("recommended").share_revoked))}
      ${row("Do Not Disturb days", fmt(pop("status_quo").mean_dnd_days), fmt(pop("recommended").mean_dnd_days))}
      ${row("Pushes received", fmt(pop("status_quo").mean_sends, 0), fmt(pop("recommended").mean_sends, 0))}
      ${row("Pushes opened", fmt(pop("status_quo").mean_opens), fmt(pop("recommended").mean_opens))}
      <p style="margin:8px 0 0;font-size:12px">Default <span class="sqv">■</span> · Recommended <span class="recv">■</span></p>`;
    function row(k, a, b) { return `<div class="row"><span>${k}</span><span><span class="sqv">${a}</span> · <span class="recv">${b}</span></span></div>`; }
  }

  const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  function renderDay() {
    $("day-v").textContent = S.day;
    const L = D.lived[S.persona];
    POLS.forEach((k) => {
      const days = L[k].days, d = days[S.day - 1];
      const off = !d.push_on && !d.revoked_today;
      const notes = d.notifications;
      const last = notes.length ? notes[notes.length - 1].time : "21:30";
      let banners = "";
      if (off) banners += `<div class="banner off">⦸ Push notifications are off for this app</div>`;
      else if (d.dnd) banners += `<div class="banner dnd">☾ Do Not Disturb turned on after too many pushes</div>`;
      if (d.revoked_today) banners += `<div class="banner off">⦸ Turned push off tonight</div>`;
      if (!off && !notes.length) banners += `<div class="banner quiet">Nothing cleared the bar today, so nothing was sent</div>`;
      const cards = notes.map((n) => `<div class="push ${n.outcome}">
          <div class="h"><span class="app"><i class="ico"></i>Threadline</span><span>${esc(n.time)} <span class="tag ${n.outcome}">${n.outcome === "muted" ? "silenced" : n.outcome}</span></span></div>
          <div class="ti">${esc(n.title)}</div><div class="bo">${esc(n.body)}</div>
          <div class="c">r/${esc(n.community)} · ${esc(D.typeLabel[n.type])}</div></div>`).reverse().join("");
      const empty = off ? `<div class="empty">This person will not hear from the app again unless they go into settings and turn push back on.</div>` : "";
      $("screen-" + k).innerHTML = `<div class="sbar"><span>${esc(last)}</span><span>● ● ●</span></div>
        <div class="clock"><div class="d">${WEEK[(S.day - 1) % 7]} · Day ${S.day}</div><div class="t">${esc(last)}</div></div>
        ${banners}<div class="stack">${cards}${empty}</div>`;
      $("fat-" + k).style.width = Math.round(d.fatigue_end * 100) + "%";
      $("strip-" + k).querySelectorAll("button").forEach((b) => b.classList.toggle("cur", +b.dataset.day === S.day));
      let sent = 0, opened = 0, dnd = 0, offDay = 0;
      days.slice(0, S.day).forEach((x) => {
        sent += x.notifications.length; opened += x.notifications.filter((n) => n.outcome === "opened").length;
        dnd += x.dnd ? 1 : 0; if (x.revoked_today) offDay = x.day;
      });
      $("tally-" + k).innerHTML = `By day ${S.day}: <b>${sent}</b> pushes, <b>${opened}</b> opened, <b>${dnd}</b> Do Not Disturb day${dnd === 1 ? "" : "s"}` +
        (offDay ? `, <b>push turned off on day ${offDay}</b>.` : ".");
    });
  }


  /* ---------- Dashboard ---------- */
  function renderDashboard() {
    const R = D.recs[S.persona], v = R.validation, sq = v.status_quo, rc = v.recommended, bv = v.best_volume_first;
    const C = D.cohort[S.persona], days = D.meta.horizon_days;
    const rSq = reach(C.status_quo.push_on), rRc = reach(C.recommended.push_on);
    const opens = (x) => x.sends_per_user_day * days * x.open_rate;
    const cost = (x) => (x.sends_per_user_day * days) / Math.max(0.01, x.incremental_active_days);
    const T = [
      ["Pushes per day", fmt(sq.sends_per_user_day, 2), fmt(rc.sends_per_user_day, 2), "lower", "Average pushes sent per person per day, including days after they turned push off (zero)."],
      ["Extra active days", "+" + fmt(sq.incremental_active_days), "+" + fmt(rc.incremental_active_days), "higher", `Lift versus the same person with no pushes, over ${days} days. ± ${fmt(sq.ci95)} and ± ${fmt(rc.ci95)} (95%).`],
      ["Open rate", pct(sq.open_rate), pct(rc.open_rate), "higher", "Opened pushes ÷ pushes sent. Silenced pushes count as sent and not opened."],
      [`Opens per person · ${days}d`, fmt(opens(sq)), fmt(opens(rc)), "higher", "Pushes per day × days × open rate. Fewer sends can still mean more opens."],
      ["Push on · day 30", pct(sq.push_on_day30), pct(rc.push_on_day30), "higher", "Share of people who still have push enabled after the first month."],
      [`Push on · day ${days}`, pct(sq.push_on_end), pct(rc.push_on_end), "higher", "Share of people who still have push enabled at the end. Permission never comes back."],
      ["Reach days", fmt(rSq, 0), fmt(rRc, 0), "higher", `Of ${days} days, how many the average person could still be reached (area under the permission curve).`],
      ["DND days per person", fmt(sq.dnd_days_per_user, 1), fmt(rc.dnd_days_per_user, 1), "lower", "Days the person silenced everything after too many ignored pushes."],
      ["Pushes per extra active day", fmt(cost(sq), 0), fmt(cost(rc), 0), "lower", "Total pushes sent ÷ extra active days. The cost of one unit of lift."],
    ];
    $("tiles").innerHTML = T.map(([k, a, b, want, def]) => {
      const na = parseFloat(a), nb = parseFloat(b);
      const better = want === "higher" ? nb > na : nb < na, same = Math.abs(nb - na) < 1e-9;
      const d = nb - na, isPct = /%$/.test(a);
      const delta = (d > 0 ? "▲ " : "▼ ") + (isPct ? Math.abs(Math.round(d)) + " pts" : fmt(Math.abs(d), Number.isInteger(na) && Number.isInteger(nb) ? 0 : 1));
      return `<div class="tile" data-tip="${esc(def)}"><div class="k">${k}</div>
        <div class="pair"><div><span class="who">Default</span><span class="num sq">${a}</span></div><div><span class="who">Recommended</span><span class="num rec">${b}</span></div></div>
        <div class="delta ${same ? "flat" : better ? "good" : "bad"}">${same ? "no change" : delta + (better ? " · better" : " · worse")}</div></div>`;
    }).join("");

    // mechanism vs volume
    const row = (name, x, hl) => `<tr class="${hl ? "hl" : ""}"><td>${name}</td><td>${esc(x.policy)}</td><td class="n">${fmt(x.sends_per_user_day, 2)}</td><td class="n">+${fmt(x.incremental_active_days)} ± ${fmt(x.ci95)}</td><td class="n">${pct(x.push_on_end)}</td><td class="n">${fmt(x.open_rate * 100)}%</td><td class="n">${fmt(cost(x), 0)}</td></tr>`;
    $("cmp").innerHTML = `<thead><tr><th>Policy</th><th>Rule</th><th class="n">Pushes / day</th><th class="n">Extra active days</th><th class="n">Push on, day ${days}</th><th class="n">Open rate</th><th class="n">Pushes per extra day</th></tr></thead><tbody>` +
      row("Today's default", sq) + row("Best volume-first", bv) + row("Recommended", rc, true) + "</tbody>";
    const pts = Math.round((rc.push_on_end - bv.push_on_end) * 100);
    const tiedBv = Math.abs(rc.incremental_active_days - bv.incremental_active_days) <= rc.ci95 + bv.ci95;
    $("mech-note").innerHTML = `The best volume-first policy already cuts volume to ${fmt(bv.sends_per_user_day, 2)} a day. The recommended policy sends ${rc.sends_per_user_day < bv.sends_per_user_day ? "less still" : "about the same"} (${fmt(rc.sends_per_user_day, 2)}) and ${tiedBv ? "matches its lift" : "beats it on lift"}, while keeping <b>${pts > 0 ? pts + " more people in 100" : "the same share"}</b> reachable at day ${days}. That difference is the fatigue-aware rule itself, not the lower volume.`;

    // all personas
    const cols = ["status_quo", "recommended"];
    $("allp").innerHTML = `<thead><tr><th>Persona</th><th>Policy</th><th class="n">Pushes / day</th><th class="n">Extra active days</th><th class="n">Push on, day 30</th><th class="n">Push on, day ${days}</th><th class="n">Reach days</th><th class="n">Open rate</th><th class="n">DND days</th></tr></thead><tbody>` +
      Object.keys(D.recs).map((pk) => cols.map((ck, i) => {
        const x = D.recs[pk].validation[ck], rd = reach(D.cohort[pk][ck].push_on);
        return `<tr class="${pk === S.persona ? "cur" : ""} ${ck === "recommended" ? "hl" : ""}"><td>${i === 0 ? `<b>${PN[pk]}</b>` : ""}</td><td><span class="dot ${ck === "recommended" ? "rec" : "sq"}"></span> ${ck === "recommended" ? "Recommended" : "Today's default"}</td><td class="n">${fmt(x.sends_per_user_day, 2)}</td><td class="n">+${fmt(x.incremental_active_days)}</td><td class="n">${pct(x.push_on_day30)}</td><td class="n">${pct(x.push_on_end)}</td><td class="n">${fmt(rd, 0)}</td><td class="n">${fmt(x.open_rate * 100)}%</td><td class="n">${fmt(x.dnd_days_per_user, 1)}</td></tr>`;
      }).join("")).join("") + "</tbody>";
  }
  function drawCumulative() {
    const C = D.cohort[S.persona], a = cum(C.status_quo.incremental_dau), b = cum(C.recommended.incremental_dau);
    const v = D.recs[S.persona].validation, sq = v.status_quo, rc = v.recommended;
    const tied = Math.abs(rc.incremental_active_days - sq.incremental_active_days) <= rc.ci95 + sq.ci95;
    const ahead = b[b.length - 1] > a[a.length - 1];
    let cross = 0;
    for (let i = 0; i < a.length; i++) if (b[i] <= a[i]) cross = i + 1;
    const fewer = Math.round((1 - rc.sends_per_user_day / sq.sends_per_user_day) * 100);
    $("cum-note").textContent = tied ? `The two policies finish within the same interval (+${fmt(sq.incremental_active_days)} vs +${fmt(rc.incremental_active_days)}). The recommended one gets there with ${fewer}% fewer pushes and more people still reachable.`
      : !ahead ? "Today's default finishes ahead on lift over this horizon."
      : cross === 0 ? "The recommended policy is ahead from day one."
      : `Today's default is ahead for the first ${cross} days, then the lost permission catches up with it. Recommended is ahead from day ${cross + 1} and the gap keeps widening.`;
    lineChart("chart-cum", [{ data: a, color: css("--sq"), name: "Today's default" }, { data: b, color: css("--rec"), name: "Recommended" }],
      { lo: 0, hi: 1, nice: true, fmt: (v) => "+" + fmt(v, 0), unit: " extra active days", mark: !tied && cross > 0 && ahead ? cross + 1 : 0 });
  }
  function drawHeat() {
    const R = D.recs[S.persona], caps = D.meta.grid.caps, ths = D.meta.grid.thresholds, rp = R.recommended_policy;
    const W = 520, H = 240, ml = 74, mt = 30, mr = 10, mb = 44, iw = W - ml - mr, ih = H - mt - mb;
    const rows = [...ths.map((t) => ({ key: "fa", t })), { key: "vf" }];
    const cw = iw / caps.length, ch = ih / rows.length;
    const cell = (c, r) => R.grid.find((g) => g.cap === c && (r.key === "vf" ? g.kind === "volume_first" : g.kind === "fatigue_aware" && g.threshold === r.t));
    let lo = Infinity, hi = -Infinity;
    rows.forEach((r) => caps.forEach((c) => { const g = cell(c, r); lo = Math.min(lo, g.incremental_active_days); hi = Math.max(hi, g.incremental_active_days); }));
    const ink = css("--ink"), muted = css("--muted"), rec = css("--rec"), surf = css("--surface");
    let s = `<text x="${ml + iw / 2}" y="14" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${muted}">EXTRA ACTIVE DAYS · DARKER = MORE · OUTLINED = CHOSEN</text>`;
    rows.forEach((r, j) => {
      const y = mt + j * ch;
      s += `<text x="${ml - 8}" y="${y + ch / 2 + 4}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="11" fill="${muted}">${r.key === "vf" ? "vol-first" : "bar " + r.t}</text>`;
      caps.forEach((c, i) => {
        const g = cell(c, r), x = ml + i * cw, k = (g.incremental_active_days - lo) / (hi - lo || 1), op = 0.08 + 0.92 * k;
        const chosen = r.key === "fa" && c === rp.cap && r.t === rp.threshold, sqc = r.key === "vf" && c === D.meta.status_quo.cap;
        const t = `<b>${r.key === "vf" ? "Volume-first" : "Fatigue-aware, bar " + r.t}, cap ${c}</b><br>+${fmt(g.incremental_active_days)} ± ${fmt(g.ci95)} extra active days<br>${pct(g.push_on_end)} push on at day 180 · ${fmt(g.sends_per_user_day, 2)} pushes/day`;
        s += `<rect x="${x + 1}" y="${y + 1}" width="${cw - 2}" height="${ch - 2}" rx="3" fill="${rec}" fill-opacity="${op.toFixed(2)}" stroke="${chosen ? ink : sqc ? css("--sq") : "none"}" stroke-width="${chosen ? 2.5 : 1.5}" ${sqc && !chosen ? 'stroke-dasharray="3 2"' : ""} data-tip="${esc(t)}"/>`;
        s += `<text x="${x + cw / 2}" y="${y + ch / 2 + 4}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="11" font-weight="${chosen ? 600 : 400}" fill="${k > 0.55 ? surf : ink}" pointer-events="none">${fmt(g.incremental_active_days)}</text>`;
      });
    });
    caps.forEach((c, i) => { s += `<text x="${ml + i * cw + cw / 2}" y="${H - 22}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="12" fill="${c === rp.cap ? ink : muted}" font-weight="${c === rp.cap ? 600 : 400}">${c}</text>`; });
    s += `<text x="${ml + iw / 2}" y="${H - 5}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${muted}">DAILY CAP · DASHED = TODAY'S DEFAULT</text>`;
    $("chart-heat").innerHTML = s;
    const best = R.grid.filter((g) => g.kind === "fatigue_aware").sort((a, b) => b.incremental_active_days - a.incremental_active_days)[0];
    const chosenG = cell(rp.cap, { key: "fa", t: rp.threshold });
    $("heat-note").textContent = best.cap === rp.cap && best.threshold === rp.threshold
      ? `Cap ${rp.cap} with bar ${rp.threshold} has the best lift outright.`
      : `Cap ${best.cap} with bar ${best.threshold} has the highest mean lift (+${fmt(best.incremental_active_days)}), but it is within the interval of cap ${rp.cap}, bar ${rp.threshold} (+${fmt(chosenG.incremental_active_days)}), which keeps ${Math.round((chosenG.push_on_end - best.push_on_end) * 100)} more people in 100 reachable. Ties break toward reach.`;
  }

  /* ---------- Six months: day 30 vs day 180 ---------- */
  function renderLongrun() {
    const v = D.recs[S.persona].validation, sq = v.status_quo, rc = v.recommended, days = D.meta.horizon_days;
    const C = D.cohort[S.persona];
    const row = (name, x, c, cls) => `<tr><td><span class="dot ${cls}"></span> ${name}</td><td class="n">${pct(x.push_on_day30)}</td><td class="n">${pct(x.push_on_end)}</td><td class="n">${Math.round((x.push_on_day30 - x.push_on_end) * 100)} pts</td><td class="n">${fmt(reach(c.push_on), 0)}</td></tr>`;
    $("d30").innerHTML = `<thead><tr><th>Policy</th><th class="n">Push on, day 30</th><th class="n">Push on, day ${days}</th><th class="n">Lost after month 1</th><th class="n">Reach days</th></tr></thead><tbody>` + row("Today's default", sq, C.status_quo, "sq") + row("Recommended", rc, C.recommended, "rec") + "</tbody>";
    const lostSq = Math.round((sq.push_on_day30 - sq.push_on_end) * 100), lostRc = Math.round((rc.push_on_day30 - rc.push_on_end) * 100);
    $("d30-note").innerHTML = `A 30-day test would show today's default keeping <b>${pct(sq.push_on_day30)}</b> of people reachable, against <b>${pct(rc.push_on_day30)}</b> for the recommended policy: a gap of ${Math.round((rc.push_on_day30 - sq.push_on_day30) * 100)} points. By day ${days} the gap is <b>${Math.round((rc.push_on_end - sq.push_on_end) * 100)} points</b>, because the default loses another ${lostSq} points of permission after the first month and the recommended policy loses ${lostRc}.`;
  }

  /* ---------- Volume recommendation ---------- */
  function bestByCap(grid, kind) {
    const m = {};
    grid.filter((g) => g.kind === kind).forEach((g) => {
      if (!m[g.cap] || g.incremental_active_days > m[g.cap].incremental_active_days) m[g.cap] = g;
    });
    return Object.values(m).sort((a, b) => a.cap - b.cap);
  }
  function renderVolume() {
    const R = D.recs[S.persona], rp = R.recommended_policy, days = D.meta.horizon_days;
    const tied = R.tied_caps.length > 1 ? `Ceilings ${R.tied_caps.join(", ")} are statistically tied on lift; the one shown keeps the most people reachable.` : "No other cap comes within the 95% interval.";
    $("vol-sub").textContent = `Each bar is ${D.meta.users_per_config.toLocaleString("en-US")} simulated people over ${days} days. The fatigue-aware bars use the best relevance bar found for that cap (searched ${D.meta.grid.thresholds.join(", ")}).`;
    const avg = R.validation.recommended.sends_per_user_day;
    const others = Object.keys(D.recs).map((k) => `${({ minimalist: "Minimalist", casual: "Casual", contributor: "Contributor" }[k] || k)} ~${fmt(D.recs[k].validation.recommended.sends_per_user_day)}`).join(" · ");
    $("rec-card").innerHTML = `<div class="k">Recommended for this persona</div>
      <div class="big">~${fmt(avg)} / day</div>
      <p>On average, with a hard ceiling of <b>${rp.cap}</b>. Send only pushes whose relevance, after the fatigue cost, clears <b>${rp.threshold}</b>. ${tied}</p>
      <p style="margin-top:8px;border-top:1px solid var(--rule);padding-top:8px">By persona: ${esc(others)} a day</p>`;
    const v = R.validation;
    const rows = [["Today's default", v.status_quo, false], ["Best volume-first", v.best_volume_first, false], ["Recommended", v.recommended, true]];
    $("valid").innerHTML = `<table><thead><tr><th>Validation cohort (fresh seed)</th><th>Policy</th><th class="n">Extra active days</th><th class="n">Push on, day ${days}</th><th class="n">Pushes / day</th><th class="n">Open rate</th><th class="n">DND days</th></tr></thead><tbody>` +
      rows.map(([name, r, hl]) => `<tr class="${hl ? "hl" : ""}"><td>${name}</td><td>${esc(r.policy)}</td><td class="n">+${fmt(r.incremental_active_days)} ± ${fmt(r.ci95)}</td><td class="n">${pct(r.push_on_end)}</td><td class="n">${fmt(r.sends_per_user_day, 2)}</td><td class="n">${fmt(r.open_rate * 100)}%</td><td class="n">${fmt(r.dnd_days_per_user)}</td></tr>`).join("") +
      `</tbody></table>`;
  }
  function drawVolume() {
    const R = D.recs[S.persona], fa = bestByCap(R.grid, "fatigue_aware"), vf = bestByCap(R.grid, "volume_first");
    const W = 860, H = 300, ml = 56, mr = 12, mt = 16, mb = 42, iw = W - ml - mr, ih = H - mt - mb;
    let hi = 1; [...fa, ...vf].forEach((g) => (hi = Math.max(hi, g.incremental_active_days + g.ci95)));
    hi = niceMax(hi);
    const Y = (x) => mt + ih - (x / hi) * ih;
    const ink = css("--ink"), muted = css("--muted"), rule = css("--rule"), cRec = css("--rec"), cSq = css("--sq"), wash = css("--surface-2");
    const n = fa.length, gw = iw / n, bw = Math.min(30, gw * 0.3);
    let s = "";
    for (let t = 0; t <= 4; t++) {
      const val = (hi * t) / 4, y = Y(val);
      s += `<line x1="${ml}" x2="${W - mr}" y1="${y}" y2="${y}" stroke="${rule}" stroke-width="1" fill="none"/>`;
      s += `<text x="${ml - 8}" y="${y + 4}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="11" fill="${muted}">${fmt(val, 0)}</text>`;
    }
    s += `<text x="14" y="${mt + ih / 2}" transform="rotate(-90 14 ${mt + ih / 2})" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${muted}">EXTRA ACTIVE DAYS / USER</text>`;
    fa.forEach((g, i) => {
      const cx = ml + gw * i + gw / 2, v = vf[i];
      if (g.cap === R.recommended_policy.cap) s += `<rect x="${ml + gw * i + 4}" y="${mt}" width="${gw - 8}" height="${ih}" fill="${wash}" stroke="none"/>`;
      [[v, cSq, cx - bw - 2], [g, cRec, cx + 2]].forEach(([d, col, x]) => {
        const y = Y(Math.max(0, d.incremental_active_days));
        const tt = `<b>${d.kind === "volume_first" ? "Volume-first" : "Fatigue-aware, bar " + d.threshold}, cap ${d.cap}</b><br>+${fmt(d.incremental_active_days)} ± ${fmt(d.ci95)} extra active days<br>${pct(d.push_on_end)} push on at day 180 · ${fmt(d.sends_per_user_day, 2)} pushes/day`;
        s += `<rect x="${x}" y="${y}" width="${bw}" height="${Y(0) - y}" fill="${col}" stroke="none" rx="2" data-tip="${esc(tt)}"/>`;
        const y1 = Y(Math.max(0, d.incremental_active_days - d.ci95)), y2 = Y(d.incremental_active_days + d.ci95);
        s += `<line x1="${x + bw / 2}" x2="${x + bw / 2}" y1="${y1}" y2="${y2}" stroke="${ink}" stroke-width="1.5" fill="none"/>`;
      });
      s += `<text x="${cx}" y="${Y(g.incremental_active_days + g.ci95) - 6}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="11" fill="${cRec}">${fmt(g.incremental_active_days)}</text>`;
      s += `<text x="${cx}" y="${H - 22}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="12" font-weight="${g.cap === R.recommended_policy.cap ? 600 : 400}" fill="${g.cap === R.recommended_policy.cap ? ink : muted}">${g.cap}</text>`;
    });
    s += `<text x="${ml + iw / 2}" y="${H - 4}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${muted}">DAILY CAP (MAX PUSHES PER DAY) · SHADED = RECOMMENDED</text>`;
    $("chart-volume").innerHTML = s;
  }

  /* ---------- Content mix ---------- */
  const RULE_TEXT = { send: "Core: always eligible", optional: "Only when it clears the bar", rare: "Effectively off", drop: "Drop" };
  function renderMix() {
    const R = D.recs[S.persona], rec = R.content_mix, sq = R.content_mix_status_quo;
    let maxShare = 0.01; [...rec, ...sq].forEach((m) => (maxShare = Math.max(maxShare, m.share_of_sends)));
    const bar = (cls, x) => `<span class="${cls}"><i style="width:${Math.max(2, (x / maxShare) * 110)}px"></i>${pct(x)}</span>`;
    $("mix").innerHTML = `<thead><tr><th>Notification type</th><th>Share of pushes · default vs recommended</th><th class="n">Per person per day · rec.</th><th class="n">Open rate · default</th><th class="n">Open rate · recommended</th><th class="n">If switched off</th><th>Rule</th></tr></thead><tbody>` +
      rec.map((m, i) => {
        const s = sq[i];
        const delta = m.delta_if_removed;
        return `<tr><td>${esc(m.label)}</td><td><div class="bars">${bar("s", s.share_of_sends)}${bar("r", m.share_of_sends)}</div></td>
          <td class="n">${fmt(m.sends_per_user_day, 2)}</td><td class="n">${fmt(s.open_rate * 100)}%</td><td class="n">${fmt(m.open_rate * 100)}%</td>
          <td class="n">${delta >= 0 ? "+" : ""}${fmt(delta, 2)} ± ${fmt(m.ci95, 2)} days</td>
          <td><span class="rule ${m.rule}">${RULE_TEXT[m.rule]}</span></td></tr>`;
      }).join("") + `</tbody>`;
    const isReply = (m) => ["reply_post", "reply_comment", "milestone"].includes(m.type);
    const share = (arr) => arr.filter(isReply).reduce((a, m) => a + m.share_of_sends, 0);
    const sqTop = [...sq].sort((a, b) => b.share_of_sends - a.share_of_sends)[0];
    const rare = rec.filter((m) => m.rule === "rare").map((m) => m.label.toLowerCase());
    const drop = rec.filter((m) => m.rule === "drop").map((m) => m.label.toLowerCase());
    $("mix-note").innerHTML = `Under today's default, <b>${esc(sqTop.label.toLowerCase())}</b> is the largest type at ${pct(sqTop.share_of_sends)} of pushes. ` +
      `Pushes about the person's own posts and comments go from <b>${pct(share(sq))}</b> to <b>${pct(share(rec))}</b> of what gets sent. ` +
      (drop.length ? `Switching off ${esc(drop.join(", "))} improves results, so the recommended policy drops it. ` : `Once the relevance bar filters out weak candidates, every remaining type still earns its slot. `) +
      (rare.length ? `${esc(rare.join(", ").replace(/^./, (c) => c.toUpperCase()))} almost never clears the bar.` : "");
  }

  /* ---------- 180-day curves ---------- */
  function lineChart(id, series, opt) {
    const W = 520, H = 240, ml = 44, mr = 10, mt = 12, mb = 30, iw = W - ml - mr, ih = H - mt - mb;
    const n = series[0].data.length;
    let lo = opt.lo, hi = opt.hi;
    series.forEach((s) => s.data.forEach((v) => { if (v > hi) hi = v; if (v < lo) lo = v; }));
    if (opt.nice) hi = niceMax(hi);
    const X = (i) => ml + (i / (n - 1)) * iw, Y = (v) => mt + ih - ((v - lo) / (hi - lo || 1)) * ih;
    const muted = css("--muted"), rule = css("--rule");
    let s = "";
    for (let t = 0; t <= 4; t++) {
      const val = lo + ((hi - lo) * t) / 4, y = Y(val);
      s += `<line x1="${ml}" x2="${W - mr}" y1="${y}" y2="${y}" stroke="${rule}" stroke-width="1" fill="none"/>`;
      s += `<text x="${ml - 7}" y="${y + 4}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${muted}">${opt.fmt(val)}</text>`;
    }
    [1, 30, 60, 90, 120, 150, 180].filter((d) => d <= n).forEach((d) => {
      s += `<text x="${X(d - 1)}" y="${H - 10}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${muted}">${d}</text>`;
    });
    if (opt.mark) {
      const x = X(opt.mark - 1);
      s += `<line x1="${x}" x2="${x}" y1="${mt}" y2="${mt + ih}" stroke="${muted}" stroke-width="1" stroke-dasharray="3 3"/>`;
      s += `<text x="${x + 5}" y="${mt + 11}" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${muted}">day ${opt.mark}</text>`;
    }
    const sms = series.map((sr) => smooth(sr.data, opt.smooth || 0));
    series.forEach((sr, k) => {
      const sm = sms[k];
      const p = sm.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1)).join(" ");
      s += `<path d="${p}" fill="none" stroke="${sr.color}" stroke-width="2.25" stroke-linejoin="round"/>`;
      s += `<circle cx="${X(n - 1)}" cy="${Y(sm[n - 1])}" r="3.5" fill="${sr.color}" stroke="${css("--surface")}" stroke-width="1.5"/>`;
      s += `<text x="${X(n - 1) - 6}" y="${Y(sm[n - 1]) - 8 + (k ? 0 : (Math.abs(Y(sms[0][n - 1]) - Y(sms[1] ? sms[1][n - 1] : -99)) < 14 ? -12 : 0))}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="11" font-weight="600" fill="${sr.color}">${opt.fmt(sm[n - 1])}</text>`;
    });
    // hover: one invisible column per day, each carrying its own tooltip
    const cw = iw / (n - 1);
    for (let i = 0; i < n; i++) {
      const t = `<b>Day ${i + 1}</b>` + series.map((sr, k) => `<br><i style="background:${sr.color}"></i>${sr.name || ""} ${opt.fmt(sms[k][i])}${opt.unit || ""}`).join("");
      s += `<rect class="hov" x="${X(i) - cw / 2}" y="${mt}" width="${cw}" height="${ih}" fill="transparent" data-tip="${esc(t)}"/>`;
    }
    s += `<line id="${id}-x" x1="0" x2="0" y1="${mt}" y2="${mt + ih}" stroke="${muted}" stroke-width="1" opacity="0"/>`;
    $(id).innerHTML = s;
    const xl = $(id + "-x");
    $(id).addEventListener("mousemove", (e) => {
      const r = e.target.closest(".hov"); if (!r) { xl.setAttribute("opacity", 0); return; }
      const cx = +r.getAttribute("x") + cw / 2; xl.setAttribute("x1", cx); xl.setAttribute("x2", cx); xl.setAttribute("opacity", 0.8);
    });
    $(id).addEventListener("mouseleave", () => xl.setAttribute("opacity", 0));
  }
  function renderCharts() {
    if (!D) return;
    drawVolume(); drawCumulative(); drawHeat();
    const C = D.cohort[S.persona], cSq = css("--sq"), cRec = css("--rec");
    lineChart("chart-perm", [{ data: C.status_quo.push_on, color: cSq, name: "Today's default" }, { data: C.recommended.push_on, color: cRec, name: "Recommended" }],
      { lo: 0, hi: 1, fmt: (v) => Math.round(v * 100) + "%", unit: " push on" });
    lineChart("chart-dau", [{ data: C.status_quo.incremental_dau, color: cSq, name: "Today's default" }, { data: C.recommended.incremental_dau, color: cRec, name: "Recommended" }],
      { lo: 0, hi: 1, nice: true, smooth: 3, fmt: (v) => "+" + fmt(v) + "pp", unit: " of users active who otherwise would not be" });
  }

  /* ---------- data files ---------- */
  function renderData() {
    const files = [
      ["events_sample.csv", "One row per push: persona, policy, person, day, time, type, relevance, outcome, fatigue"],
      ["recommendations.json", "Optimiser grid, chosen policy, content ablation, validation"],
      ["lived.json", "The two representative months shown above, push by push"],
      ["cohort.json", "180-day permission and lift curves"],
      ["meta.json", "Personas, notification types and run parameters"],
    ];
    $("data-list").innerHTML = files.map(([f, d]) => `<a href="data/${f}"><b>${f}</b><span>${d}</span></a>`).join("");
  }

  function smooth(a, w) {
    if (!w) return a;
    return a.map((_, i) => { let s = 0, n = 0; for (let j = Math.max(0, i - w); j <= Math.min(a.length - 1, i + w); j++) { s += a[j]; n++; } return s / n; });
  }
  function niceMax(x) {
    const p = Math.pow(10, Math.floor(Math.log10(x))), m = x / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  }
})();
