(() => {
const BRIDGE_URL = "http://localhost:4611";
let currentMode = "live"; // 'live', 'sandbox', 'demo'

// ── Sandbox Isolation ────────────────────────────────────────────────────────
const SANDBOX_SESSION_ID = crypto.randomUUID().slice(0, 16);
let sandboxChatHistory = [];  // never written to producer memory
let sandboxProposals = [];    // AI proposals pending user approval

// ── Observability State ──────────────────────────────────────────────────────
let sessionStats = {
    actionsRun: 0,
    verified: 0,
    failed: 0,
    totalTimeMs: 0,
    totalTokens: 0,
    estimatedCostUsd: 0
};
let sessionLog = [];

// ── ACTION_REGISTRY (matched to conductor_bridge.py contracts) ───────────────
const ACTION_REGISTRY = [
    // Phase D Slice 1/2 Supported
    { id: "vol", group: "Mix", label: "Set Volume to -6dB", endpoint: "/action/track_volume", method: "POST", payload: { track: "Kick", volume: 0.5 }, supported: true },
    { id: "pan", group: "Mix", label: "Pan Center", endpoint: "/action/track_pan", method: "POST", payload: { track: "Kick", pan: 0.5 }, supported: true },
    { id: "mute", group: "Mix", label: "Mute Track", endpoint: "/action/track_mute", method: "POST", payload: { track: "Kick", mute: true }, supported: true },
    { id: "solo", group: "Mix", label: "Solo Track", endpoint: "/action/track_solo", method: "POST", payload: { track: "Kick", solo: true }, supported: true },

    // Expanded Slice 1
    { id: "create_track", group: "Track", label: "Create MIDI Track", endpoint: "/action/track_create", method: "POST", payload: { name: "New Synth", type: "midi" }, supported: true },
    { id: "del_track", group: "Roadmap", label: "Delete Track", endpoint: "/action/track_delete", method: "POST", payload: { track: "New Synth", confirm: true }, supported: false, future_reason: "Requires confirmation flow (destructive, no undo)" },
    { id: "dup_track", group: "Track", label: "Duplicate Track", endpoint: "/action/track_duplicate", method: "POST", payload: { track: "Kick" }, supported: true },
    { id: "ren_track", group: "Track", label: "Rename Track", endpoint: "/action/track_rename", method: "POST", payload: { track: "Kick", new_name: "Kick Main" }, supported: true },
    { id: "arm_track", group: "Track", label: "Arm Track", endpoint: "/action/track_arm", method: "POST", payload: { track: "Kick", arm: true }, supported: true },
    { id: "monitor_track", group: "Track", label: "Monitor Track (Auto)", endpoint: "/action/track_monitor", method: "POST", payload: { track: "Kick", mode: 1 }, supported: true },
    { id: "color_track", group: "Track", label: "Color Track", endpoint: "/action/track_color", method: "POST", payload: { track: "Kick", color: 60 }, supported: true },
    { id: "ret_track", group: "Track", label: "Create Return Track", endpoint: "/action/return_track_create", method: "POST", payload: {}, supported: true },
    { id: "multi_track", group: "Track", label: "Create Multiple Tracks", endpoint: "/action/tracks_create_multiple", method: "POST", payload: { count: 3, type: "audio" }, supported: true },

    // Expanded Slice 2
    { id: "route_track", group: "Mix", label: "Route to Master", endpoint: "/action/track_route", method: "POST", payload: { track: "Kick", routing: "Master", confirm: true }, supported: true },
    { id: "send_track", group: "Mix", label: "Send to Reverb", endpoint: "/action/track_send", method: "POST", payload: { track: "Kick", send: 0, value: 0.5 }, supported: true },
    { id: "play", group: "Transport", label: "Play", endpoint: "/action/transport_play", method: "POST", payload: {}, supported: true },
    { id: "stop", group: "Transport", label: "Stop", endpoint: "/action/transport_stop", method: "POST", payload: {}, supported: true },
    { id: "record", group: "Roadmap", label: "Record", endpoint: "/action/transport_record", method: "POST", payload: { record: true, confirm: true }, supported: false, future_reason: "Requires confirmation flow (destructive, no undo)" },
    { id: "loop", group: "Transport", label: "Loop", endpoint: "/action/transport_loop", method: "POST", payload: { loop: true }, supported: true },
    { id: "metronome", group: "Transport", label: "Metronome", endpoint: "/action/transport_metronome", method: "POST", payload: { metronome: true }, supported: true },

    // Expanded Slice 3A
    { id: "bypass", group: "Plugin", label: "Bypass Plugin", endpoint: "/action/plugin_bypass", method: "POST", payload: { track: "Kick", device_name: "Pro-Q 4", bypass: true }, supported: true },

    // Future / Unsupported
    { id: "export", group: "Roadmap", label: "Bounce Master", endpoint: "/action/export", method: "POST", payload: {}, supported: false, future_reason: "Pending Phase D Slice 8" },
    { id: "plugin_tweak", group: "Roadmap", label: "Tweak Pro-Q EQ", endpoint: "/action/plugin_param", method: "POST", payload: {}, supported: false, future_reason: "Pending PluginBridge UI" },
    { id: "plugin_load", group: "Roadmap", label: "Load Plugin", endpoint: "/action/plugin_load", method: "POST", payload: {}, supported: false, future_reason: "Not built yet" },
    { id: "clip_action", group: "Roadmap", label: "Edit MIDI Clip", endpoint: "/action/clip_edit", method: "POST", payload: {}, supported: false, future_reason: "Not built yet" }
];

// ── CoProducer Reply Composer ────────────────────────────────────────────────
// Policy: backend controls facts (ok, error_code, verification_status,
//         before_state/after_state). This layer controls wording only.
// Rules:  calm, brief, studio-assistant tone. No endpoint names. No proof IDs.
//         No raw error codes. No token/model metadata. No "locked"/"capability"
//         permission-system language. Ask one question when info is missing.
function composeReply(action, response) {
    // Pull track name from structured state — never parse error strings.
    const target =
        (response.after_state  && response.after_state.track_name)  ||
        (response.before_state && response.before_state.track_name) ||
        null;

    if (!response.ok) {
        const ec = response.error_code || "";
        switch (ec) {
            case "UNDO_DRIFT_DETECTED":
                return "Ableton changed since that move — skipping the undo to stay safe.";
            case "BRIDGE_PLUGIN_ABSENT":
                return target
                    ? `Couldn’t find that plugin on ${target}.`
                    : "Couldn’t find that plugin on the track.";
            case "BRIDGE_PARAM_OUT_OF_RANGE":
                return "That value is out of range for this control.";
            case "BRIDGE_TRACK_ABSENT":
                return "Can’t find that track — check the name?";
            case "SECURITY_CONFIRMATION_REQUIRED":
                return "That needs a quick confirmation before I touch it.";
            case "SECURITY_CLARIFY_REQUIRED":
                return "I need one more detail before I can do that safely.";
            case "NEVER_DO_BLOCKED":
                return "Your safety rules are blocking that.";
            case "ABLETON_DISCONNECTED":
                return "Ableton doesn’t seem to be connected — is Live running?";
            default:
                return "That didn’t go through — something stopped it.";
        }
    }

    const vs = response.verification_status || "";
    if (vs === "VERIFIED")
        return target
            ? `Done — ${target} updated and confirmed.`
            : "Done — confirmed in Ableton.";
    if (vs === "ALREADY_CORRECT")
        return target
            ? `${target} was already set that way.`
            : "Already set that way.";
    // Applied but readback didn’t confirm (UNVERIFIED or missing)
    return target
        ? `Applied to ${target} — couldn’t read it back.`
        : "Sent to Ableton — couldn’t read it back.";
}

function translateStatus(response) {
    if (!response.ok) return "Failed";
    if (response.verification_status === "VERIFIED") return "Confirmed";
    if (response.verification_status === "ALREADY_CORRECT") return "Already Correct";
    return "Unverified";
}

// ── UI Elements ──────────────────────────────────────────────────────────────
const actionContainer = document.getElementById("advanced-action-buttons-container");
const timelineContainer = document.getElementById("timeline-container");
const statusDisplay = document.getElementById("status-display");
const coproducerBox = document.getElementById("coproducer-response");
const modeSelect = document.getElementById("harness-mode-select");
const resetBtn = document.getElementById("reset-session-btn");
const advancedClearBtn = document.getElementById("advancedClearBtn");

// ── Initialization ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    if (actionContainer) renderActionButtons();

    if (modeSelect) {
        modeSelect.addEventListener("change", (e) => {
            currentMode = e.target.value;
            const labels = { "live": "Live Mode", "sandbox": "AI Sandbox Mode", "demo": "Demo / Mock Mode" };
            setStatus(`Mode: ${labels[currentMode]}`, "idle");
            updateChatVisibility();
            if (currentMode === "sandbox") {
                showCoProducerResponse("AI Sandbox active. Type a command below. Nothing runs until you approve it.", false, false);
            }
        });
    }

    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
            if (currentMode === "sandbox") resetSandbox();
            else resetMainUI();
        });
    }
    if (advancedClearBtn) {
        advancedClearBtn.addEventListener("click", () => {
            if (currentMode === "sandbox") resetSandbox();
            else resetMainUI();
        });
    }

    // Export button
    if ((advancedClearBtn || resetBtn) && !document.getElementById("export-report-btn")) {
        const exportBtn = document.createElement("button");
        exportBtn.id = "export-report-btn";
        exportBtn.textContent = "Export Report";
        exportBtn.style.cssText = "background:var(--surface-2); border:1px solid var(--border-subtle); color:var(--text-primary); border-radius:7px; padding:5px 8px; font-size:11px; cursor:pointer;";
        exportBtn.addEventListener("click", exportSessionReport);
        if (advancedClearBtn) advancedClearBtn.parentNode.insertBefore(exportBtn, advancedClearBtn.nextSibling);
        else resetBtn.parentNode.insertBefore(exportBtn, resetBtn.nextSibling);
    }

    // Wire both chat surfaces. The old prototype fake chat handler is bypassed.
    const submitInputs = [
        document.getElementById("chatInput"),
        document.getElementById("floatChatInput")
    ].filter(Boolean);
    submitInputs.forEach((input) => {
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSandboxChat(input);
            }
        });
    });
    const sendBtn = document.getElementById("sendBtn");
    const floatSendBtn = document.getElementById("floatSendBtn");
    if (sendBtn) sendBtn.addEventListener("click", () => handleSandboxChat(document.getElementById("chatInput")));
    if (floatSendBtn) floatSendBtn.addEventListener("click", () => handleSandboxChat(document.getElementById("floatChatInput")));

    updateSessionTotals();
    updateChatVisibility();
});

