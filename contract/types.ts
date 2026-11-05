// Owner: Aditya. A mirror of CONTRACT.md for the frontend.
// Deepak: import these types and do not redefine them. Need a change? Ask Aditya.

export type Status =
  | "INTAKE" | "NEEDS_CLARIFICATION" | "FINDING" | "VERIFYING" | "OUTREACH"
  | "NEGOTIATING" | "BOOKING" | "BOOKED" | "ESCALATED" | "FAILED";

export interface Constraints {
  topic: string; duration_min: number; window_start: string; window_end: string; max_inr: number;
}

export interface Claim {
  text: string;
  status: "verified" | "contradicted" | "unverifiable";
  evidence: string | null;
  source: string;
  fetched_at: string;
}

export interface ShortlistItem {
  expert_id: string; name: string; headline: string; rate_inr: number; score: number;
  flag: "ok" | "unverifiable" | "contradicted";
  outreach_state: "pending" | "contacted" | "replied" | "declined" | "timed_out" | "booked" | "released" | "skipped";
  claims: Claim[];
}

export interface TimelineEvent {
  t: string; step: Status; msg: string;
  source: "llm" | "code" | "crustdata" | "telegram" | "gcal" | "human" | string;
}

export interface Booking {
  expert_id: string; start: string; end: string; price_inr: number;
  calendar_event_id: string; confirmation: string;
}

export interface EscalationOption {
  option_id: string; expert_id: string; slot: string; price_inr: number; summary: string;
}

export interface Escalation { reason: string; options: EscalationOption[]; }

export interface Request {
  id: string; status: Status; raw_text: string;
  clarification_question: string | null;
  constraints: Constraints | null;
  shortlist: ShortlistItem[];
  timeline: TimelineEvent[];
  booking: Booking | null;
  escalation: Escalation | null;
}

export interface Expert {
  expert_id: string; name: string; headline: string; linkedin_url: string;
  rate_inr: number; simulated: boolean;
}

export interface Eval {
  run_at: string; total_runs: number; consistent: number;
  budget_violations: number; time_violations: number; double_bookings: number;
  fakes_planted: number; fakes_caught: number;
}
