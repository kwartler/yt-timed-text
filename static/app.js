// YT Timed Text frontend

// -------- Quit button --------
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("quitBtn").addEventListener("click", async () => {
    if (!confirm("Stop the server and close the app?")) return;
    try {
      await fetch("/api/shutdown", { method: "POST" });
    } catch (_) { /* server already gone */ }
    document.body.innerHTML = "<div style='padding:40px;font-family:sans-serif;color:#8a93a3'>Server stopped. You can close this tab.</div>";
  });
});

const $ = (s) => document.querySelector(s);
const statusEl = $("#status");

function setStatus(msg, isError = false) {
  statusEl.textContent = msg || "";
  statusEl.classList.toggle("error", !!isError);
}

function fmtDuration(secs) {
  if (!secs && secs !== 0) return "";
  secs = Math.floor(secs);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
           : `${m}:${String(s).padStart(2, "0")}`;
}

function showOnly(id) {
  for (const v of ["#videoView", "#channelView"]) {
    $(v).classList.toggle("hidden", v !== "#" + id);
  }
}

// -------- Submit --------
$("#urlForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("#urlInput").value.trim();
  if (!url) return;
  setStatus("Resolving...");
  $("#goBtn").disabled = true;
  try {
    const r = await fetch("/api/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Resolve failed");

    if (data.type === "video") {
      await showVideo(data);
    } else {
      await showChannel(data);
    }
    setStatus("");
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    $("#goBtn").disabled = false;
  }
});

// -------- Video view --------
async function showVideo(v) {
  $("#vTitle").textContent = v.title;
  $("#vMeta").textContent = [v.channel, fmtDuration(v.duration)].filter(Boolean).join(" • ");
  $("#vThumb").src = v.thumbnail || `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`;
  showOnly("videoView");

  // Populate languages
  const langSel = $("#vLang");
  langSel.innerHTML = `<option>Loading...</option>`;
  try {
    const r = await fetch(`/api/captions/${v.id}/languages`);
    const data = await r.json();
    const opts = [];
    for (const m of data.manual || []) opts.push({ code: m.code, label: `${m.code} — ${m.name}` });
    for (const a of data.auto || []) opts.push({ code: a.code, label: `${a.code} — ${a.name} (auto)` });
    langSel.innerHTML = "";
    if (!opts.length) {
      langSel.innerHTML = `<option value="">No captions available</option>`;
      $("#vDownload").disabled = true;
    } else {
      for (const o of opts) {
        const opt = document.createElement("option");
        opt.value = o.code;
        opt.textContent = o.label;
        langSel.appendChild(opt);
      }
      // Default to 'en' or 'en-US' if present
      const pref = opts.find(o => o.code === "en") || opts.find(o => o.code.startsWith("en")) || opts[0];
      langSel.value = pref.code;
      $("#vDownload").disabled = false;
    }
  } catch (err) {
    langSel.innerHTML = `<option value="en">en</option>`;
  }

  $("#vDownload").onclick = () => {
    const lang = langSel.value || "en";
    window.location = `/api/captions/${v.id}?lang=${encodeURIComponent(lang)}`;
  };
}

// -------- Channel view --------
let channelRows = [];

async function showChannel(c) {
  channelRows = [];
  $("#cTitle").textContent = c.title || "Channel";
  $("#cMeta").textContent = "Loading videos...";
  $("#cBody").innerHTML = "";
  $("#cCount").textContent = "0 videos";
  $("#cDownload").disabled = true;
  showOnly("channelView");

  // Stream NDJSON
  const r = await fetch(`/api/channel/videos?url=${encodeURIComponent(c.url)}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let count = 0;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      let obj;
      try { obj = JSON.parse(line); } catch { continue; }
      if (obj._error) { setStatus(obj._error, true); continue; }
      channelRows.push(obj);
      appendRow(obj);
      count++;
      if (count % 25 === 0) $("#cCount").textContent = `${count} videos`;
    }
  }
  $("#cCount").textContent = `${channelRows.length} videos`;
  $("#cMeta").textContent = `${channelRows.length} videos`;
  updateSelectionCount();
}

function appendRow(v) {
  const tr = document.createElement("tr");
  tr.dataset.id = v.id;
  tr.dataset.title = (v.title || "").toLowerCase();
  tr.innerHTML = `
    <td><input type="checkbox" class="rowChk" data-id="${v.id}"></td>
    <td><a href="https://www.youtube.com/watch?v=${v.id}" target="_blank"><img class="thumb" loading="lazy" src="${v.thumbnail}" alt=""></a></td>
    <td>${escapeHtml(v.title)}</td>
    <td>${fmtDuration(v.duration)}</td>
  `;
  $("#cBody").appendChild(tr);
  tr.querySelector(".rowChk").addEventListener("change", updateSelectionCount);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function selectedIds() {
  return Array.from(document.querySelectorAll(".rowChk:checked")).map(c => c.dataset.id);
}

function updateSelectionCount() {
  const n = selectedIds().length;
  const btn = $("#cDownload");
  btn.textContent = `Download selected (${n})`;
  btn.disabled = n === 0;
}

$("#cAll").addEventListener("change", (e) => {
  const visibleRows = Array.from(document.querySelectorAll("#cBody tr")).filter(tr => tr.style.display !== "none");
  for (const tr of visibleRows) {
    const chk = tr.querySelector(".rowChk");
    chk.checked = e.target.checked;
  }
  updateSelectionCount();
});

$("#cFilter").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase().trim();
  for (const tr of document.querySelectorAll("#cBody tr")) {
    tr.style.display = !q || tr.dataset.title.includes(q) ? "" : "none";
  }
});

$("#cDownload").addEventListener("click", async () => {
  const ids = selectedIds();
  if (!ids.length) return;
  const lang = $("#cLang").value;
  setStatus(`Building ZIP for ${ids.length} videos... this can take a while.`);
  $("#cDownload").disabled = true;
  try {
    const r = await fetch("/api/captions/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_ids: ids, lang }),
    });
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(txt || "Batch failed");
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `captions_${Date.now()}.zip`;
    a.click();
    URL.revokeObjectURL(url);
    setStatus(`Downloaded ${ids.length} captions.`);
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    $("#cDownload").disabled = false;
    updateSelectionCount();
  }
});
