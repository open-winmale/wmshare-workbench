/**
 * 自动生成文件 —— 禁止手改。
 *
 * 真源：backend/workbench/core/envelope.py
 * 重新生成：make gen-contract
 * 漂移检查：gates/check_contract.py（CI 强制）
 *
 * 为什么生成：手写双份 TS 类型与后端契约必然漂移，且漂移只会在运行时
 * 表现为 undefined。见 docs/ADR/002。
 */

export const ENVELOPE_VERSION = 1;

//: 信封字段集（顺序即后端构造顺序）
export const ENVELOPE_FIELDS = ["ok", "as_of", "data", "meta", "freshness", "warnings", "ec"] as const;
export type EnvelopeField = (typeof ENVELOPE_FIELDS)[number];

//: 数据新鲜度档位
export const FRESHNESS_VALUES = ["fresh", "stale", "expired", "unknown"] as const;
export type FreshnessValue = (typeof FRESHNESS_VALUES)[number];

//: 失败时可采取的处置动作（决定错误态按钮）
export const ERROR_ACTIONS = ["retry", "topup", "config", "fix_input", "report"] as const;
export type ErrorAction = (typeof ERROR_ACTIONS)[number];

//: ec 子结构字段
export const EC_FIELDS = ["pred_lo", "pred_hi", "actual", "model"] as const;
export type EcField = (typeof EC_FIELDS)[number];

export interface EcEstimate {
  /** 无成本模型时为 null —— **不是 0**（0 会被读成「免费」） */
  pred_lo: number | null;
  pred_hi: number | null;
  /** 实际消耗，来自后端 meta.metering */
  actual: number | null;
  /** 成本模型名；无模型时 "none" */
  model: string;
}

export interface Envelope<T = unknown> {
  ok: boolean;
  /** 数据截至日 YYYY-MM-DD；未知为 "" */
  as_of: string;
  /** 载荷。ok=false 时后端保证为 {}（失败原因在 meta） */
  data: T;
  meta: Record<string, unknown>;
  freshness: FreshnessValue;
  /** 中文告警，逐条可读 */
  warnings: string[];
  ec: EcEstimate | null;
}

/** 失败信封的 meta 约定字段 */
export interface ErrorMeta {
  error?: string;
  code?: string;
  action?: ErrorAction;
}

//: 端点清单（前端不得手写端点字符串）
export const ENDPOINTS = {
  appinfo: { method: "GET", path: "/api/appinfo", summary: "版本/演示态/凭证状态" },
  assistant: { method: "GET", path: "/api/assistant/info", summary: "AI 助手：配置状态与领域清单" },
  assistant_chat: { method: "POST", path: "/api/assistant/chat", summary: "AI 助手：发起一轮提问（返回 job_id）" },
  assistant_session: { method: "POST", path: "/api/assistant/session", summary: "AI 助手：读取或删除一个会话" },
  assistant_sessions: { method: "GET", path: "/api/assistant/sessions", summary: "AI 助手：会话列表" },
  assistant_stop: { method: "POST", path: "/api/assistant/stop", summary: "AI 助手：停止运行中的任务" },
  assistant_stream: { method: "GET", path: "/api/assistant/stream", summary: "AI 助手：轮询任务进度与部分结果" },
  backtest: { method: "POST", path: "/api/backtest/run", summary: "单标的回测" },
  dashboard: { method: "POST", path: "/api/dashboard/run", summary: "每日驾驶舱" },
  ec_estimate: { method: "POST", path: "/api/ec/estimate", summary: "EC 试算" },
  economics: { method: "POST", path: "/api/economics/run", summary: "宏观时序与曲线" },
  equity: { method: "POST", path: "/api/equity/run", summary: "个股研究" },
  health: { method: "GET", path: "/api/health", summary: "hub/db/wmshare 三态" },
  key: { method: "POST", path: "/api/key", summary: "热切凭证" },
  markets: { method: "POST", path: "/api/markets/run", summary: "行情表与 KPI" },
  portfolio: { method: "POST", path: "/api/portfolio/run", summary: "持仓账本" },
  screener: { method: "POST", path: "/api/screener/run", summary: "条件选股" },
  sources: { method: "POST", path: "/api/sources/run", summary: "数据源与新鲜度总览" },
  tools: { method: "GET", path: "/api/tools", summary: "工具注册表" },
  watchlist: { method: "POST", path: "/api/watchlist/run", summary: "自选批量行情" },
} as const;

export type EndpointSlug = keyof typeof ENDPOINTS;
