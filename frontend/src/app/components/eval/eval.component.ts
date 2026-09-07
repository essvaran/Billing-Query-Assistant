import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

export type TabId = 'overview' | 'cases' | 'assertions' | 'judge';

export interface EvalCase {
  id: string;
  question: string;
  mode: string;
  expected: 'answer' | 'refusal';
  regression: boolean;
  traceId?: string;
  assertions: { bare: boolean; dash: boolean; hal: boolean; fab: boolean };
  judge: 'GOOD' | 'NOT_GOOD';
  judgeV2: 'GOOD' | 'NOT_GOOD';
  snippet: string;
}

// Real data from evaluation/answers_25.jsonl (clean run date: 2026-09-03, model: openai/gpt-oss-120b via Groq)
// 25/25 answers generated successfully (5s inter-call delay + 429 retry-backoff).
// Assertions: 25/25 pass -- model now produces full chunk IDs so citation validator no longer masks answers.
// Judge v1 = 22/25 GOOD (88%), Judge v2 = 22/25 GOOD (88%), both fail G04, F06, CE02.
// Human labels in labels_25.json (updated 2026-09-03 after clean run). Agreement v1=v2=96% (24/25).
const CASES: EvalCase[] = [
  { id:'R01', question:'Error code ERR-4040 appeared, how do I fix it?',
    mode:'citation_abbreviation',  expected:'answer',  regression:false, traceId:'3dd5ae80',
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'Add new payment method, set as default, retry migration. [HC-BILL-002--error-codes--err-4040]' },
  { id:'R02', question:'The migration is stuck with error 4032',
    mode:'false_refusal',          expected:'answer',  regression:true, traceId:'a9161b2e',
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'[WEEK 5 FAIL] False refusal -- wrong chunks retrieved (troubleshooting-guide, ACC-5006, ERR-4040); ERR-4032 article not surfaced. Fixed in clean run.' },
  { id:'G01', question:'Can I get a refund if my billing migration fails?',
    mode:'corpus_gap', expected:'refusal', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'I cannot answer that from the indexed help-centre articles.' },
  { id:'G02', question:'What is the processing fee for international credit card payments?',
    mode:'corpus_gap', expected:'refusal', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'I cannot answer that from the indexed help-centre articles.' },
  { id:'G03', question:'How long does a billing migration typically take?',
    mode:'corpus_gap', expected:'refusal', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'Typically 24 hrs; up to 72 hrs for 50+ invoices. [HC-BILL-001--timeline--prose-001]' },
  { id:'G04', question:'Can I pause a billing migration once it has started?',
    mode:'corpus_gap', expected:'refusal', regression:true, traceId:'b7c312f1',
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'NOT_GOOD',  judgeV2:'NOT_GOOD',
    snippet:'[WRONG CHUNK] Answer states cannot pause but cited chunk (extended-faq) does not contain that information.' },
  { id:'G05', question:'Is there a customer service phone number for billing issues?',
    mode:'corpus_gap', expected:'refusal', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'I cannot answer that from the indexed help-centre articles.' },
  { id:'G06', question:'What is the SLA for resolving billing migration errors?',
    mode:'corpus_gap', expected:'refusal', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'I cannot answer that from the indexed help-centre articles.' },
  { id:'F01', question:'What does ERR-4032 mean?',
    mode:'false_refusal', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'ERR-4032: required field missing from billing profile (blocking). [HC-BILL-002--error-codes--err-4032]' },
  { id:'F02', question:'What causes PAY-1001?',
    mode:'false_refusal', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'PAY-1001: default payment method expired before migration completed. [HC-BILL-002--pay-series--pay-1001]' },
  { id:'F03', question:'What does ERR-5010 mean?',
    mode:'false_refusal', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'ERR-5010: invoice account locked due to prior unresolved dispute. [HC-BILL-002--error-codes--err-5010]' },
  { id:'F04', question:'What happens to auto-pay during a billing migration?',
    mode:'false_refusal', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'Auto-pay paused during migration; resumes after owner confirms new default method. [HC-BILL-001--recurring-billing...]' },
  { id:'F05', question:'Which account roles can confirm a billing migration?',
    mode:'false_refusal', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'Billing Administrator and Account Owner can confirm migration. [HC-BILL-005--who-can-initiate...]' },
  { id:'F06', question:'Can a completed billing migration be rolled back?',
    mode:'false_refusal', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'NOT_GOOD',  judgeV2:'NOT_GOOD',
    snippet:'[JUDGE STRICT] Core answer correct from HC-BILL-006; second citation (FAQ chunk) seen as unsupported by judge.' },
  { id:'F07', question:'What does ERR-4040 mean and how is it different from ERR-4032?',
    mode:'false_refusal', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'ERR-4040 = payment re-verification failure; ERR-4032 = required field missing. [HC-BILL-002--error-codes--err-4040, --err-4032]' },
  { id:'A01', question:'How do I fix ERR-6030?',
    mode:'citation_abbreviation', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'ERR-6030: need Account Owner or Billing Admin to submit rollback. [HC-BILL-006--rollback-error-codes--err-6030]' },
  { id:'A02', question:'How do I request a migration rollback?',
    mode:'citation_abbreviation', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'Billing Overview > Migration Status > Request rollback. Processed in 4 biz hrs. [HC-BILL-006--how-to-request-rollback]' },
  { id:'A03', question:'What does PLAN-ENT-V1 map to on the new platform?',
    mode:'citation_abbreviation', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'PLAN-ENT-V1 maps to PLAN-ENTERPRISE-2024 (201+ seats). [HC-BILL-001--subscription-migration--plan-ent-v1]' },
  { id:'A04', question:'Which error codes are related to payment method issues?',
    mode:'citation_abbreviation', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'PAY-1005 (expired PO), PAY-1009 (fraud flag). All PAY-series are blocking. [HC-BILL-002--pay-series]' },
  { id:'A05', question:'Tell me about PAY-1007',
    mode:'citation_abbreviation', expected:'refusal', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'PAY-1007: tokenization timeout (blocking). Retry; contact support after 2 retries. [HC-BILL-002--pay-series--pay-1007]' },
  { id:'CE01', question:'Payment method re-verification failed during migration',
    mode:'citation_character_error', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'ERR-4040: payment re-verification failed. Add new method, set default, retry. [HC-BILL-003--payment-errors--err-4040]' },
  { id:'CE02', question:'What steps should I take if ERR-4032 keeps repeating?',
    mode:'citation_character_error', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'NOT_GOOD',  judgeV2:'NOT_GOOD',
    snippet:'[HALLUCINATION] Step 2 adds specific menu paths and data fields not found in retrieved context chunks.' },
  { id:'CE03', question:'How do I add a new payment method during migration?',
    mode:'citation_character_error', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'Add new payment method, set as default before retrying migration. [HC-BILL-003--payment-errors--err-4040]' },
  { id:'CE04', question:'What does the ERR-6030 error code indicate for rollback scenarios?',
    mode:'citation_character_error', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'ERR-6030: rollback by user without Billing Admin role. Ask Account Owner or Admin. [HC-BILL-006--rollback-error-codes--err-6030]' },
  { id:'CE05', question:'What are the prerequisites for a billing migration?',
    mode:'citation_character_error', expected:'answer', regression:false,
    assertions:{bare:true,dash:true,hal:true,fab:true}, judge:'GOOD',  judgeV2:'GOOD',
    snippet:'3 prerequisites: verified payment method, no disputed charges, accepted billing terms. [HC-BILL-001--migration-prerequisites]' },
];