function updateChatVisibility() {
    const chatArea = document.getElementById("chatArea");
    const chatToolbar = document.querySelector(".chat-toolbar");
    if (currentMode === "sandbox") {
        if (chatArea) chatArea.style.display = "flex";
        if (chatToolbar) chatToolbar.style.display = "none";
    } else {
        if (chatArea) chatArea.style.display = "none";
        if (chatToolbar) chatToolbar.style.display = "none";
    }
}

// ── Sandbox Reset ────────────────────────────────────────────────────────────
function resetSandbox() {
    sandboxChatHistory = [];
    sandboxProposals = [];
    const messages = document.getElementById("messages");
    if (messages) {
        messages.innerHTML = '<div class="msg-wrap"><div class="msg assistant">AI Sandbox reset. Chat history and proposals cleared. Backend logs are preserved.</div></div>';
    }
    sessionStats = { actionsRun: 0, verified: 0, failed: 0, totalTimeMs: 0, totalTokens: 0, estimatedCostUsd: 0 };
    sessionLog = [];
    if (timelineContainer) {
        timelineContainer.innerHTML = '<div class="timeline-empty" style="font-size: 11px; color: var(--text-tertiary); text-align: center; padding: 20px;">Timeline is empty. Execute an action to begin.</div>';
    }
    if (coproducerBox) coproducerBox.classList.add("hidden");
    updateSessionTotals();
    setStatus("Sandbox reset. Logs preserved.", "idle");
}

