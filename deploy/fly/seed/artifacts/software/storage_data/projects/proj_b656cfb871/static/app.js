// Minimal dependency-free frontend over the generated API.
async function load() {
  const target = document.getElementById("items");
  try {
    const res = await fetch("/string_reversal_requests");
    const data = await res.json();
    const rows = Array.isArray(data) ? data : [data];
    target.innerHTML = rows.length
      ? rows.map((r) => `<li>${JSON.stringify(r)}</li>`).join("")
      : '<li class="muted">No records yet.</li>';
  } catch (err) {
    target.innerHTML = `<li class="muted">API unavailable: ${err}</li>`;
  }
}
load();