interface ModeStats {
  mode: string;
  cssClass: string;
  n: number;
  assertPass: number;
  judgePass: number;
  judgeV2Pass: number;
  overallPass: number;
  overallV2Pass: number;
  pct: number;
  pctV2: number;
  description: string;
}

@Component({
  selector: 'app-eval',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './eval.component.html',
  styleUrl: './eval.component.scss',
})
export class EvalComponent {
  activeTab: TabId = 'overview';
  caseFilter = 'all';

  readonly cases = CASES;

  readonly modeList = ['corpus_gap', 'false_refusal', 'citation_abbreviation', 'citation_character_error'];

  readonly modeLabels: Record<string, string> = {
    corpus_gap: 'corpus_gap',
    false_refusal: 'false_refusal',
    citation_abbreviation: 'citation_abbrev',
    citation_character_error: 'citation_char_err',
  };

  readonly modeDescriptions: Record<string, string> = {
    corpus_gap: 'Question has no answer in corpus. Correct response is the refusal message.',
    false_refusal: 'Answer exists in corpus but system may refuse. Tests that retrieval finds the right chunk.',
    citation_abbreviation: 'Model produces correct content but shortens chunk IDs to bare article IDs.',
    citation_character_error: 'Model uses en-dash (–) instead of ASCII hyphen (-) inside citation brackets.',
  };