function resetMainUI() {
    if (timelineContainer) {
        timelineContainer.innerHTML = '<div class="timeline-empty" style="font-size: 11px; color: var(--text-tertiary); text-align: center; padding: 20px;">Timeline is empty. Execute an action to begin.</div>';
    }
    if (coproducerBox) coproducerBox.classList.add("hidden");
    sessionStats = { actionsRun: 0, verified: 0, failed: 0, totalTimeMs: 0, totalTokens: 0, estimatedCostUsd: 0 };
    sessionLog = [];
    updateSessionTotals();
    setStatus("UI Reset. Logs preserved.", "idle");
}

// ── Chat Handler ──────────────────────────────────────────────────
function showParserStatus(text) {
    setStatus(text, text === "Calling AI parser" ? "requesting" : "idle");
    const floatStatus = document.getElementById("floatHarnessStatus");
    if (floatStatus) floatStatus.textContent = text;
    if (typeof window.setNotchState === "function") {
        if (text === "Calling AI parser") window.setNotchState("thinking");
        if (text === "Parser returned") window.setNotchState("default");
    }
}

function addFloatHarnessMessage(content, role) {
    const messages = document.getElementById("floatMessages");
    if (!messages) return;
    if (role === "assistant") removeFloatThinkingMessage();
    const msg = document.createElement("div");
    msg.className = role === "user" ? "fc-user-msg" : "fc-ai-msg";
    if (typeof content === "string") msg.textContent = content;
    else msg.appendChild(content);
    messages.appendChild(msg);
    messages.scrollTop = messages.scrollHeight;
    return msg;
}

function showFloatThinkingMessage(label = "Conductor is thinking...") {
    const messages = document.getElementById("floatMessages");
    if (!messages || document.getElementById("floatThinkingMsg")) return;
    const msg = document.createElement("div");
    msg.id = "floatThinkingMsg";
    msg.className = "fc-thinking-msg";
    const dot = document.createElement("span");
    dot.className = "fc-thinking-dot";
    msg.appendChild(dot);
    msg.appendChild(document.createTextNode(label));
    messages.appendChild(msg);
    messages.scrollTop = messages.scrollHeight;
}

function removeFloatThinkingMessage() {
    const msg = document.getElementById("floatThinkingMsg");
    if (msg) msg.remove();
}

