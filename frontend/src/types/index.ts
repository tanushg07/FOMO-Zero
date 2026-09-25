export interface ActionItem { 
  task: string; 
  deadline: string | null; 
  priority: "High" | "Medium" | "Low"; 
}

export interface CriticalDate { 
  date: string; 
  event: string; 
}

export interface NoticeResult {
  id: string;
  title: string;
  target_audience: string;
  core_update: string;
  critical_dates: CriticalDate[];
  action_checklist: ActionItem[];
  consequence_if_missed: string;
  validation_status: "Verified" | "Needs Review" | "Blocked";
  raw_evidence: string; // markdown chunk
  original_text: string;
}