  readonly filterOptions = [
    { label: 'All (25)', value: 'all' },
    { label: 'corpus_gap (6)', value: 'corpus_gap' },
    { label: 'false_refusal (8)', value: 'false_refusal' },
    { label: 'citation_abbrev (6)', value: 'citation_abbreviation' },
    { label: 'citation_char_err (5)', value: 'citation_character_error' },
  ];

  readonly regressions = CASES.filter(c => c.regression);

  get filteredCases(): EvalCase[] {
    return this.caseFilter === 'all'
      ? CASES
      : CASES.filter(c => c.mode === this.caseFilter);
  }

  get modeStats(): ModeStats[] {
    return this.modeList.map(mode => {
      const rows = CASES.filter(c => c.mode === mode);
      const n = rows.length;
      const ap  = rows.filter(c => this.assertPass(c)).length;
      const jp  = rows.filter(c => c.judge    === 'GOOD').length;
      const jp2 = rows.filter(c => c.judgeV2  === 'GOOD').length;
      const op  = rows.filter(c => this.overallPass(c)).length;
      const op2 = rows.filter(c => this.overallV2Pass(c)).length;
      return {
        mode,
        cssClass: this.modeClass(mode),
        n,
        assertPass: ap,
        judgePass: jp,
        judgeV2Pass: jp2,
        overallPass: op,
        overallV2Pass: op2,
        pct:   Math.round((op  / n) * 100),
        pctV2: Math.round((op2 / n) * 100),
        description: this.modeDescriptions[mode] ?? '',
      };
    });
  }

  get totalOverall():   number { return CASES.filter(c => this.overallPass(c)).length; }
  get totalOverallV2(): number { return CASES.filter(c => this.overallV2Pass(c)).length; }
  get totalAssert():    number { return CASES.filter(c => this.assertPass(c)).length; }
  get totalJudge():     number { return CASES.filter(c => c.judge   === 'GOOD').length; }
  get totalJudgeV2():   number { return CASES.filter(c => c.judgeV2 === 'GOOD').length; }

  // Human labels from labels_25.json (updated 2026-09-03 after clean run -- stale labels from broken run replaced)
  // NOT_GOOD: G04 (wrong chunk cited), CE02 (hallucinated escalation steps). All others GOOD.
  private humanGood = new Set(['R01','R02','G01','G02','G03','G05','G06',
    'F01','F02','F03','F04','F05','F06','F07','A01','A02','A03','A04','A05',
    'CE01','CE03','CE04','CE05']);
  agreementV1(): number { return CASES.filter(c => (c.judge   === 'GOOD') === this.humanGood.has(c.id)).length; }
  agreementV2(): number { return CASES.filter(c => (c.judgeV2 === 'GOOD') === this.humanGood.has(c.id)).length; }

  assertPass(c: EvalCase):    boolean { return c.assertions.bare && c.assertions.dash && c.assertions.hal && c.assertions.fab; }
  overallPass(c: EvalCase):   boolean { return this.assertPass(c) && c.judge   === 'GOOD'; }
  overallV2Pass(c: EvalCase): boolean { return this.assertPass(c) && c.judgeV2 === 'GOOD'; }

  failedAsserts(c: EvalCase): string[] {
    const f: string[] = [];
    if (!c.assertions.bare) f.push('bare_id');
    if (!c.assertions.dash) f.push('en_dash');
    return f;
  }

  modeClass(mode: string): string {
    return {
      corpus_gap: 'mode--gap',
      false_refusal: 'mode--fr',
      citation_abbreviation: 'mode--ca',
      citation_character_error: 'mode--ce',
    }[mode] ?? '';
  }

  setTab(tab: TabId): void { this.activeTab = tab; }
  setFilter(f: string): void { this.caseFilter = f; }
}