async function handleSandboxChat(sourceInput = null) {
    let input = sourceInput || document.getElementById("chatInput") || document.getElementById("floatChatInput");
    if (input && input.id === "chatInput" && typeof window.prepareAttachedChatFromSessionInput === "function") {
        input = window.prepareAttachedChatFromSessionInput(input) || input;
    }
    if (!input || !input.value.trim()) return;
    const userText = input.value.trim();
    const fromFloatChat = input.id === "floatChatInput";

    console.log("[Harness] submit captured");
    console.log(`[Harness] current mode: ${currentMode}`);
    showParserStatus("Submit captured");

    const floatChat = document.getElementById("floatChat");
    if (floatChat) floatChat.classList.remove("fc-long-response");

    if (currentMode !== "sandbox") {
        if (currentMode === "demo") {
            input.value = "";
            addChatMessage(userText, "user");
            if (fromFloatChat) addFloatHarnessMessage(userText, "user");
            if (fromFloatChat) showFloatThinkingMessage();
            setStatus("Demo Mode: simulating AI...", "requesting");
            setTimeout(() => {
                addChatMessage("This is a demo mode simulation. No backend was called.", "assistant");
                if (fromFloatChat) addFloatHarnessMessage("This is a demo mode simulation. No backend was called.", "assistant");
                setStatus("Demo simulation complete.", "idle");
                if (typeof window.setNotchState === "function") window.setNotchState("default");
            }, 800);
            return;
        }
        showCoProducerResponse("Switch to AI Sandbox Mode to use chat.", true);
        if (typeof window.setNotchState === "function") window.setNotchState("default");
        return;
    }

    input.value = "";
    addChatMessage(userText, "user");
    if (fromFloatChat) addFloatHarnessMessage(userText, "user");
    if (fromFloatChat) showFloatThinkingMessage();
    sandboxChatHistory.push({ role: "user", text: userText, ts: new Date().toISOString() });
    showParserStatus("Calling AI parser");
    const startTime = performance.now();
    const reqStartedAt = new Date().toISOString();

    try {
        console.log("[Harness] calling /harness/orchestrate");
        const res = await fetch("/harness/orchestrate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: userText })
        });
        const data = await res.json();
        const endTime = performance.now();
        const durationMs = Math.round(endTime - startTime);
        showParserStatus("Parser returned");

        if (!data.ok) {
            const reason = data.reason || data.error || "AI Sandbox is not configured. Check your .env file.";
            addChatMessage(reason, "assistant");
            if (fromFloatChat) addFloatHarnessMessage(reason, "assistant");
            sandboxChatHistory.push({ role: "assistant", text: reason, ts: new Date().toISOString() });
            setStatus("AI could not map that request.", "failed");
            return;
        }

        if (data.needs_confirmation && data.clarification) {
            addChatMessage(data.clarification, "assistant");
            if (fromFloatChat) addFloatHarnessMessage(data.clarification, "assistant");
            sandboxChatHistory.push({ role: "assistant", text: data.clarification, ts: new Date().toISOString() });
            setStatus("AI needs clarification.", "idle");
            return;
        }

        // Knowledge / mentor / read / clarify answer — display directly, no proposal card.
        if (data.type === "answer") {
            const answerText = data.text || "Couldn't get an answer — try rephrasing?";
            addChatMessage(answerText, "assistant");
            if (fromFloatChat) addFloatHarnessMessage(answerText, "assistant");
            sandboxChatHistory.push({ role: "assistant", text: answerText, ts: new Date().toISOString() });
            if (data.tokens && data.tokens.total) sessionStats.totalTokens += data.tokens.total;
            updateSessionTotals();
            setStatus("Answer ready.", "idle");
            if (typeof window.setNotchState === "function") window.setNotchState("default");
            return;
        }

        const action = ACTION_REGISTRY.find(a => a.id === data.action_id);
        if (!action) {
            addChatMessage("Not sure how to handle that one — try rephrasing?", "assistant");
            if (fromFloatChat) addFloatHarnessMessage("Not sure how to handle that one — try rephrasing?", "assistant");
            setStatus("Couldn't map that.", "failed");
            return;
        }
        if (!action.supported) {
            addChatMessage("I can't do that one in this version yet — it's on the roadmap.", "assistant");
            if (fromFloatChat) addFloatHarnessMessage("I can't do that one in this version yet — it's on the roadmap.", "assistant");
            setStatus("Not available yet.", "failed");
            return;
        }

        const proposal = {
            action_id: data.action_id,
            action_label: action.label,
            endpoint: action.endpoint,
            params: data.params || action.payload,
            confidence: data.confidence,
            reason: data.reason,
            sandbox: true,
            sandbox_session_id: SANDBOX_SESSION_ID,
            ai_obs: {
                model_name: data.model || null,
                provider: data.provider || null,
                input_tokens: data.tokens?.input || null,
                output_tokens: data.tokens?.output || null,
                total_tokens: data.tokens?.total || null,
                parse_duration_ms: durationMs,
                request_started_at: reqStartedAt,
                request_completed_at: new Date().toISOString()
            }
        };
        proposal.id = crypto.randomUUID();
        sandboxProposals.push(proposal);
        addChatMessage(buildProposalDOM(proposal), "assistant");
        if (fromFloatChat) addFloatHarnessMessage(buildProposalDOM(proposal, true), "assistant");
        sandboxChatHistory.push({ role: "assistant", text: `[Proposal] ${data.reason}`, ts: new Date().toISOString() });
        if (proposal.ai_obs.total_tokens) sessionStats.totalTokens += proposal.ai_obs.total_tokens;
        updateSessionTotals();
        setStatus(`Proposed: ${action.label}`, "idle");
    } catch (e) {
        const msg = e.message.includes("Failed to fetch")
            ? "Can\u2019t reach the harness proxy server. Is it running on port 4620?"
            : "Proxy error: " + e.message;
        addChatMessage(msg, "assistant");
        if (fromFloatChat) addFloatHarnessMessage(msg, "assistant");
        setStatus("Proxy unreachable.", "failed");
        if (typeof window.setNotchState === "function") window.setNotchState("default");
    }
}

