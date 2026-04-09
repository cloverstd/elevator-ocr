from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>电梯楼层识别</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f3efe4;
        --card: rgba(255, 252, 245, 0.88);
        --ink: #17202a;
        --accent: #176087;
        --muted: #6f7880;
        --ok: #237a3b;
        --bad: #b64926;
        --ring: rgba(23, 96, 135, 0.18);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(circle at top left, rgba(23, 96, 135, 0.18), transparent 30%),
          radial-gradient(circle at bottom right, rgba(182, 73, 38, 0.15), transparent 28%),
          linear-gradient(135deg, #f9f5eb 0%, #efe7d8 45%, #f4efe6 100%);
        color: var(--ink);
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      }
      .panel {
        width: min(96vw, 1360px);
        padding: 28px;
        border-radius: 28px;
        background: var(--card);
        border: 1px solid rgba(23, 32, 42, 0.08);
        box-shadow: 0 24px 70px rgba(23, 32, 42, 0.12);
        backdrop-filter: blur(18px);
      }
      .page {
        display: grid;
        gap: 20px;
      }
      .layout {
        display: grid;
        grid-template-columns: minmax(0, 1.18fr) minmax(420px, 0.82fr);
        gap: 20px;
        align-items: start;
      }
      .camera {
        border-radius: 22px;
        background: rgba(23, 32, 42, 0.92);
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
      }
      .camera-toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 12px 14px;
        color: rgba(255,255,255,0.88);
        border-bottom: 1px solid rgba(255,255,255,0.08);
      }
      .camera-toolbar-left {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }
      .zoom-readout {
        min-width: 56px;
        text-align: center;
        font-size: 13px;
        color: rgba(255,255,255,0.8);
      }
      .camera-viewport {
        overflow: auto;
        max-height: 72vh;
        overscroll-behavior: contain;
      }
      .camera-stage {
        position: relative;
        width: fit-content;
      }
      .camera img {
        display: block;
        width: 100%;
        height: 100%;
      }
      .overlay {
        position: absolute;
        inset: 0;
        pointer-events: none;
      }
      .roi {
        position: absolute;
        border: 3px solid;
        border-radius: 12px;
        pointer-events: auto;
        touch-action: none;
        min-width: 24px;
        min-height: 24px;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.16);
      }
      .roi-floor { border-color: #40dc60; }
      .roi-direction { border-color: #ffb428; }
      .roi.active {
        box-shadow: 0 0 0 4px rgba(255,255,255,0.18), inset 0 0 0 1px rgba(255,255,255,0.16);
      }
      .roi-label {
        position: absolute;
        top: -28px;
        left: 0;
        padding: 4px 8px;
        border-radius: 999px;
        color: #fff;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.04em;
        background: rgba(23, 32, 42, 0.78);
      }
      .roi-handle {
        position: absolute;
        right: -8px;
        bottom: -8px;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: #fff;
        border: 2px solid rgba(23, 32, 42, 0.85);
        cursor: nwse-resize;
      }
      .roi-rotation {
        position: absolute;
        top: -26px;
        right: -6px;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #fff;
        border: 2px solid rgba(23, 32, 42, 0.85);
        opacity: 0.9;
      }
      .camera-note {
        margin: 0;
        padding: 10px 14px 14px;
        color: rgba(255,255,255,0.72);
        font-size: 13px;
      }
      .status {
        min-width: 0;
        display: grid;
        gap: 16px;
      }
      .summary-card {
        padding: 18px 20px;
        border-radius: 22px;
        background: rgba(255, 255, 255, 0.72);
        box-shadow: inset 0 0 0 1px var(--ring);
      }
      .notice {
        display: none;
        padding: 14px 16px;
        border-radius: 16px;
        font-size: 14px;
        font-weight: 700;
        box-shadow: inset 0 0 0 1px var(--ring);
      }
      .notice.show {
        display: block;
      }
      .notice.info {
        background: rgba(23, 96, 135, 0.1);
        color: var(--accent);
      }
      .notice.ok {
        background: rgba(35, 122, 59, 0.12);
        color: var(--ok);
      }
      .notice.bad {
        background: rgba(182, 73, 38, 0.12);
        color: var(--bad);
      }
      .segmented {
        display: inline-flex;
        padding: 4px;
        border-radius: 999px;
        background: rgba(23, 32, 42, 0.08);
        gap: 4px;
      }
      .segmented button {
        padding: 7px 12px;
        border-radius: 999px;
        background: transparent;
        color: var(--muted);
      }
      .segmented button.active {
        background: #17202a;
        color: #fff;
      }
      .eyebrow {
        margin: 0 0 8px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        font-size: 12px;
        color: var(--muted);
      }
      .floor {
        font-family: "Space Grotesk", "Segoe UI", sans-serif;
        font-size: clamp(88px, 20vw, 144px);
        line-height: 0.95;
        margin: 0;
      }
      .meta {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        margin-top: 20px;
      }
      .stat {
        padding: 14px 16px;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
        box-shadow: inset 0 0 0 1px var(--ring);
      }
      .label {
        display: block;
        font-size: 12px;
        color: var(--muted);
        margin-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .value {
        font-size: 22px;
        font-weight: 700;
      }
      .status-ok { color: var(--ok); }
      .status-bad { color: var(--bad); }
      .footer {
        margin-top: 18px;
        font-size: 13px;
        color: var(--muted);
      }
      .roi-tools {
        display: grid;
        gap: 16px;
      }
      .section-dual {
        display: grid;
        grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
        gap: 16px;
        align-items: start;
      }
      .bottom-dual {
        display: grid;
        grid-template-columns: minmax(360px, 0.82fr) minmax(0, 1.18fr);
        gap: 20px;
        align-items: start;
      }
      .section-stack {
        display: grid;
        gap: 16px;
      }
      .roi-card {
        padding: 14px 16px;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
        box-shadow: inset 0 0 0 1px var(--ring);
      }
      .roi-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 8px;
      }
      .roi-title {
        margin: 0;
        font-size: 14px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
      }
      .roi-code {
        margin: 0;
        font-family: "IBM Plex Mono", monospace;
        font-size: 14px;
        line-height: 1.5;
        word-break: break-all;
      }
      .roi-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      button {
        appearance: none;
        border: 0;
        border-radius: 10px;
        padding: 8px 12px;
        font: inherit;
        font-size: 13px;
        font-weight: 700;
        background: #17202a;
        color: #fff;
        cursor: pointer;
      }
      .camera button {
        background: rgba(255,255,255,0.12);
        color: #fff;
      }
      button.secondary {
        background: rgba(23, 32, 42, 0.1);
        color: var(--ink);
        box-shadow: inset 0 0 0 1px rgba(23, 32, 42, 0.12);
      }
      input[type="range"] {
        width: 160px;
      }
      .hint {
        margin: 10px 0 0;
        color: var(--muted);
        font-size: 13px;
      }
      .preview-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
      }
      .preview-card {
        padding: 14px 16px;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
        box-shadow: inset 0 0 0 1px var(--ring);
      }
      .preview-card img {
        display: block;
        width: 100%;
        height: auto;
        border-radius: 12px;
        background: #111;
        image-rendering: pixelated;
      }
      .preview-meta {
        margin-top: 12px;
        display: grid;
        gap: 10px;
      }
      .prediction {
        font-size: 14px;
        color: var(--ink);
      }
      .prediction strong {
        font-size: 18px;
      }
      .feedback-row {
        display: flex;
        gap: 8px;
        align-items: center;
        flex-wrap: wrap;
      }
      .feedback-input,
      .feedback-select {
        width: 100%;
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid rgba(23, 32, 42, 0.14);
        background: rgba(255, 255, 255, 0.96);
        color: var(--ink);
        font: inherit;
      }
      .feedback-status {
        min-height: 18px;
        font-size: 13px;
        color: var(--muted);
      }
      .feedback-status.ok {
        color: var(--ok);
      }
      .feedback-status.bad {
        color: var(--bad);
      }
      .stats-card {
        padding: 14px 16px;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
        box-shadow: inset 0 0 0 1px var(--ring);
      }
      .stats-card p {
        margin: 6px 0 0;
        color: var(--muted);
        font-size: 14px;
      }
      .stats-emphasis {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin-top: 12px;
      }
      .coverage-summary {
        margin-top: 12px;
        font-size: 14px;
        color: var(--muted);
      }
      .coverage-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 8px;
        margin-top: 12px;
      }
      .coverage-chip {
        padding: 10px 8px;
        border-radius: 12px;
        background: rgba(23, 32, 42, 0.06);
        text-align: center;
        box-shadow: inset 0 0 0 1px rgba(23, 32, 42, 0.08);
      }
      .coverage-chip strong {
        display: block;
        font-size: 14px;
      }
      .coverage-chip span {
        display: block;
        margin-top: 4px;
        font-size: 12px;
        color: var(--muted);
      }
      .coverage-chip.empty {
        background: rgba(182, 73, 38, 0.08);
      }
      .coverage-chip.low {
        background: rgba(255, 180, 40, 0.14);
      }
      .coverage-chip.good {
        background: rgba(35, 122, 59, 0.12);
      }
      .stats-emphasis .stat {
        padding: 12px 14px;
      }
      .field-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }
      .field {
        display: grid;
        gap: 6px;
      }
      .field label {
        font-size: 12px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .field input {
        width: 100%;
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid rgba(23, 32, 42, 0.14);
        background: rgba(255, 255, 255, 0.96);
        color: var(--ink);
        font: inherit;
      }
      .training-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        align-items: start;
      }
      .training-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
      }
      .status-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 72px;
        padding: 6px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.04em;
      }
      .status-pill-idle {
        background: rgba(23, 32, 42, 0.08);
        color: var(--muted);
      }
      .status-pill-running {
        background: rgba(23, 96, 135, 0.14);
        color: var(--accent);
      }
      .status-pill-succeeded {
        background: rgba(35, 122, 59, 0.14);
        color: var(--ok);
      }
      .status-pill-failed {
        background: rgba(182, 73, 38, 0.14);
        color: var(--bad);
      }
      .training-metric {
        margin-top: 6px;
        font-size: 13px;
        color: var(--muted);
      }
      .training-metric.strong-ok {
        color: var(--ok);
        font-weight: 700;
      }
      .training-metric.strong-warn {
        color: var(--bad);
        font-weight: 700;
      }
      .training-trend {
        margin-top: 8px;
        font-size: 13px;
        font-weight: 700;
      }
      .training-trend.better {
        color: var(--ok);
      }
      .training-trend.same {
        color: var(--accent);
      }
      .training-trend.worse {
        color: var(--bad);
      }
      .trend-chart {
        width: 100%;
        height: 120px;
        margin-top: 10px;
        border-radius: 12px;
        background: rgba(23, 32, 42, 0.06);
        display: none;
      }
      .trend-empty {
        margin-top: 10px;
        font-size: 13px;
        color: var(--muted);
      }
      .training-log {
        margin: 10px 0 0;
        padding: 12px;
        min-height: 120px;
        border-radius: 12px;
        background: rgba(23, 32, 42, 0.92);
        color: rgba(255, 255, 255, 0.9);
        font: 12px/1.45 "IBM Plex Mono", monospace;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .debug-list {
        margin: 10px 0 0;
        padding-left: 18px;
        color: var(--ink);
        font-size: 14px;
      }
      .debug-list li {
        margin: 4px 0;
      }
      .pending-view {
        display: grid;
        gap: 12px;
      }
      .pending-batch-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .pending-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 12px;
        flex-wrap: wrap;
      }
      .pending-image {
        display: block;
        width: 100%;
        height: auto;
        border-radius: 12px;
        background: #111;
        image-rendering: pixelated;
      }
      .pending-list {
        display: grid;
        gap: 8px;
        max-height: 280px;
        overflow: auto;
      }
      .pending-item {
        display: grid;
        grid-template-columns: auto 76px minmax(0, 1fr);
        gap: 10px;
        align-items: center;
        padding: 8px;
        border-radius: 12px;
        border: 0;
        background: rgba(255, 255, 255, 0.72);
        box-shadow: inset 0 0 0 1px var(--ring);
        cursor: pointer;
        color: var(--ink);
        text-align: left;
      }
      .pending-item.active {
        box-shadow: inset 0 0 0 2px rgba(23, 96, 135, 0.45);
        background: rgba(23, 96, 135, 0.08);
      }
      .pending-thumb {
        display: block;
        width: 76px;
        height: 46px;
        object-fit: cover;
        border-radius: 8px;
        background: #111;
      }
      .pending-check {
        width: 16px;
        height: 16px;
        accent-color: #176087;
      }
      .pending-item-meta {
        min-width: 0;
        font-size: 13px;
        color: var(--ink);
      }
      .pending-item-meta strong {
        display: block;
        font-size: 14px;
      }
      .preview-title {
        margin: 0 0 10px;
        font-size: 14px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
      }
      @media (max-width: 900px) {
        .layout {
          grid-template-columns: 1fr;
        }
        .bottom-dual,
        .section-dual,
        .preview-grid {
          grid-template-columns: 1fr;
        }
        .training-grid,
        .stats-emphasis,
        .coverage-grid {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <main class="panel">
      <div class="page">
        <div class="layout">
          <section class="camera">
            <div class="camera-toolbar">
              <div class="camera-toolbar-left">
                <button id="zoom-out" type="button">-</button>
                <input id="zoom-slider" type="range" min="0.1" max="3" step="0.05" value="1">
                <button id="zoom-in" type="button">+</button>
                <button id="zoom-fit" type="button">适配</button>
                <button id="zoom-100" type="button">100%</button>
                <span id="zoom-readout" class="zoom-readout">100%</span>
              </div>
            </div>
            <div id="camera-viewport" class="camera-viewport">
              <div id="camera-stage" class="camera-stage">
                <img id="snapshot" src="/api/v1/frame.jpg" alt="电梯最新画面">
                <div id="overlay" class="overlay">
                  <div id="floor-roi" class="roi roi-floor">
                    <span class="roi-label">楼层</span>
                    <span class="roi-handle" data-role="resize"></span>
                    <span class="roi-rotation"></span>
                  </div>
                  <div id="direction-roi" class="roi roi-direction">
                    <span class="roi-label">方向</span>
                    <span class="roi-handle" data-role="resize"></span>
                    <span class="roi-rotation"></span>
                  </div>
                </div>
              </div>
            </div>
            <p class="camera-note">最新画面，已叠加楼层和方向 ROI 框。</p>
          </section>
          <section class="status">
            <div id="training-notice" class="notice"></div>
            <div class="summary-card">
              <p class="eyebrow">电梯状态</p>
              <h1 id="floor" class="floor">--</h1>
              <div class="meta">
                <div class="stat">
                  <span class="label">方向</span>
                  <span id="direction" class="value">未知</span>
                </div>
                <div class="stat">
                  <span class="label">视频流</span>
                  <span id="stream" class="value status-bad">未连接</span>
                </div>
              </div>
              <p id="updated" class="footer">等待状态更新...</p>
            </div>
            <div class="roi-tools">
              <div class="section-dual">
                <div class="section-stack">
                  <div class="roi-card">
                    <div class="roi-head">
                      <h2 class="roi-title">楼层 ROI</h2>
                      <div class="roi-actions">
                        <button id="floor-rotate-minus" class="secondary" type="button">-1°</button>
                        <button id="floor-rotate-plus" class="secondary" type="button">+1°</button>
                        <button id="copy-floor" type="button">复制</button>
                      </div>
                    </div>
                    <p id="floor-roi-text" class="roi-code">FLOOR_ROI=--</p>
                  </div>
                  <div class="roi-card">
                    <div class="roi-head">
                      <h2 class="roi-title">方向 ROI</h2>
                      <div class="roi-actions">
                        <button id="direction-rotate-minus" class="secondary" type="button">-1°</button>
                        <button id="direction-rotate-plus" class="secondary" type="button">+1°</button>
                        <button id="copy-direction" type="button">复制</button>
                      </div>
                    </div>
                    <p id="direction-roi-text" class="roi-code">DIRECTION_ROI=--</p>
                  </div>
                  <div class="roi-card">
                    <div class="roi-actions">
                      <button id="copy-both" type="button">复制两项</button>
                      <button id="reset-roi" class="secondary" type="button">重置</button>
                    </div>
                    <p class="hint">拖动框内部可移动位置，拖动圆点可调整大小。数值使用原始像素坐标，可直接粘贴到 `.env`。</p>
                  </div>
                </div>
                <div class="section-stack">
                  <div class="stats-card">
                    <h3 class="preview-title">标注统计</h3>
                  <p id="feedback-stats">已标楼层 0，已标方向 0，待标楼层 0</p>
                  <div class="stats-emphasis">
                    <div class="stat">
                      <span class="label">当前楼层</span>
                      <span id="floor-prediction" class="value">--</span>
                      </div>
                      <div class="stat">
                        <span class="label">当前方向</span>
                        <span id="direction-prediction" class="value">未知</span>
                      </div>
                      <div class="stat">
                        <span class="label">训练状态</span>
                      <span id="training-overview" class="value">空闲</span>
                    </div>
                  </div>
                  <div id="floor-coverage-summary" class="coverage-summary">楼层覆盖 0 / 0，等待样本。</div>
                  <div id="floor-coverage-grid" class="coverage-grid"></div>
                </div>
                  <div class="stats-card">
                    <h3 class="preview-title">识别调试</h3>
                    <p id="debug-floor-source">楼层来源：--</p>
                    <ul id="debug-floor-candidates" class="debug-list">
                      <li>还没有楼层候选。</li>
                    </ul>
                    <p id="debug-direction-source">方向来源：--</p>
                    <ul id="debug-direction-candidates" class="debug-list">
                      <li>还没有方向候选。</li>
                    </ul>
                  </div>
                </div>
              </div>
              <div class="preview-grid">
                <div class="preview-card">
                  <h3 class="preview-title">楼层裁剪</h3>
                  <img id="floor-preview" src="/api/v1/frame/floor.jpg" alt="楼层裁剪">
                  <div class="preview-meta">
                    <div class="prediction">当前预测：<strong id="floor-inline-prediction">--</strong></div>
                    <div class="feedback-row">
                      <button id="floor-accept" type="button">预测正确</button>
                    </div>
                    <input id="floor-label-input" class="feedback-input" type="text" placeholder="输入正确楼层，例如 35 或 -2">
                    <div class="feedback-row">
                      <button id="floor-submit" class="secondary" type="button">提交楼层标注</button>
                    </div>
                    <div id="floor-feedback-status" class="feedback-status"></div>
                  </div>
                </div>
                <div class="preview-card">
                  <h3 class="preview-title">方向裁剪</h3>
                  <img id="direction-preview" src="/api/v1/frame/direction.jpg" alt="方向裁剪">
                  <div class="preview-meta">
                    <div class="prediction">当前预测：<strong id="direction-inline-prediction">未知</strong></div>
                    <div class="feedback-row">
                      <button id="direction-accept" type="button">预测正确</button>
                    </div>
                    <select id="direction-label-input" class="feedback-select">
                      <option value="up">上行</option>
                      <option value="down">下行</option>
                      <option value="idle">静止</option>
                      <option value="unknown">未知</option>
                    </select>
                    <div class="feedback-row">
                      <button id="direction-submit" class="secondary" type="button">提交方向标注</button>
                    </div>
                    <div id="direction-feedback-status" class="feedback-status"></div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
        <section class="bottom-dual">
          <div class="stats-card">
            <h3 class="preview-title">待标楼层样本</h3>
            <div class="pending-head">
              <div class="segmented">
                <button id="history-pending" class="active" type="button">待标</button>
                <button id="history-labeled" type="button">已标</button>
              </div>
              <div class="segmented">
                <button id="pending-order-hard" class="active" type="button">困难优先</button>
                <button id="pending-order-newest" type="button">最新优先</button>
              </div>
            </div>
            <div class="pending-view">
              <img id="pending-floor-image" class="pending-image" alt="待标楼层样本">
              <div id="pending-floor-meta" class="feedback-status">当前没有待标楼层样本。</div>
              <input id="pending-floor-label-input" class="feedback-input" type="text" placeholder="输入这张待标样本的楼层">
              <div class="roi-actions">
                <button id="pending-floor-submit" class="secondary" type="button">提交标注</button>
                <button id="pending-floor-next" class="secondary" type="button">下一张</button>
              </div>
              <div id="pending-batch-actions" class="pending-batch-actions">
                <button id="pending-floor-select-all" class="secondary" type="button">全选本页</button>
                <button id="pending-floor-clear-all" class="secondary" type="button">清空选择</button>
                <button id="pending-floor-batch-submit" type="button">批量提交选中</button>
              </div>
              <div id="pending-floor-status" class="feedback-status"></div>
              <div id="pending-floor-list" class="pending-list">
                <div class="feedback-status">还没有待标历史样本。</div>
              </div>
            </div>
          </div>
          <div class="stats-card">
            <h3 class="preview-title">模型训练</h3>
            <div class="field-grid">
              <div class="field">
                <label for="train-epochs">训练轮数</label>
                <input id="train-epochs" type="number" min="1" max="500" value="18">
              </div>
              <div class="field">
                <label for="train-batch-size">批大小</label>
                <input id="train-batch-size" type="number" min="1" max="1024" value="32">
              </div>
              <div class="field">
                <label for="train-lr">学习率</label>
                <input id="train-lr" type="number" min="0.000001" max="1" step="0.0001" value="0.001">
              </div>
              <div class="field">
                <label for="train-image-size">输入尺寸</label>
                <input id="train-image-size" type="number" min="16" max="512" value="96">
              </div>
            </div>
            <div class="roi-actions" style="margin-top: 12px;">
              <button id="train-floor" type="button">训练楼层模型</button>
              <button id="train-direction" type="button">训练方向模型</button>
              <button id="reload-models" class="secondary" type="button">重新加载模型</button>
            </div>
            <div class="training-grid" style="margin-top: 12px;">
              <div class="preview-card">
                <div class="training-head">
                  <h3 class="preview-title">楼层模型</h3>
                  <span id="floor-train-pill" class="status-pill status-pill-idle">空闲</span>
                </div>
                <div id="floor-train-metric" class="training-metric">暂无训练结果。</div>
                <div id="floor-train-trend" class="training-trend">等待首次训练。</div>
                <div id="floor-train-chart-empty" class="trend-empty">至少训练两次后显示趋势图。</div>
                <svg id="floor-train-chart" class="trend-chart" viewBox="0 0 320 120" preserveAspectRatio="none"></svg>
                <div id="floor-train-status" class="feedback-status">空闲，尚未开始训练。</div>
                <pre id="floor-train-log" class="training-log">还没有训练记录。</pre>
              </div>
              <div class="preview-card">
                <div class="training-head">
                  <h3 class="preview-title">方向模型</h3>
                  <span id="direction-train-pill" class="status-pill status-pill-idle">空闲</span>
                </div>
                <div id="direction-train-metric" class="training-metric">暂无训练结果。</div>
                <div id="direction-train-trend" class="training-trend">等待首次训练。</div>
                <div id="direction-train-chart-empty" class="trend-empty">至少训练两次后显示趋势图。</div>
                <svg id="direction-train-chart" class="trend-chart" viewBox="0 0 320 120" preserveAspectRatio="none"></svg>
                <div id="direction-train-status" class="feedback-status">空闲，尚未开始训练。</div>
                <pre id="direction-train-log" class="training-log">还没有训练记录。</pre>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
    <script>
      const floorEl = document.getElementById("floor");
      const directionEl = document.getElementById("direction");
      const streamEl = document.getElementById("stream");
      const updatedEl = document.getElementById("updated");
      const snapshotEl = document.getElementById("snapshot");
      const floorPreviewEl = document.getElementById("floor-preview");
      const directionPreviewEl = document.getElementById("direction-preview");
      const overlayEl = document.getElementById("overlay");
      const stageEl = document.getElementById("camera-stage");
      const viewportEl = document.getElementById("camera-viewport");
      const floorRoiEl = document.getElementById("floor-roi");
      const directionRoiEl = document.getElementById("direction-roi");
      const floorRoiTextEl = document.getElementById("floor-roi-text");
      const directionRoiTextEl = document.getElementById("direction-roi-text");
      const zoomSliderEl = document.getElementById("zoom-slider");
      const zoomReadoutEl = document.getElementById("zoom-readout");
      const zoomOutEl = document.getElementById("zoom-out");
      const zoomInEl = document.getElementById("zoom-in");
      const zoomFitEl = document.getElementById("zoom-fit");
      const zoom100El = document.getElementById("zoom-100");
      const copyFloorEl = document.getElementById("copy-floor");
      const copyDirectionEl = document.getElementById("copy-direction");
      const copyBothEl = document.getElementById("copy-both");
      const resetRoiEl = document.getElementById("reset-roi");
      const floorRotateMinusEl = document.getElementById("floor-rotate-minus");
      const floorRotatePlusEl = document.getElementById("floor-rotate-plus");
      const directionRotateMinusEl = document.getElementById("direction-rotate-minus");
      const directionRotatePlusEl = document.getElementById("direction-rotate-plus");
      const floorPredictionEl = document.getElementById("floor-prediction");
      const directionPredictionEl = document.getElementById("direction-prediction");
      const floorAcceptEl = document.getElementById("floor-accept");
      const directionAcceptEl = document.getElementById("direction-accept");
      const floorLabelInputEl = document.getElementById("floor-label-input");
      const directionLabelInputEl = document.getElementById("direction-label-input");
      const floorSubmitEl = document.getElementById("floor-submit");
      const directionSubmitEl = document.getElementById("direction-submit");
      const floorFeedbackStatusEl = document.getElementById("floor-feedback-status");
      const directionFeedbackStatusEl = document.getElementById("direction-feedback-status");
      const feedbackStatsEl = document.getElementById("feedback-stats");
      const floorCoverageSummaryEl = document.getElementById("floor-coverage-summary");
      const floorCoverageGridEl = document.getElementById("floor-coverage-grid");
      const floorInlinePredictionEl = document.getElementById("floor-inline-prediction");
      const directionInlinePredictionEl = document.getElementById("direction-inline-prediction");
      const trainingOverviewEl = document.getElementById("training-overview");
      const trainingNoticeEl = document.getElementById("training-notice");
      const debugFloorSourceEl = document.getElementById("debug-floor-source");
      const debugFloorCandidatesEl = document.getElementById("debug-floor-candidates");
      const debugDirectionSourceEl = document.getElementById("debug-direction-source");
      const debugDirectionCandidatesEl = document.getElementById("debug-direction-candidates");
      const pendingFloorImageEl = document.getElementById("pending-floor-image");
      const pendingFloorMetaEl = document.getElementById("pending-floor-meta");
      const pendingFloorLabelInputEl = document.getElementById("pending-floor-label-input");
      const pendingFloorSubmitEl = document.getElementById("pending-floor-submit");
      const pendingFloorNextEl = document.getElementById("pending-floor-next");
      const pendingBatchActionsEl = document.getElementById("pending-batch-actions");
      const pendingFloorSelectAllEl = document.getElementById("pending-floor-select-all");
      const pendingFloorClearAllEl = document.getElementById("pending-floor-clear-all");
      const pendingFloorBatchSubmitEl = document.getElementById("pending-floor-batch-submit");
      const pendingFloorStatusEl = document.getElementById("pending-floor-status");
      const pendingFloorListEl = document.getElementById("pending-floor-list");
      const historyPendingEl = document.getElementById("history-pending");
      const historyLabeledEl = document.getElementById("history-labeled");
      const pendingOrderHardEl = document.getElementById("pending-order-hard");
      const pendingOrderNewestEl = document.getElementById("pending-order-newest");
      const trainEpochsEl = document.getElementById("train-epochs");
      const trainBatchSizeEl = document.getElementById("train-batch-size");
      const trainLrEl = document.getElementById("train-lr");
      const trainImageSizeEl = document.getElementById("train-image-size");
      const trainFloorEl = document.getElementById("train-floor");
      const trainDirectionEl = document.getElementById("train-direction");
      const reloadModelsEl = document.getElementById("reload-models");
      const floorTrainPillEl = document.getElementById("floor-train-pill");
      const directionTrainPillEl = document.getElementById("direction-train-pill");
      const floorTrainMetricEl = document.getElementById("floor-train-metric");
      const directionTrainMetricEl = document.getElementById("direction-train-metric");
      const floorTrainTrendEl = document.getElementById("floor-train-trend");
      const directionTrainTrendEl = document.getElementById("direction-train-trend");
      const floorTrainChartEl = document.getElementById("floor-train-chart");
      const directionTrainChartEl = document.getElementById("direction-train-chart");
      const floorTrainChartEmptyEl = document.getElementById("floor-train-chart-empty");
      const directionTrainChartEmptyEl = document.getElementById("direction-train-chart-empty");
      const floorTrainStatusEl = document.getElementById("floor-train-status");
      const directionTrainStatusEl = document.getElementById("direction-train-status");
      const floorTrainLogEl = document.getElementById("floor-train-log");
      const directionTrainLogEl = document.getElementById("direction-train-log");

      const roiState = {
        frameWidth: 0,
        frameHeight: 0,
        floor: null,
        direction: null,
        initialFloor: null,
        initialDirection: null,
        zoom: 1,
      };
      let currentState = null;
      const dragState = {
        target: null,
        mode: null,
        startX: 0,
        startY: 0,
        startRect: null,
      };
      let refreshInFlight = false;
      let trainingPollHandle = null;
      let currentPendingFloor = null;
      let pendingFloorItems = [];
      let selectedPendingFloorIds = new Set();
      let pendingFloorMode = "pending";
      let pendingFloorOrder = "hard";
      let lastTrainingSignature = "";

      const directionText = {
        up: "上行",
        down: "下行",
        idle: "静止",
        unknown: "未知",
      };
      const sourceText = {
        sample: "样本匹配",
        model: "神经网络",
        ocr: "文字识别",
        template: "模板",
        unknown: "未知",
      };
      const trainingStateText = {
        idle: "空闲",
        running: "训练中",
        succeeded: "完成",
        failed: "失败",
      };

      function formatDirection(value) {
        return directionText[value] ?? value ?? "--";
      }

      function formatSource(value) {
        return sourceText[value] ?? value ?? "--";
      }

      function formatTrainingState(value) {
        return trainingStateText[value] ?? value ?? "--";
      }

      function formatMaybeDirection(value) {
        return value in directionText ? formatDirection(value) : value;
      }

      function formatBackendMessage(message) {
        if (!message) {
          return "";
        }
        const mappings = [
          ["training started", "训练已启动"],
          ["training finished and model reloaded", "训练完成，新模型已加载"],
          ["training finished but model not loaded", "训练完成，但模型未加载"],
          ["model reloaded manually", "已手动重新加载模型"],
          ["training cancelled", "训练已取消"],
        ];
        for (const [needle, localized] of mappings) {
          if (message === needle) {
            return localized;
          }
        }
        const exitCodeMatch = message.match(/training failed with exit code (\\d+)/);
        if (exitCodeMatch) {
          return `训练失败，退出码 ${exitCodeMatch[1]}`;
        }
        if (message.includes("already running")) {
          return "训练任务已在运行";
        }
        return message;
      }

      function showTrainingNotice(message, tone) {
        trainingNoticeEl.textContent = message;
        trainingNoticeEl.className = `notice show ${tone}`;
      }

      function updateHistoryModeButtons() {
        historyPendingEl.classList.toggle("active", pendingFloorMode === "pending");
        historyLabeledEl.classList.toggle("active", pendingFloorMode === "labeled");
        pendingOrderHardEl.classList.toggle("active", pendingFloorOrder === "hard");
        pendingOrderNewestEl.classList.toggle("active", pendingFloorOrder === "newest");
        pendingFloorSubmitEl.textContent = pendingFloorMode === "pending" ? "提交标注" : "更新标注";
        pendingBatchActionsEl.style.display = pendingFloorMode === "pending" ? "flex" : "none";
        pendingOrderHardEl.disabled = pendingFloorMode !== "pending";
        pendingOrderNewestEl.disabled = pendingFloorMode !== "pending";
      }

      function setMetricSummary(element, task) {
        const accuracy = task.last_accuracy;
        const samples = task.num_samples;
        element.className = "training-metric";
        if (accuracy == null && samples == null) {
          element.textContent = "暂无训练结果。";
          return;
        }
        const parts = [];
        if (samples != null) {
          parts.push(`样本数 ${samples}`);
        }
        if (accuracy != null) {
          parts.push(`最近准确率 ${(accuracy * 100).toFixed(1)}%`);
          if (accuracy >= 0.9) {
            element.classList.add("strong-ok");
          } else if (accuracy < 0.75) {
            element.classList.add("strong-warn");
          }
        }
        element.textContent = parts.join(" | ");
      }

      function setTrendSummary(element, task) {
        element.className = "training-trend";
        if (task.last_accuracy == null || task.previous_accuracy == null || !task.accuracy_trend) {
          element.textContent = "等待对比结果。";
          return;
        }
        if (task.accuracy_trend === "better") {
          element.classList.add("better");
          element.textContent = `比上次提升 ${((task.last_accuracy - task.previous_accuracy) * 100).toFixed(1)}%`;
          return;
        }
        if (task.accuracy_trend === "worse") {
          element.classList.add("worse");
          element.textContent = `比上次下降 ${((task.previous_accuracy - task.last_accuracy) * 100).toFixed(1)}%`;
          return;
        }
        element.classList.add("same");
        element.textContent = "与上次基本持平";
      }

      function formatPercent(value) {
        return `${(value * 100).toFixed(1)}%`;
      }

      function renderTrendChart(svgEl, emptyEl, task) {
        const history = (task.history ?? []).filter((item) => Number.isFinite(item.accuracy));
        if (history.length < 2) {
          svgEl.style.display = "none";
          svgEl.innerHTML = "";
          emptyEl.style.display = "block";
          emptyEl.textContent = "至少训练两次后显示趋势图。";
          return;
        }

        const width = 320;
        const height = 120;
        const padLeft = 22;
        const padRight = 12;
        const padTop = 14;
        const padBottom = 22;
        const values = history.map((item) => item.accuracy);
        const minValue = Math.max(0, Math.min(...values) - 0.03);
        const maxValue = Math.min(1, Math.max(...values) + 0.03);
        const span = Math.max(0.02, maxValue - minValue);
        const xStep = history.length === 1 ? 0 : (width - padLeft - padRight) / (history.length - 1);
        const toX = (index) => padLeft + xStep * index;
        const toY = (value) => {
          const ratio = (value - minValue) / span;
          return height - padBottom - ratio * (height - padTop - padBottom);
        };
        const points = history.map((item, index) => ({
          x: toX(index),
          y: toY(item.accuracy),
          accuracy: item.accuracy,
          label: new Date(item.finished_at).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" }),
        }));
        const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
        const areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(1)} ${(height - padBottom).toFixed(1)} L ${points[0].x.toFixed(1)} ${(height - padBottom).toFixed(1)} Z`;
        const guides = [0, 0.5, 1].map((ratio) => {
          const y = padTop + ratio * (height - padTop - padBottom);
          const value = maxValue - ratio * span;
          return `
            <line x1="${padLeft}" y1="${y.toFixed(1)}" x2="${width - padRight}" y2="${y.toFixed(1)}" stroke="rgba(23,32,42,0.12)" stroke-width="1" />
            <text x="4" y="${(y + 4).toFixed(1)}" fill="#6f7880" font-size="10">${formatPercent(value)}</text>
          `;
        }).join("");
        const labels = points.map((point, index) => {
          const anchor = index === 0 ? "start" : index === points.length - 1 ? "end" : "middle";
          return `<text x="${point.x.toFixed(1)}" y="${(height - 6).toFixed(1)}" text-anchor="${anchor}" fill="#6f7880" font-size="10">${point.label}</text>`;
        }).join("");
        const dots = points.map((point) => `
          <circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="3.5" fill="#176087">
            <title>${point.label} ${formatPercent(point.accuracy)}</title>
          </circle>
        `).join("");

        svgEl.innerHTML = `
          ${guides}
          <path d="${areaPath}" fill="rgba(23,96,135,0.12)"></path>
          <path d="${linePath}" fill="none" stroke="#176087" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></path>
          ${dots}
          ${labels}
        `;
        emptyEl.style.display = "none";
        svgEl.style.display = "block";
      }

      function extractLatestAccuracy(logTail) {
        if (!logTail || !logTail.length) {
          return null;
        }
        for (let index = logTail.length - 1; index >= 0; index -= 1) {
          const match = String(logTail[index]).match(/acc=([0-9.]+)/);
          if (match) {
            return Number(match[1]);
          }
        }
        return null;
      }

      function setTrainingPill(element, state) {
        element.textContent = formatTrainingState(state);
        element.className = `status-pill status-pill-${state ?? "idle"}`;
      }

      async function refreshImage(element, url) {
        const separator = url.includes("?") ? "&" : "?";
        const response = await fetch(`${url}${separator}ts=${Date.now()}`, {
          cache: "no-store",
        });
        if (!response.ok) {
          return;
        }
        const blob = await response.blob();
        const nextUrl = URL.createObjectURL(blob);
        const previousUrl = element.dataset.objectUrl;
        element.src = nextUrl;
        element.dataset.objectUrl = nextUrl;
        if (previousUrl) {
          URL.revokeObjectURL(previousUrl);
        }
      }

      async function refreshVisuals() {
        if (refreshInFlight) {
          return;
        }
        refreshInFlight = true;
        try {
          await Promise.all([
            refreshImage(snapshotEl, "/api/v1/frame.jpg"),
            refreshImage(floorPreviewEl, "/api/v1/frame/floor.jpg"),
            refreshImage(directionPreviewEl, "/api/v1/frame/direction.jpg"),
          ]);
        } finally {
          refreshInFlight = false;
        }
      }

      function setFeedbackStatus(element, message, tone = "") {
        element.textContent = message;
        element.className = `feedback-status${tone ? " " + tone : ""}`;
      }

      function renderCoverage(payload) {
        const covered = payload?.covered_floors ?? 0;
        const total = payload?.total_floors ?? 0;
        const labeled = payload?.total_labeled ?? 0;
        floorCoverageSummaryEl.textContent = `楼层覆盖 ${covered} / ${total}，累计样本 ${labeled}`;
        const items = payload?.items ?? [];
        if (!items.length) {
          floorCoverageGridEl.innerHTML = '<div class="feedback-status">还没有楼层覆盖数据。</div>';
          return;
        }
        floorCoverageGridEl.innerHTML = items.map((item) => {
          const tone = item.count === 0 ? "empty" : item.count < 3 ? "low" : "good";
          return `
            <div class="coverage-chip ${tone}">
              <strong>${item.floor}</strong>
              <span>${item.count} 张</span>
            </div>
          `;
        }).join("");
      }

      async function refreshFeedbackStats() {
        const [feedbackResponse, pendingResponse, coverageResponse] = await Promise.all([
          fetch("/api/v1/feedback/stats", { cache: "no-store" }),
          fetch("/api/v1/pending/stats", { cache: "no-store" }),
          fetch("/api/v1/feedback/coverage", { cache: "no-store" }),
        ]);
        if (!feedbackResponse.ok || !pendingResponse.ok || !coverageResponse.ok) {
          return;
        }
        const [feedbackStats, pendingStats, coverageStats] = await Promise.all([
          feedbackResponse.json(),
          pendingResponse.json(),
          coverageResponse.json(),
        ]);
        feedbackStatsEl.textContent = `已标楼层 ${feedbackStats.floor}，已标方向 ${feedbackStats.direction}，待标楼层 ${pendingStats.floor}`;
        renderCoverage(coverageStats);
      }

      function renderCandidateList(element, candidates) {
        if (!candidates || candidates.length === 0) {
          element.innerHTML = "<li>还没有候选结果。</li>";
          return;
        }
        element.innerHTML = candidates
          .map((item) => `<li>${formatMaybeDirection(item.label)} | ${(item.score * 100).toFixed(1)} 分 | ${formatSource(item.source)}</li>`)
          .join("");
      }

      async function refreshRecognitionDebug() {
        const response = await fetch("/api/v1/debug/recognition", { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const payload = await response.json();
        if (!payload) {
          debugFloorSourceEl.textContent = "楼层来源：--";
          debugDirectionSourceEl.textContent = "方向来源：--";
          renderCandidateList(debugFloorCandidatesEl, []);
          renderCandidateList(debugDirectionCandidatesEl, []);
          return;
        }
        debugFloorSourceEl.textContent = `楼层来源：${formatSource(payload.floor_source)}`;
        debugDirectionSourceEl.textContent = `方向来源：${formatSource(payload.direction_source)}`;
        renderCandidateList(debugFloorCandidatesEl, payload.floor_candidates);
        renderCandidateList(debugDirectionCandidatesEl, payload.direction_candidates);
      }

      async function loadPendingFloor() {
        const response = await fetch(`/api/v1/pending/next?kind=floor&order=${pendingFloorOrder}`, { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const sample = await response.json();
        renderPendingFloor(sample);
      }

      function renderPendingFloor(sample) {
        currentPendingFloor = sample;
        setFeedbackStatus(pendingFloorStatusEl, "");
        if (!sample) {
          pendingFloorImageEl.removeAttribute("src");
          pendingFloorMetaEl.textContent = pendingFloorMode === "pending" ? "当前没有待标楼层样本。" : "当前没有已标楼层样本。";
          pendingFloorLabelInputEl.value = "";
          return;
        }
        pendingFloorMetaEl.textContent = pendingFloorMode === "pending"
          ? `预测 ${sample.predicted_label ?? "--"} | 置信度 ${sample.confidence ?? "--"} | 采集时间 ${new Date(sample.created_at).toLocaleString()}`
          : `预测 ${sample.predicted_label ?? "--"} | 标注 ${sample.confirmed_label ?? "--"} | 标注时间 ${sample.labeled_at ? new Date(sample.labeled_at).toLocaleString() : "--"}`;
        pendingFloorLabelInputEl.value = pendingFloorMode === "pending"
          ? (sample.predicted_label ?? "")
          : (sample.confirmed_label ?? sample.predicted_label ?? "");
        refreshImage(pendingFloorImageEl, sample.image_url);
        renderPendingFloorList();
      }

      async function refreshPendingFloorList() {
        const order = pendingFloorMode === "pending" ? pendingFloorOrder : "newest";
        const response = await fetch(`/api/v1/pending/list?kind=floor&status=${pendingFloorMode}&order=${order}&limit=80`, { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const payload = await response.json();
        pendingFloorItems = payload.items ?? [];
        selectedPendingFloorIds = new Set(
          [...selectedPendingFloorIds].filter((itemId) => pendingFloorItems.some((item) => item.id === itemId))
        );
        if (!currentPendingFloor && pendingFloorItems.length) {
          renderPendingFloor(pendingFloorItems[0]);
          return;
        }
        const stillExists = currentPendingFloor
          ? pendingFloorItems.find((item) => item.id === currentPendingFloor.id)
          : null;
        if (currentPendingFloor && !stillExists) {
          renderPendingFloor(pendingFloorItems[0] ?? null);
          return;
        }
        renderPendingFloorList();
      }

      function renderPendingFloorList() {
        if (!pendingFloorItems.length) {
          pendingFloorListEl.innerHTML = pendingFloorMode === "pending"
            ? '<div class="feedback-status">还没有待标历史样本。</div>'
            : '<div class="feedback-status">还没有已标历史样本。</div>';
          return;
        }
        pendingFloorListEl.innerHTML = pendingFloorItems
          .map((item) => {
            const active = currentPendingFloor?.id === item.id ? " active" : "";
            const confidence = item.confidence == null ? "--" : Number(item.confidence).toFixed(1);
            const summary = pendingFloorMode === "pending"
              ? `${confidence} | ${new Date(item.created_at).toLocaleString()}`
              : `${item.confirmed_label ?? "--"} | ${item.labeled_at ? new Date(item.labeled_at).toLocaleString() : "--"}`;
            const title = pendingFloorMode === "pending" ? (item.predicted_label ?? "--") : (item.confirmed_label ?? "--");
            const checkbox = pendingFloorMode === "pending"
              ? `<input class="pending-check" type="checkbox" data-select-pending-id="${item.id}" ${selectedPendingFloorIds.has(item.id) ? "checked" : ""}>`
              : "";
            return `
              <div class="pending-item${active}" data-pending-id="${item.id}">
                ${checkbox}
                <img class="pending-thumb" src="${item.image_url}" alt="待标楼层样本 ${item.id}">
                <span class="pending-item-meta">
                  <strong>${title}</strong>
                  <span>${summary}</span>
                </span>
              </div>
            `;
          })
          .join("");
      }

      async function submitPendingFloor(label, acceptedPrediction, button) {
        if (!currentPendingFloor) {
          setFeedbackStatus(pendingFloorStatusEl, pendingFloorMode === "pending" ? "没有可提交的待标样本" : "没有可更新的已标样本", "bad");
          return;
        }
        const previous = button.textContent;
        button.disabled = true;
        button.textContent = "提交中";
        try {
          const response = await fetch(`/api/v1/pending/${currentPendingFloor.id}/label`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              confirmed_label: label,
              accepted_prediction: acceptedPrediction,
            }),
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) {
            setFeedbackStatus(pendingFloorStatusEl, formatBackendMessage(payload.error) || "提交失败", "bad");
            return;
          }
          setFeedbackStatus(
            pendingFloorStatusEl,
            pendingFloorMode === "pending" ? `已保存为 ${label}` : `已更新为 ${label}`,
            "ok",
          );
          await Promise.all([refreshFeedbackStats(), refreshPendingFloorList()]);
        } finally {
          button.disabled = false;
          button.textContent = previous;
        }
      }

      async function submitPendingFloorBatch(button) {
        const sampleIds = pendingFloorItems
          .filter((item) => selectedPendingFloorIds.has(item.id) && item.predicted_label)
          .map((item) => item.id);
        if (!sampleIds.length) {
          setFeedbackStatus(pendingFloorStatusEl, "请先勾选要批量提交的待标样本", "bad");
          return;
        }
        const previous = button.textContent;
        button.disabled = true;
        button.textContent = "提交中";
        try {
          const response = await fetch("/api/v1/pending/batch-label", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sample_ids: sampleIds }),
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) {
            setFeedbackStatus(pendingFloorStatusEl, formatBackendMessage(payload.error) || "批量提交失败", "bad");
            return;
          }
          selectedPendingFloorIds = new Set();
          setFeedbackStatus(pendingFloorStatusEl, `已批量提交 ${payload.accepted ?? 0} 张样本`, "ok");
          await Promise.all([refreshFeedbackStats(), refreshPendingFloorList()]);
        } finally {
          button.disabled = false;
          button.textContent = previous;
        }
      }

      async function submitFeedback(kind, label, acceptedPrediction, button) {
        const statusEl = kind === "floor" ? floorFeedbackStatusEl : directionFeedbackStatusEl;
        const previous = button.textContent;
        button.disabled = true;
        button.textContent = "提交中";
        setFeedbackStatus(statusEl, "");
        try {
          const response = await fetch("/api/v1/feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ kind, label, accepted_prediction: acceptedPrediction }),
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) {
            setFeedbackStatus(statusEl, formatBackendMessage(payload.error) || "提交失败", "bad");
            return;
          }
          setFeedbackStatus(statusEl, `已保存：${kind === "direction" ? formatDirection(label) : label}`, "ok");
          await refreshFeedbackStats();
        } catch {
          setFeedbackStatus(statusEl, "提交失败", "bad");
        } finally {
          button.disabled = false;
          button.textContent = previous;
        }
      }

      function formatWhen(value) {
        if (!value) {
          return "-";
        }
        return new Date(value).toLocaleString();
      }

      function renderTrainingTask(task, statusEl, logEl, pillEl, metricEl, trendEl, chartEl, chartEmptyEl) {
        const tone = task.state === "failed" ? "bad" : task.state === "succeeded" ? "ok" : "";
        const loaded = task.model_loaded ? "已加载" : "未加载";
        const message = formatBackendMessage(task.message);
        setTrainingPill(pillEl, task.state);
        setMetricSummary(metricEl, task);
        setTrendSummary(trendEl, task);
        renderTrendChart(chartEl, chartEmptyEl, task);
        setFeedbackStatus(
          statusEl,
          `${formatTrainingState(task.state)} | 开始 ${formatWhen(task.started_at)} | 结束 ${formatWhen(task.finished_at)} | ${loaded}${message ? " | " + message : ""}`,
          tone,
        );
        logEl.textContent = task.log_tail.length ? task.log_tail.join("\\n") : "还没有训练日志。";
      }

      async function refreshTrainingStatus() {
        const response = await fetch("/api/v1/training/status", { cache: "no-store" });
        if (!response.ok) {
          return;
        }
        const payload = await response.json();
        renderTrainingTask(
          payload.floor,
          floorTrainStatusEl,
          floorTrainLogEl,
          floorTrainPillEl,
          floorTrainMetricEl,
          floorTrainTrendEl,
          floorTrainChartEl,
          floorTrainChartEmptyEl,
        );
        renderTrainingTask(
          payload.direction,
          directionTrainStatusEl,
          directionTrainLogEl,
          directionTrainPillEl,
          directionTrainMetricEl,
          directionTrainTrendEl,
          directionTrainChartEl,
          directionTrainChartEmptyEl,
        );
        const overview =
          payload.floor.state === "running" || payload.direction.state === "running"
            ? "训练中"
            : payload.floor.state === "failed" || payload.direction.state === "failed"
              ? "失败"
              : payload.floor.state === "succeeded" || payload.direction.state === "succeeded"
                ? "已完成"
                : "空闲";
        trainingOverviewEl.textContent = overview;
        const signature = [
          payload.floor.state,
          payload.floor.finished_at,
          payload.direction.state,
          payload.direction.finished_at,
        ].join("|");
        if (signature !== lastTrainingSignature) {
          lastTrainingSignature = signature;
          if (payload.floor.state === "running" || payload.direction.state === "running") {
            showTrainingNotice("模型训练正在进行中，页面会自动刷新训练状态。", "info");
          } else if (payload.floor.state === "failed" || payload.direction.state === "failed") {
            showTrainingNotice("模型训练失败，请查看下方日志。", "bad");
          } else if (payload.floor.state === "succeeded" || payload.direction.state === "succeeded") {
            const better = payload.floor.accuracy_trend === "better" || payload.direction.accuracy_trend === "better";
            const worse = payload.floor.accuracy_trend === "worse" || payload.direction.accuracy_trend === "worse";
            showTrainingNotice(
              better
                ? "模型训练完成，本次效果优于上次。"
                : worse
                  ? "模型训练完成，但本次效果低于上次。"
                  : "模型训练完成，新结果已刷新到页面。",
              better ? "ok" : worse ? "bad" : "info",
            );
          }
        }

        const running = payload.floor.state === "running" || payload.direction.state === "running";
        if (running && !trainingPollHandle) {
          trainingPollHandle = setInterval(refreshTrainingStatus, 1500);
        }
        if (!running && trainingPollHandle) {
          clearInterval(trainingPollHandle);
          trainingPollHandle = null;
        }
      }

      function trainingPayload(task) {
        return {
          task,
          epochs: Number(trainEpochsEl.value),
          batch_size: Number(trainBatchSizeEl.value),
          lr: Number(trainLrEl.value),
          image_size: Number(trainImageSizeEl.value),
        };
      }

      async function startTraining(task, button) {
        const previous = button.textContent;
        button.disabled = true;
        button.textContent = "启动中";
        try {
          const response = await fetch("/api/v1/training", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(trainingPayload(task)),
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) {
            const statusEl = task === "floor" ? floorTrainStatusEl : directionTrainStatusEl;
            setFeedbackStatus(statusEl, formatBackendMessage(payload.error) || "训练启动失败", "bad");
            return;
          }
          await refreshTrainingStatus();
        } finally {
          button.disabled = false;
          button.textContent = previous;
        }
      }

      async function reloadModels(button) {
        const previous = button.textContent;
        button.disabled = true;
        button.textContent = "重载中";
        try {
          await fetch("/api/v1/models/reload", { method: "POST" });
          await refreshTrainingStatus();
        } finally {
          button.disabled = false;
          button.textContent = previous;
        }
      }

      function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
      }

      function cloneRect(rect) {
        return {
          x: rect.x,
          y: rect.y,
          w: rect.w,
          h: rect.h,
          angle: rect.angle ?? 0,
        };
      }

      function roiEnvLine(name, rect) {
        return `${name}=${rect.x},${rect.y},${rect.w},${rect.h},${rect.angle.toFixed(1)}`;
      }

      function updateZoom(value) {
        roiState.zoom = clamp(Number(value), 0.1, 3);
        if (!roiState.frameWidth || !roiState.frameHeight) {
          return;
        }
        stageEl.style.width = `${Math.round(roiState.frameWidth * roiState.zoom)}px`;
        stageEl.style.height = `${Math.round(roiState.frameHeight * roiState.zoom)}px`;
        zoomSliderEl.value = String(roiState.zoom);
        zoomReadoutEl.textContent = `${Math.round(roiState.zoom * 100)}%`;
      }

      function fitZoom() {
        if (!roiState.frameWidth) {
          return;
        }
        const fit = viewportEl.clientWidth / roiState.frameWidth;
        updateZoom(clamp(fit || 1, 0.1, 3));
      }

      async function copyText(text, button) {
        const original = button.textContent;
        try {
          await navigator.clipboard.writeText(text);
          button.textContent = "已复制";
          setTimeout(() => { button.textContent = original; }, 1200);
        } catch {
          button.textContent = "复制失败";
          setTimeout(() => { button.textContent = original; }, 1200);
        }
      }

      function renderRoiBox(element, rect) {
        if (!rect || !roiState.frameWidth || !roiState.frameHeight) {
          element.style.display = "none";
          return;
        }
        element.style.display = "block";
        element.style.left = `${(rect.x / roiState.frameWidth) * 100}%`;
        element.style.top = `${(rect.y / roiState.frameHeight) * 100}%`;
        element.style.width = `${(rect.w / roiState.frameWidth) * 100}%`;
        element.style.height = `${(rect.h / roiState.frameHeight) * 100}%`;
        element.style.transform = `rotate(${rect.angle}deg)`;
        element.style.transformOrigin = "center center";
      }

      function renderRoiPanel() {
        renderRoiBox(floorRoiEl, roiState.floor);
        renderRoiBox(directionRoiEl, roiState.direction);
        floorRoiTextEl.textContent = roiState.floor ? roiEnvLine("FLOOR_ROI", roiState.floor) : "FLOOR_ROI=--";
        directionRoiTextEl.textContent = roiState.direction ? roiEnvLine("DIRECTION_ROI", roiState.direction) : "DIRECTION_ROI=--";
      }

      function getRectByTarget(target) {
        return target === "floor" ? roiState.floor : roiState.direction;
      }

      function setRectByTarget(target, rect) {
        if (target === "floor") {
          roiState.floor = rect;
        } else {
          roiState.direction = rect;
        }
      }

      function onPointerDown(event) {
        const roiEl = event.target.closest(".roi");
        if (!roiEl || !roiState.frameWidth || !roiState.frameHeight) {
          return;
        }
        const target = roiEl.id === "floor-roi" ? "floor" : "direction";
        dragState.target = target;
        dragState.mode = event.target.dataset.role === "resize" ? "resize" : "move";
        dragState.startX = event.clientX;
        dragState.startY = event.clientY;
        dragState.startRect = cloneRect(getRectByTarget(target));
        floorRoiEl.classList.toggle("active", target === "floor");
        directionRoiEl.classList.toggle("active", target === "direction");
        roiEl.setPointerCapture(event.pointerId);
        event.preventDefault();
      }

      function onPointerMove(event) {
        if (!dragState.target || !dragState.startRect) {
          return;
        }
        const bounds = snapshotEl.getBoundingClientRect();
        if (!bounds.width || !bounds.height) {
          return;
        }

        const deltaX = ((event.clientX - dragState.startX) / bounds.width) * roiState.frameWidth;
        const deltaY = ((event.clientY - dragState.startY) / bounds.height) * roiState.frameHeight;
        const next = cloneRect(dragState.startRect);

        if (dragState.mode === "move") {
          next.x = clamp(Math.round(dragState.startRect.x + deltaX), 0, roiState.frameWidth - next.w);
          next.y = clamp(Math.round(dragState.startRect.y + deltaY), 0, roiState.frameHeight - next.h);
        } else {
          next.w = clamp(Math.round(dragState.startRect.w + deltaX), 1, roiState.frameWidth - next.x);
          next.h = clamp(Math.round(dragState.startRect.h + deltaY), 1, roiState.frameHeight - next.y);
        }

        setRectByTarget(dragState.target, next);
        renderRoiPanel();
      }

      function onPointerUp() {
        dragState.target = null;
        dragState.mode = null;
        dragState.startRect = null;
      }

      async function loadRoi() {
        const response = await fetch("/api/v1/roi");
        const data = await response.json();
        roiState.floor = data.floor_roi;
        roiState.direction = data.direction_roi;
        roiState.initialFloor = cloneRect(data.floor_roi);
        roiState.initialDirection = cloneRect(data.direction_roi);

        if (data.frame_size) {
          roiState.frameWidth = data.frame_size.width;
          roiState.frameHeight = data.frame_size.height;
          fitZoom();
          renderRoiPanel();
          return;
        }

        await new Promise((resolve) => {
          if (snapshotEl.complete && snapshotEl.naturalWidth) {
            resolve();
            return;
          }
          snapshotEl.addEventListener("load", resolve, { once: true });
        });
        roiState.frameWidth = snapshotEl.naturalWidth;
        roiState.frameHeight = snapshotEl.naturalHeight;
        fitZoom();
        renderRoiPanel();
      }

      function render(state) {
        currentState = state;
        floorEl.textContent = state.floor ?? "--";
        directionEl.textContent = formatDirection(state.direction);
        streamEl.textContent = state.stream_connected ? "已连接" : "未连接";
        streamEl.className = "value " + (state.stream_connected ? "status-ok" : "status-bad");
        updatedEl.textContent = "最后更新：" + new Date(state.published_ts).toLocaleString();
        floorPredictionEl.textContent = state.floor ?? "--";
        floorInlinePredictionEl.textContent = state.floor ?? "--";
        directionPredictionEl.textContent = formatDirection(state.direction);
        directionInlinePredictionEl.textContent = formatDirection(state.direction);
        directionLabelInputEl.value = state.direction ?? "unknown";
        refreshVisuals();
      }

      async function bootstrap() {
        const [stateResponse] = await Promise.all([
          fetch("/api/v1/state"),
          loadRoi(),
          refreshFeedbackStats(),
          refreshPendingFloorList(),
          refreshRecognitionDebug(),
          refreshTrainingStatus(),
        ]);
        render(await stateResponse.json());
      }

      bootstrap().catch(() => {
        updatedEl.textContent = "加载当前状态失败。";
      });
      updateHistoryModeButtons();

      const source = new EventSource("/api/v1/events/stream");
      source.addEventListener("state", (event) => {
        render(JSON.parse(event.data));
      });
      source.onerror = () => {
        updatedEl.textContent = "实时状态流已断开，正在重连...";
      };

      setInterval(refreshVisuals, 350);
      setInterval(refreshRecognitionDebug, 1000);
      overlayEl.addEventListener("pointerdown", onPointerDown);
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
      window.addEventListener("pointercancel", onPointerUp);

      copyFloorEl.addEventListener("click", () => copyText(floorRoiTextEl.textContent, copyFloorEl));
      copyDirectionEl.addEventListener("click", () => copyText(directionRoiTextEl.textContent, copyDirectionEl));
      copyBothEl.addEventListener("click", () => copyText(`${floorRoiTextEl.textContent}\\n${directionRoiTextEl.textContent}`, copyBothEl));
      resetRoiEl.addEventListener("click", () => {
        if (!roiState.initialFloor || !roiState.initialDirection) {
          return;
        }
        roiState.floor = cloneRect(roiState.initialFloor);
        roiState.direction = cloneRect(roiState.initialDirection);
        renderRoiPanel();
      });
      floorRotateMinusEl.addEventListener("click", () => {
        roiState.floor.angle = Number((roiState.floor.angle - 1).toFixed(1));
        renderRoiPanel();
      });
      floorRotatePlusEl.addEventListener("click", () => {
        roiState.floor.angle = Number((roiState.floor.angle + 1).toFixed(1));
        renderRoiPanel();
      });
      directionRotateMinusEl.addEventListener("click", () => {
        roiState.direction.angle = Number((roiState.direction.angle - 1).toFixed(1));
        renderRoiPanel();
      });
      directionRotatePlusEl.addEventListener("click", () => {
        roiState.direction.angle = Number((roiState.direction.angle + 1).toFixed(1));
        renderRoiPanel();
      });
      floorAcceptEl.addEventListener("click", () => {
        if (!currentState?.floor) {
          setFeedbackStatus(floorFeedbackStatusEl, "当前没有可保存的楼层预测", "bad");
          return;
        }
        submitFeedback("floor", currentState.floor, true, floorAcceptEl);
      });
      floorSubmitEl.addEventListener("click", () => {
        const label = floorLabelInputEl.value.trim();
        if (!label) {
          setFeedbackStatus(floorFeedbackStatusEl, "请输入楼层标注", "bad");
          return;
        }
        submitFeedback("floor", label, currentState?.floor === label, floorSubmitEl);
      });
      directionAcceptEl.addEventListener("click", () => {
        const label = currentState?.direction ?? "unknown";
        submitFeedback("direction", label, true, directionAcceptEl);
      });
      directionSubmitEl.addEventListener("click", () => {
        const label = directionLabelInputEl.value;
        submitFeedback("direction", label, currentState?.direction === label, directionSubmitEl);
      });
      pendingFloorSubmitEl.addEventListener("click", () => {
        const label = pendingFloorLabelInputEl.value.trim();
        if (!label) {
          setFeedbackStatus(pendingFloorStatusEl, "请输入楼层标注", "bad");
          return;
        }
        submitPendingFloor(label, currentPendingFloor?.predicted_label === label, pendingFloorSubmitEl);
      });
      pendingFloorNextEl.addEventListener("click", () => {
        if (!pendingFloorItems.length) {
          loadPendingFloor();
          return;
        }
        const currentIndex = pendingFloorItems.findIndex((item) => item.id === currentPendingFloor?.id);
        const nextIndex = currentIndex >= 0 ? Math.min(pendingFloorItems.length - 1, currentIndex + 1) : 0;
        renderPendingFloor(pendingFloorItems[nextIndex] ?? null);
      });
      pendingFloorListEl.addEventListener("click", (event) => {
        const checkbox = event.target.closest("[data-select-pending-id]");
        if (checkbox) {
          const sampleId = checkbox.dataset.selectPendingId;
          if (checkbox.checked) {
            selectedPendingFloorIds.add(sampleId);
          } else {
            selectedPendingFloorIds.delete(sampleId);
          }
          return;
        }
        const button = event.target.closest("[data-pending-id]");
        if (!button) {
          return;
        }
        const sample = pendingFloorItems.find((item) => item.id === button.dataset.pendingId);
        if (sample) {
          renderPendingFloor(sample);
        }
      });
      historyPendingEl.addEventListener("click", () => {
        pendingFloorMode = "pending";
        currentPendingFloor = null;
        selectedPendingFloorIds = new Set();
        updateHistoryModeButtons();
        refreshPendingFloorList();
      });
      historyLabeledEl.addEventListener("click", () => {
        pendingFloorMode = "labeled";
        currentPendingFloor = null;
        selectedPendingFloorIds = new Set();
        updateHistoryModeButtons();
        refreshPendingFloorList();
      });
      pendingOrderHardEl.addEventListener("click", () => {
        pendingFloorOrder = "hard";
        currentPendingFloor = null;
        updateHistoryModeButtons();
        refreshPendingFloorList();
      });
      pendingOrderNewestEl.addEventListener("click", () => {
        pendingFloorOrder = "newest";
        currentPendingFloor = null;
        updateHistoryModeButtons();
        refreshPendingFloorList();
      });
      pendingFloorSelectAllEl.addEventListener("click", () => {
        selectedPendingFloorIds = new Set(
          pendingFloorItems.filter((item) => item.predicted_label).map((item) => item.id)
        );
        renderPendingFloorList();
      });
      pendingFloorClearAllEl.addEventListener("click", () => {
        selectedPendingFloorIds = new Set();
        renderPendingFloorList();
      });
      pendingFloorBatchSubmitEl.addEventListener("click", () => submitPendingFloorBatch(pendingFloorBatchSubmitEl));
      trainFloorEl.addEventListener("click", () => startTraining("floor", trainFloorEl));
      trainDirectionEl.addEventListener("click", () => startTraining("direction", trainDirectionEl));
      reloadModelsEl.addEventListener("click", () => reloadModels(reloadModelsEl));
      zoomSliderEl.addEventListener("input", (event) => updateZoom(event.target.value));
      zoomOutEl.addEventListener("click", () => updateZoom(roiState.zoom - 0.1));
      zoomInEl.addEventListener("click", () => updateZoom(roiState.zoom + 0.1));
      zoomFitEl.addEventListener("click", fitZoom);
      zoom100El.addEventListener("click", () => updateZoom(1));
      window.addEventListener("resize", () => {
        if (Math.abs(roiState.zoom - (viewportEl.clientWidth / (roiState.frameWidth || 1))) < 0.03) {
          fitZoom();
        }
      });
    </script>
  </body>
</html>
"""
