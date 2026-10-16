const byId = (id) => document.getElementById(id);

function setList(id, values) {
  const element = byId(id);
  element.replaceChildren();
  const shown = values.length ? values : ["未从当前证据识别到明确条款"];
  for (const value of shown) {
    const item = document.createElement("li");
    item.textContent = value;
    element.appendChild(item);
  }
}

function scoreRow(label, value, className, scale = 1) {
  const safe = value == null ? 0 : Number(value);
  const percent = Math.max(0, Math.min(100, safe * scale * 100));
  return `<span>${label}</span><div class="bar"><span class="${className}" style="width:${percent}%"></span></div><span>${value == null ? "-" : safe.toFixed(3)}</span>`;
}

function renderCandidates(candidates) {
  const list = byId("candidateList");
  list.replaceChildren();
  if (!candidates.length) {
    list.innerHTML = '<div class="empty-state">没有满足条件的候选片段。</div>';
    return;
  }
  for (const candidate of candidates) {
    const item = document.createElement("article");
    item.className = "candidate";
    const rankChange = candidate.initial_rank === candidate.final_rank
      ? "排名未变"
      : `#${candidate.initial_rank} → #${candidate.final_rank}`;
    item.innerHTML = `
      <div class="candidate-head">
        <span class="rank">${candidate.final_rank}</span>
        <div class="candidate-title">${escapeHtml(candidate.title)}<div class="candidate-meta">${escapeHtml(candidate.section_path.join(" > "))} · ${escapeHtml(candidate.version)}</div></div>
        <span class="rank-change">${rankChange}</span>
      </div>
      <div class="candidate-text">${escapeHtml(candidate.text)}</div>
      <div class="score-grid">
        ${scoreRow("BM25", candidate.scores.bm25, "bar-bm25", 0.08)}
        ${scoreRow("Dense", candidate.scores.dense, "bar-dense")}
        ${scoreRow("RRF", candidate.scores.rrf, "bar-dense", 30)}
        ${scoreRow("Rerank", candidate.scores.rerank, "bar-rerank")}
      </div>`;
    list.appendChild(item);
  }
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
}

function renderAnswer(response) {
  byId("timing").textContent = `检索 ${response.retrieval_ms.toFixed(0)} ms · 生成 ${response.generation_ms.toFixed(0)} ms`;
  byId("modeBadge").textContent = `${response.requested_mode} → ${response.effective_mode}`;
  const notice = byId("degradation");
  if (response.degraded) {
    notice.textContent = response.degradation_reasons.join("；");
    notice.classList.remove("hidden");
  } else {
    notice.classList.add("hidden");
  }
  renderCandidates(response.candidates);
  if (!response.answer) return;
  byId("answerEmpty").classList.add("hidden");
  byId("answerContent").classList.remove("hidden");
  byId("policyExplanation").textContent = response.answer.policy_explanation + (response.answer.refusal_reason ? `\n${response.answer.refusal_reason}` : "");
  byId("timing").textContent += ` · ${response.answer.generator}`;
  setList("applicable", response.answer.applicable_conditions);
  setList("inapplicable", response.answer.inapplicable_conditions);
  setList("missing", response.answer.missing_information);
  const citations = byId("citations");
  citations.replaceChildren();
  for (const citation of response.answer.citations) {
    const item = document.createElement("li");
    const link = document.createElement(citation.synthetic ? "span" : "a");
    link.href = citation.source_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = `[${citation.citation_id}] ${citation.document} · ${citation.section} · ${citation.version} · 生效：${citation.effective_from || "未知"}${citation.effective_to ? ` 至 ${citation.effective_to}` : ""}${citation.synthetic ? " · 合成测试" : ""}`;
    item.appendChild(link);
    for (const url of (citation.additional_source_urls || [])) {
      if (url === citation.source_url) continue;
      const additional = document.createElement("a");
      additional.href = url;
      additional.target = "_blank";
      additional.rel = "noreferrer";
      additional.textContent = "补充来源";
      item.appendChild(document.createTextNode(" · "));
      item.appendChild(additional);
    }
    citations.appendChild(item);
  }
}

async function runQuery() {
  const button = byId("searchButton");
  button.disabled = true;
  button.querySelector("span").textContent = "检索中...";
  byId("answerContent").classList.add("hidden");
  byId("answerEmpty").classList.remove("hidden");
  byId("answerEmpty").textContent = "正在检索...";
  byId("degradation").classList.add("hidden");
  byId("candidateList").replaceChildren();
  byId("timing").textContent = "";
  byId("modeBadge").textContent = "";
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const platform = byId("platform").value || null;
  const productCategory = byId("category").value || null;
  const asOfDate = byId("asOfDate").value || null;
  const payload = {
    question: byId("question").value,
    mode,
    top_k: 5,
    filters: { platform, product_category: productCategory, as_of_date: asOfDate, version: byId("version").value || null },
    context: {
      platform, product_category: productCategory, as_of_date: asOfDate,
      model: byId("model").value || null,
      purchase_date: byId("purchaseDate").value || null,
      receipt_date: byId("receiptDate").value || null,
      request_type: byId("requestType").value || null,
      opened: triState("opened"), activated: triState("activated"), used: triState("used"),
    },
    generate: true,
  };
  try {
    const response = await fetch("/api/v1/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const detail = (await response.json()).detail;
      throw new Error(typeof detail === "string" ? detail : `输入校验失败 (HTTP ${response.status})`);
    }
    renderAnswer(await response.json());
  } catch (error) {
    const notice = byId("degradation");
    notice.textContent = `请求失败：${error.message}`;
    notice.classList.remove("hidden");
    byId("answerEmpty").textContent = "本次请求未取得回答";
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "检索并回答";
  }
}

function triState(id) {
  const value = byId(id).value;
  return value === "" ? null : value === "true";
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    const health = await response.json();
    byId("healthText").textContent = health.index_ready
      ? `索引 ${health.index_version} · ${health.details.chunk_strategy}`
      : "索引尚未构建";
    byId("statusBadge").classList.toggle("ok", health.status === "ok");
    byId("statusBadge").lastChild.textContent = health.status === "ok" ? "就绪" : "降级";
  } catch {
    byId("healthText").textContent = "无法连接服务";
  }
}

window.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();
  byId("searchButton").addEventListener("click", runQuery);
  checkHealth();
});