function buildProposalDOM(proposal, compact = false) {
    const container = document.createElement("div");
    container.className = "sandbox-proposal";
    container.style.cssText = compact
        ? "background:rgba(255,255,255,0.04); border:1px solid var(--border-subtle); border-radius:8px; padding:10px; margin:2px 0; min-width:220px;"
        : "background:rgba(255,255,255,0.04); border:1px solid var(--border-subtle); border-radius:6px; padding:10px; margin:4px 0;";

    const titleDiv = document.createElement("div");
    titleDiv.style.cssText = "font-size:12px; font-weight:600; color:var(--text-primary); margin-bottom:6px;";
    titleDiv.textContent = `Proposed: ${proposal.action_label}`;
    container.appendChild(titleDiv);

    const reasonDiv = document.createElement("div");
    reasonDiv.style.cssText = "font-size:11px; color:var(--text-secondary); margin-bottom:4px;";
    reasonDiv.textContent = proposal.reason;
    container.appendChild(reasonDiv);

    // Confidence is the only meta shown directly; endpoint/model/tokens go in debug details.
    const confPct = Math.round((proposal.confidence || 0) * 100);
    const confDiv = document.createElement("div");
    confDiv.style.cssText = "font-size:11px; color:var(--text-secondary); margin-bottom:6px;";
    confDiv.textContent = `Confidence: ${confPct}%`;
    container.appendChild(confDiv);

    const details = document.createElement("details");
    details.style.cssText = "font-size:10px; color:var(--text-tertiary); margin-bottom:8px;";
    const summary = document.createElement("summary");
    summary.style.cursor = "pointer";
    summary.textContent = "Debug info";
    details.appendChild(summary);
    const modelStr = proposal.ai_obs.model_name || "not reported";
    const tokensStr = proposal.ai_obs.total_tokens || "not reported";
    const pre = document.createElement("pre");
    pre.style.cssText = "background:rgba(0,0,0,0.3); padding:6px; border-radius:4px; margin-top:4px; color:#a3adbd; font-size:10px;";
    pre.textContent = `Endpoint: ${proposal.endpoint}\nModel: ${modelStr} | Tokens: ${tokensStr}\n\nParams:\n${JSON.stringify(proposal.params, null, 2)}`;
    details.appendChild(pre);
    if (!compact) container.appendChild(details);

    const btn = document.createElement("button");
    btn.style.cssText = "background:var(--accent); color:white; border:none; padding:4px 12px; border-radius:4px; font-size:11px; font-weight:600; cursor:pointer;";
    btn.textContent = "Send to Live Mode";
    btn.addEventListener("click", async () => {
        const action = ACTION_REGISTRY.find(a => a.id === proposal.action_id);
        if (!action || !action.supported) {
            showCoProducerResponse("That action is no longer available.", true);
            return;
        }
        const execAction = { ...action, payload: proposal.params };
        addChatMessage(`Sending "${action.label}" to Ableton via Live Mode...`, "assistant");
        const floatStatus = document.getElementById("floatHarnessStatus");
        if (floatStatus) floatStatus.textContent = `Sending ${action.label} to Live Mode`;
        await executeAction(execAction, proposal.ai_obs);
    });
    container.appendChild(btn);

    const warnSpan = document.createElement("span");
    warnSpan.style.cssText = "font-size:10px; color:var(--text-tertiary); margin-left:8px;";
    warnSpan.textContent = "This will affect Ableton.";
    container.appendChild(warnSpan);

    return container;
}

function addChatMessage(content, role) {
    const messages = document.getElementById("messages");
    if (!messages) return;
    const wrap = document.createElement("div");
    if (role === "user") {
        wrap.className = "msg user";
        if (typeof content === "string") wrap.textContent = content;
        else wrap.appendChild(content);
    } else {
        wrap.className = "msg-wrap";
        const msgDiv = document.createElement("div");
        msgDiv.className = "msg assistant";
        if (typeof content === "string") msgDiv.textContent = content;
        else msgDiv.appendChild(content);
        wrap.appendChild(msgDiv);
    }
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
}

