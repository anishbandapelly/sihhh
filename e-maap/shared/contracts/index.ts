export type PackageFamily = 'RIGID_CUBOID'|'CURVED_RIGID'|'FLEXIBLE'|'OTHER_PACKAGE';
export type EvidenceState = 'SUPPORTED'|'CONFLICTING'|'UNRESOLVED'|'OBSCURED_DAMAGED'|'POTENTIALLY_ABSENT'|'NOT_APPLICABLE';
export type SyncStatus = 'LOCAL_ONLY'|'UPLOADING'|'SYNCHRONISED'|'FAILED';
export type FindingStatus = 'POTENTIAL'|'ACCEPTED'|'CORRECTED'|'REJECTED';
export type Role = 'INSPECTOR'|'GOVERNMENT_OFFICER';
export type Action = 'ACCEPT'|'CORRECT'|'REJECT';
export type Value = Record<string,string|number|null>;
export type BBox = [number,number,number,number];
export interface Identity { id:string; name:string; role:Role|null; session_type:'officer'|'citizen' }
export interface LoginResult {id:string;name:string;role:Role;access_token:string;token_type:string}
export interface Product {product_name:string;brand?:string|null;manufacturer:string;variant?:string|null;batch_lot?:string|null;net_quantity_text?:string|null;barcode?:string|null;package_family:PackageFamily;officer_confirmed_json?:Record<string,unknown>}
export interface Priority {computed_band?:string;severity_rank?:number;verified_history?:number;evidence_readiness?:number;factors?:string[];pattern_id?:string;override?:{band:string;reason:string;officer:string;time:string}}
export interface Assignment {id:string;case_id:string;inspector_id:string;status:string;assigned_at:string;downloaded_at?:string|null}
export interface CaseSummary {id:string;reference:string;case_type:string;source:string;status:string;product_snapshot:Product;shop:{name:string;area?:string;latitude?:number;longitude?:number};priority_band:string;priority_reasons:Priority;assignment?:Assignment|null;created_at:string;parent_case_id?:string|null}
export interface Quality {state:'CHECKING'|'GOOD'|'BLUR'|'GLARE'|'COVERAGE_MISSING';usable:boolean;flags:string[];blur_metric:number;glare_metric:number;instruction:string;width?:number;height?:number;config_version?:string}
export interface Evidence {id:string;case_id:string;sequence_no:number;sha256:string;captured_at:string;synced_at?:string|null;sync_status:SyncStatus;source_type?:string;source_context_json?:{view_role:string;search_groups:string[];replacement_for?:string|null;inspected_area?:string};quality?:Quality;quality_json?:Quality;storage_available?:boolean;latitude?:number;longitude?:number;accuracy_m?:number;mime_type?:string}
export interface SourceRef {evidence_id:string;candidate_id?:string;id?:string;bbox:BBox;raw_text?:string;value?:Value;confidence?:number;extractor?:string;source_type?:string;quality?:Quality;provenance?:{sha256:string;captured_at:string;synced_at:string;latitude?:number;longitude?:number;accuracy_m?:number}}
export interface RuleResult {id:string;rule_code:string;rule_version:string;legal_reference:string;result_state:string;reason_code?:string|null;explanation:string;inputs_json:Record<string,unknown>}
export interface Finding {id:string;case_id:string;status:FindingStatus;rule_code:string;rule_version:string;explanation:string;severity:number;verified_value?:Value|null;evidence_refs:SourceRef[];verification_events:Record<string,unknown>[]}
export interface Audit {id:string;actor_id:string|null;event_type:string;created_at:string;payload:Record<string,unknown>}
export interface PresentationCheck {presentation_state:string;explanation:string;inputs:Record<string,unknown>;rule_code:string;rule_version:string}
export interface Declaration {id:string;declaration_group:string;title:string;evidence_state:EvidenceState;fused_value:Value|null;reviewed_value:Value|null;candidate_count:number;source_refs:SourceRef[];applicable_rules:RuleResult[];findings:Finding[];verification_status:string;review?:Audit|null;presentation:Record<string,PresentationCheck>;review_flags:string[];next_capture_prompt?:string|null;absence_eligible:boolean}
export interface ComplianceMap {case_id:string;status:string;items:Declaration[]}
export interface Analysis {id?:string;analysis_run_id?:string;status:'QUEUED'|'RUNNING'|'SUCCEEDED'|'FAILED';failure_code?:string|null;retryable?:boolean;message?:string}
export interface Report {id:string;case_id:string;status:'QUEUED'|'GENERATING'|'READY'|'FAILED';generated_at?:string;failure_code?:string|null;pdf_url?:string|null;docx_url?:string|null}
export interface Followup {id:string;systemic_case_id:string;assigned_to:string;status:'ASSIGNED'|'IN_PROGRESS'|'COMPLETED';note?:string|null;due_at?:string|null;updated_at:string}
export interface CaseDetail extends CaseSummary {evidence:Evidence[];history:Audit[];reports:Report[];followups:Followup[];children:CaseSummary[]}
export interface Pattern {id:string;status:'CANDIDATE'|'APPROVED'|'REJECTED';pattern_level:string;rule_code:string;verified_count:number;awaiting_count:number;citizen_lead_count:number;retailer_count:number;priority_reason:string;match_factors:{product:string;manufacturer:string;batch_lot?:string;matched_fields:string[];locations:string[];explanation:string};members?:{finding:Finding;case:CaseSummary;match_reason:Record<string,unknown>}[];awaiting_case_ids?:string[];citizen_lead_case_ids?:string[]}
export interface Dashboard {counts:{awaiting_review:number;active_inspections:number;verified_findings:number;pattern_proposals:number};priority_queue:CaseSummary[];patterns:Pattern[];locations:{name:string;count:number}[];inspectors:{id:string;name:string}[]}
export interface SourceCard {source_type:string;source_id:string;title:string;verification_label:string}
export interface CopilotAnswer {answer:string;evidence_gap:string|null;source_cards:SourceCard[];verification_labels:string[];proposed_action_draft?:unknown}
export interface Brief {id:string;context_type:'case'|'pattern';context_id:string;content:string;status:'DRAFT'|'APPROVED'|'REJECTED';source_refs:SourceCard[];creator:string;last_editor:string;created_at:string;approval_timestamp?:string}
export interface RepositoryItem {case_id:string;scanned_at:string;product_snapshot:Product;retailer:string;location:{area?:string};case_status:string;issue_summary:string[];verification_status:string[];report_refs:Report[]}
export interface Page<T> {items:T[];total:number;page:number;page_size:number}
export interface ListingResult {input_kind:string;source_label:string;quality:Quality;visible_observations:{declaration_group:string;raw_text:string;value:Value;source_ref:SourceRef;verification_label:string}[];supplied_text_observations:{declaration_group:string;raw_text:string;value:Value;source_type:string;verification_label:string}[];possible_concerns:{rule_code:string;rule_version:string;reason_code:string;explanation:string;source_refs:SourceRef[]}[];evidence_gap:string;physical_verification_required:boolean;absence_eligible:false;source_refs:SourceRef[];attached_case_id:string|null}
export interface PlanItem {id:string;declaration_group:string;required:boolean;coverage_state:string;absence_eligible:boolean;source_evidence_ids:string[];next_capture_prompt?:string|null;rule_ids:string[]}
export interface Profile {title:string;roles:string[];prompts:string[];manual:boolean}
export interface Config {version:string;capture:{blur_threshold:number;glare_threshold:number;sample_width:number;glare_luminance:number;glare_local_contrast:number};upload:{max_image_bytes:number;max_image_pixels:number};analysis:{poll_interval_ms:number;timeout_seconds:number;max_retries:number};profiles:Record<PackageFamily,Profile>}
export interface CapturePlan {case_id:string;package_family:PackageFamily;profile:Profile;items:PlanItem[];configuration:Config;rule_version_refs:{code:string;version:string}[]}
export interface DownloadedAssignment {assignment:Assignment;case:CaseSummary;capture:CapturePlan}
export interface CitizenScan {scan_id:string;package_family:PackageFamily;profile:Profile;capture_configuration:Config['capture'];upload_configuration:Config['upload'];analysis_configuration:Config['analysis'];declarations:{id:string;name:string}[]}
export interface CitizenResult {scan_id:string;notice:string;physical_verification_required:boolean;declarations:{declaration:string;value:Value|null;message:string;sources:SourceRef[]}[]}
export interface ComplaintReceipt {reference:string;tracking_token:string;status:string;message:string}
export function valueText(value:Value|null|undefined):string {return value?Object.values(value).filter(v=>v!==null&&v!=='').join(' · ')||'No value established':'No value established';}
