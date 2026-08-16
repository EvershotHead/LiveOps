/** 与后端 API JSON 结构对应的类型契约。 */

export type RunSummary = {
  run_id: string;
  study_id: string;
  status: string;
  created_at: string;
  models: Record<string, string>;
  cost_cny: number;
};

export type TopicStat = {
  count: number;
  topic_share: number | null;
  net_support_rate: number | null;
  support_rate: number | null;
  controversy: number;
  reply_conflict: number | null;
  trend_speed: number | null;
  daily_counts: number[];
  engagement_raw: number;
  video_count: number;
  video_categories: string[];
  persistence: number;
  ugc_diffusion: number;
  growth_delta: number;
  stance: {
    support: number; oppose: number; neutral: number; mixed: number;
    unclear: number; abstain: number;
  };
};

export type Overview = {
  scope_statement: string;
  study: { study_id: string; game: string; version: string; t0: string };
  dataset: {
    total_posts: number; effective_posts: number; relevant_posts: number;
    videos: number; abstain_count: number; irrelevant_count: number;
  };
  overall: {
    stance: { support: number; oppose: number; neutral: number; mixed: number; unclear: number; abstain: number };
    net_support_rate: number | null;
  };
  topic_shares: { topic: string; share: number | null; count: number; net_support: number | null; controversy: number }[];
  top_risks: { topic: string; score: number }[];
  top_opportunities: { topic: string; score: number }[];
  weights: { issue_priority: Record<string, number>; opportunity: Record<string, number> };
  disclaimer: string;
  limitations?: string[];
};

export type TimelineData = {
  t0: string;
  window: [number, number];
  topics: Record<string, { daily_counts: number[]; trend_speed: number | null }>;
  scope_statement: string;
};

export type ControversyRow = {
  topic: string;
  controversy: number;
  reply_conflict: number | null;
  stance: Record<string, number>;
  net_support: number | null;
  evidence: Record<string, string[]>;
};

export type EvidenceItem = {
  evidence_id: string;
  video_id: string;
  video_title: string;
  video_url: string;
  text_excerpt: string;
  published_at: string;
  likes: number;
  topics: string[];
  stance: string | null;
  emotion: string | null;
  irony: string;
  model_label_stage: string;
  confidence: number;
  human_modified: boolean;
  source_url: string;
};

export type SensitivityData = {
  issue: { base_ranks: Record<string, number>; scenarios: { name: string; weights: Record<string, number>; ranks: Record<string, number>; rank_shift: Record<string, number> }[] } | null;
  opportunity: { base_ranks: Record<string, number>; scenarios: { name: string; weights: Record<string, number>; ranks: Record<string, number>; rank_shift: Record<string, number> }[] } | null;
};

export type CompareRow = {
  topic: string;
  a_per_1000: number | null; a_share: number | null; a_net_support: number | null;
  a_controversy: number | null; a_count: number | null;
  b_per_1000: number | null; b_share: number | null; b_net_support: number | null;
  b_controversy: number | null; b_count: number | null;
};

export type CompareData = {
  a: { run_id: string; game: string; version: string; t0: string; dataset: Overview["dataset"] };
  b: { run_id: string; game: string; version: string; t0: string; dataset: Overview["dataset"] };
  same_relative_window: boolean;
  topic_rows: CompareRow[];
  sample_difference_note: string;
  disclaimer: string;
};

export type ReviewItem = {
  post_id: string;
  text: string;
  published_at: string;
  likes: number;
  parent_id: string | null;
  video_title: string;
  video_url: string;
  current: Record<string, unknown>;
  human_modified: boolean;
  review_count: number;
};

export type EvaluationData = {
  gold_layer: "strong_model_seed" | "human" | "mixed";
  n_gold: number;
  n_evaluated: number;
  relevance?: { macro_f1: number; abstain_rate: number };
  topics?: { macro_f1: number };
  stance?: { macro_f1: number };
  emotion?: { macro_f1: number };
  irony?: { macro_f1: number; abstain_rate: number };
  ece: number | null;
  kappa: number | null;
  cost_cny: number | null;
  throughput_per_min: number | null;
  confusion: Record<string, { labels: string[]; matrix: number[][] }>;
  targets: Record<string, number>;
  notes: string[];
};