// ── Session Totals ───────────────────────────────────────────────────────────
function updateSessionTotals() {
    let totalsDiv = document.getElementById("session-totals-block");
    if (!totalsDiv) {
        totalsDiv = document.createElement("div");
        totalsDiv.id = "session-totals-block";
        totalsDiv.style.cssText = "font-size: 11px; color: var(--text-secondary); background: rgba(0,0,0,0.2); padding: 8px; border-radius: 6px; margin-bottom: 12px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px;";
        const mount = document.getElementById("session-totals-mount");
        const tasksBody = document.querySelector(".tasks-body .activity-now");
        if (mount) mount.appendChild(totalsDiv);
        else if (tasksBody) tasksBody.insertBefore(totalsDiv, document.getElementById("status-display"));
    }
    totalsDiv.innerHTML = `
        <div><strong>Actions:</strong> ${sessionStats.actionsRun}</div>
        <div><strong style="color:var(--success)">Verified:</strong> ${sessionStats.verified}</div>
        <div><strong style="color:var(--destructive)">Failed:</strong> ${sessionStats.failed}</div>
        <div><strong>Time:</strong> ${sessionStats.totalTimeMs}ms</div>
    `;
}

function exportSessionReport() {
    if (sessionLog.length === 0 && sandboxChatHistory.length === 0) {
        alert("No actions to export yet.");
        return;
    }
    const report = {
        generated_at: new Date().toISOString(),
        sandbox_session_id: SANDBOX_SESSION_ID,
        session_totals: sessionStats,
        actions: sessionLog,
        sandbox_chat_history: sandboxChatHistory,
        sandbox_proposals: sandboxProposals
    };
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `harness_session_report_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// ── Tab Switching ────────────────────────────────────────────────────────────
window.switchPage = function(pageId) {
    if (typeof window.applyPremiumTab === "function") {
        window.applyPremiumTab(pageId);
        return;
    }
    const tabs = document.querySelectorAll(".tab");
    tabs.forEach(t => t.classList.remove("active"));
    const activeTab = document.querySelector(`.tab[onclick="switchPage('${pageId}')"]`);
    if (activeTab) activeTab.classList.add("active");
    const pages = ["page-session", "page-tasks", "page-actions", "page-assistants"];
    pages.forEach(p => {
        const el = document.getElementById(p);
        if (el) {
            if (p === `page-${pageId}`) { el.classList.add("active"); el.style.display = "flex"; }
            else { el.classList.remove("active"); el.style.display = "none"; }
        }
    });
};

// ── Action Buttons ───────────────────────────────────────────────────────────
function renderActionButtons() {
    actionContainer.innerHTML = "";
    const groups = ["Track", "Mix", "Transport", "Plugin", "Roadmap"];
    groups.forEach(group => {
        const groupActions = ACTION_REGISTRY.filter(a => a.group === group);
        if (groupActions.length === 0) return;
        const header = document.createElement("div");
        header.style.cssText = "font-size: 11px; text-transform: uppercase; font-weight: 700; color: var(--text-tertiary); margin: 12px 0 6px 0; letter-spacing: 0.5px;";
        header.textContent = group === "Roadmap" ? "Roadmap / Not Built Yet" : group;
        actionContainer.appendChild(header);
        groupActions.forEach(action => {
            const btn = document.createElement("button");
            btn.className = "action-btn";
            const labelSpan = document.createElement("span");
            labelSpan.className = "label";
            labelSpan.textContent = action.label;
            const execSpan = document.createElement("span");
            execSpan.className = "exec-label";
            execSpan.textContent = "Send to Ableton";
            execSpan.style.cssText = "font-size: 10px; color: var(--accent); font-weight: 600;";
            btn.appendChild(labelSpan);
            if (!action.supported) {
                btn.disabled = true;
                btn.title = "Not built yet — on the roadmap.";
                const reasonSpan = document.createElement("span");
                reasonSpan.style.cssText = "font-size: 10px; color: var(--text-tertiary);";
                reasonSpan.textContent = "Roadmap";
                btn.appendChild(reasonSpan);
            } else {
                btn.appendChild(execSpan);
                btn.addEventListener("click", () => executeAction(action));
            }
            actionContainer.appendChild(btn);
        });
    });
}

// ── Status & CoProducer ──────────────────────────────────────────────────────
function setStatus(text, type) {
    if (!statusDisplay) return;
    statusDisplay.textContent = text;
    statusDisplay.style.color = type === "failed" ? "var(--destructive)" : type === "requesting" ? "var(--warning)" : "var(--accent-text)";
}

function showCoProducerResponse(text, isError = false, isSuccess = false) {
    if (!coproducerBox) return;
    coproducerBox.textContent = text;
    coproducerBox.classList.remove("hidden");
    if (isError) coproducerBox.style.borderLeftColor = "var(--destructive)";
    else if (isSuccess) coproducerBox.style.borderLeftColor = "var(--success)";
    else coproducerBox.style.borderLeftColor = "var(--accent)";
}

// ── Timeline ─────────────────────────────────────────────────────────────────
function addTimelineItem(action, response, translatedText, statusStr, obs) {
    if (!timelineContainer) return;
    const emptyMsg = timelineContainer.querySelector(".timeline-empty");
    if (emptyMsg) emptyMsg.remove();
    const item = document.createElement("div");
    item.className = "activity-log-row";
    item.style.flexDirection = "column";
    item.style.gap = "4px";
    const time = new Date().toLocaleTimeString();
    let simpleTiming = obs ? `in ${obs.duration_ms}ms` : "";
    if (statusStr === "Confirmed") simpleTiming = `<span style="color:var(--success)">Verified ${simpleTiming}</span>`;
    else if (statusStr === "Failed") simpleTiming = `<span style="color:var(--destructive)">Failed ${simpleTiming}</span>`;
    else simpleTiming = `${statusStr} ${simpleTiming}`;

    const escapeHtml = (unsafe) => {
        if (typeof unsafe !== 'string') return unsafe;
        return unsafe.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    };

    let obsHtml = "";
    if (obs) {
        obsHtml = `<div style="margin-bottom: 8px; color: #a3adbd; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 6px;">
            <strong>Observability / Timing</strong><br>
            Mode: ${escapeHtml(obs.mode) || "live"}<br>
            Endpoint: <code>${escapeHtml(obs.endpoint_called)}</code><br>
            Request: ${escapeHtml(obs.request_started_at)} \u2192 ${escapeHtml(obs.request_completed_at)} (${obs.duration_ms}ms)<br>
            Model: ${escapeHtml(obs.model_name) || "not reported"}<br>
            Tokens (In/Out/Total): ${escapeHtml(String(obs.input_tokens)) || "not reported"} / ${escapeHtml(String(obs.output_tokens)) || "not reported"} / ${escapeHtml(String(obs.total_tokens)) || "not reported"}<br>
            Est. Cost: ${obs.estimated_cost ? "$" + obs.estimated_cost.toFixed(5) : "not reported"}<br>
            <br><em>Backend Timing Breakdown:</em><br>
            Retrieval: ${obs.retrieval_time_ms ? obs.retrieval_time_ms + "ms" : "not reported"}<br>
            Execution: ${obs.action_execution_time_ms ? obs.action_execution_time_ms + "ms" : "not reported"}<br>
            Verification: ${obs.readback_verification_time_ms ? obs.readback_verification_time_ms + "ms" : "not reported"}<br>
            ${obs.sandbox_session_id ? "Sandbox ID: " + escapeHtml(obs.sandbox_session_id) + "<br>" : ""}
        </div>`;
    }
    item.innerHTML = `<div style="display: flex; justify-content: space-between; width: 100%; font-size: 12px; color: var(--text-primary); margin-bottom: 4px;">
            <span>${escapeHtml(action.label)}</span>
            <span style="font-size: 10px; color: var(--text-tertiary);">${time} | ${simpleTiming}</span>
        </div>
        <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.4; background: rgba(255,255,255,0.03); padding: 6px; border-radius: 4px; width: 100%;">
            <em>Co-Producer:</em> "${escapeHtml(translatedText)}"
            <details style="margin-top: 6px; color: var(--text-tertiary); font-size: 10px;">
                <summary style="cursor: pointer; opacity: 0.8;">Debug Data (Raw ActionProof & Observability)</summary>
                <div style="background: rgba(0,0,0,0.4); padding: 8px; border-radius: 4px; overflow-x: auto; margin-top: 4px; color: #a3adbd;">
                    ${obsHtml}
                    <strong>Raw Response JSON</strong>
                    <pre style="margin-top:4px;">${escapeHtml(JSON.stringify(response, null, 2))}</pre>
                </div>
            </details>
        </div>`;
    timelineContainer.prepend(item);
}

// ── Execute Action ───────────────────────────────────────────────────────────
async function executeAction(action, aiObs = null) {
    const startTime = performance.now();
    const reqStartedAt = new Date().toISOString();
    setStatus(`Applying ${action.label}...`, "requesting");
    if (coproducerBox) coproducerBox.classList.add("hidden");

    if (currentMode === "demo") {
        setTimeout(() => {
            const endTime = performance.now();
            const reqCompletedAt = new Date().toISOString();
            const durationMs = Math.round(endTime - startTime);
            const mockResponses = [
                { ok: true, verification_status: "VERIFIED" },
                { ok: true, verification_status: "ALREADY_CORRECT" },
                { ok: false, error_code: "UNDO_DRIFT_DETECTED" },
                { ok: false, error_code: "SECURITY_CONFIRMATION_REQUIRED" },
                { ok: false, error_code: "BRIDGE_PLUGIN_ABSENT" }
            ];
            const sim = mockResponses[Math.floor(Math.random() * mockResponses.length)];
            const text = composeReply(action, sim);
            const statusStr = translateStatus(sim);
            const obs = {
                request_started_at: reqStartedAt, request_completed_at: reqCompletedAt,
                duration_ms: durationMs, endpoint_called: action.endpoint,
                response_status: sim.ok ? "200 OK" : "Simulated Error",
                verification_status: sim.verification_status || "UNKNOWN",
                mode: "demo",
                model_name: null, input_tokens: null, output_tokens: null,
                total_tokens: null, estimated_cost: null,
                retrieval_time_ms: null, action_execution_time_ms: null,
                readback_verification_time_ms: null
            };
            updateStatsAndLog(action, sim, obs, statusStr);
            setStatus(statusStr, sim.ok ? "verified" : "failed");
            showCoProducerResponse(`(DEMO) ${text}`, !sim.ok, sim.ok);
            addTimelineItem(action, sim, text, statusStr, obs);
            switchPage("tasks");
        }, 800);
        return;
    }

    // Live Mode or Sandbox->Live execution
    try {
        const res = await fetch(`${BRIDGE_URL}${action.endpoint}`, {
            method: action.method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(action.payload)
        });
        const data = await res.json();
        const endTime = performance.now();
        const reqCompletedAt = new Date().toISOString();
        const durationMs = Math.round(endTime - startTime);
        const text = composeReply(action, data);
        const statusStr = translateStatus(data);
        const obs = {
            request_started_at: reqStartedAt, request_completed_at: reqCompletedAt,
            duration_ms: durationMs, endpoint_called: action.endpoint,
            response_status: `${res.status} ${res.statusText}`,
            verification_status: data.verification_status || "UNKNOWN",
            mode: currentMode === "sandbox" ? "sandbox->live" : "live",
            sandbox_session_id: currentMode === "sandbox" ? SANDBOX_SESSION_ID : null,
            model_name: aiObs?.model_name || data.model || data.debug?.model || null,
            input_tokens: aiObs?.input_tokens || data.tokens?.input || data.debug?.tokens?.input || null,
            output_tokens: aiObs?.output_tokens || data.tokens?.output || data.debug?.tokens?.output || null,
            total_tokens: aiObs?.total_tokens || data.tokens?.total || data.debug?.tokens?.total || null,
            estimated_cost: aiObs?.estimated_cost || data.cost || data.debug?.cost || null,
            retrieval_time_ms: data.timing?.retrieval_ms || data.debug?.timing?.retrieval_ms || null,
            action_execution_time_ms: data.timing?.execution_ms || data.debug?.timing?.execution_ms || null,
            readback_verification_time_ms: data.timing?.verification_ms || data.debug?.timing?.verification_ms || null
        };
        updateStatsAndLog(action, data, obs, statusStr);
        setStatus(statusStr, data.ok ? "verified" : "failed");
        showCoProducerResponse(text, !data.ok, data.ok && (data.verification_status === "VERIFIED" || data.verification_status === "ALREADY_CORRECT"));
        addTimelineItem(action, data, text, statusStr, obs);
        switchPage("tasks");
    } catch (e) {
        const endTime = performance.now();
        const durationMs = Math.round(endTime - startTime);
        const obs = {
            request_started_at: reqStartedAt, request_completed_at: new Date().toISOString(),
            duration_ms: durationMs, endpoint_called: action.endpoint,
            response_status: "Fetch Error", verification_status: "FAILED_NETWORK",
            mode: currentMode, sandbox_session_id: currentMode === "sandbox" ? SANDBOX_SESSION_ID : null,
            model_name: aiObs?.model_name || null,
            input_tokens: aiObs?.input_tokens || null, output_tokens: aiObs?.output_tokens || null,
            total_tokens: aiObs?.total_tokens || null, estimated_cost: null
        };
        updateStatsAndLog(action, { ok: false, error: e.message }, obs, "Failed");
        setStatus("Failed", "failed");
        showCoProducerResponse("I can\u2019t reach Ableton right now. Is the bridge running?", true);
        addTimelineItem(action, { ok: false, error: e.message }, "I can\u2019t reach Ableton right now. Is the bridge running?", "Failed", obs);
        switchPage("tasks");
    }
}

// ── Stats & Log ──────────────────────────────────────────────────────────────
function updateStatsAndLog(action, response, obs, statusStr) {
    sessionStats.actionsRun++;
    sessionStats.totalTimeMs += obs.duration_ms;
    if (response.ok && (response.verification_status === "VERIFIED" || response.verification_status === "ALREADY_CORRECT")) {
        sessionStats.verified++;
    } else {
        sessionStats.failed++;
    }
    if (obs.total_tokens) sessionStats.totalTokens += obs.total_tokens;
    if (obs.estimated_cost) sessionStats.estimatedCostUsd += obs.estimated_cost;
    sessionLog.push({
        timestamp: new Date().toISOString(),
        action: action.label, endpoint: action.endpoint,
        status: statusStr, mode: obs.mode,
        sandbox_session_id: obs.sandbox_session_id || null,
        observability: obs, raw_response: response
    });
    updateSessionTotals();
}

})();
