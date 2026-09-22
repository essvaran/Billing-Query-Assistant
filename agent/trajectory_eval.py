"""Trajectory evaluation engine for the ticket agent.

Runs all 10 tickets (7 standard/branching + 3 adversarial), captures
tool-call trajectories, asserts expected sequences, and computes four
trajectory metrics plus the outcome-vs-trajectory gap.
"""

import json
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

from agent.tickets import (
    BRANCHING_IDS,
    CUSTOMERS,
    EXPECTED,
    EXPECTED_ARGS,
    EXPECTED_SEQUENCES,
    ORDERS,
    TICKET_IDS,
    TICKETS,
)


@dataclass
class ToolStep:
    tool: str
    args: dict
    result: dict
    valid_args: bool = True


@dataclass
class FailureMode:
    mode: str
    ticket_id: str
    detail: str


@dataclass
class TrajectoryResult:
    ticket_id: str
    expected_verdict: str
    outcome_passed: bool
    reply: str
    tool_steps: list[ToolStep] = field(default_factory=list)
    expected_sequences: list[list[str]] = field(default_factory=list)
    sequence_matched: bool = False
    tool_choice_correct: bool = False
    all_args_valid: bool = False
    step_count: int = 0
    optimal_step_count: int = 3
    step_efficiency: float = 0.0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    total_tokens: int = 0
    laps: int = 0
    failure_modes: list[FailureMode] = field(default_factory=list)
    trajectory_passed: bool = False
    trace_url: str | None = None


@dataclass
class GapExample:
    ticket_id: str
    expected_verdict: str
    reply_snippet: str
    actual_sequence: list[str]
    expected_sequences: list[list[str]]
    failure_modes: list[str]
    explanation: str


@dataclass
class TrajectoryEvalReport:
    run_id: str
    run_at: str
    results: list[dict] = field(default_factory=list)
    tool_choice_accuracy: float = 0.0
    argument_validity_rate: float = 0.0
    step_efficiency_mean: float = 0.0
    cost_p50: float = 0.0
    cost_max: float = 0.0
    outcome_pass_count: int = 0
    trajectory_pass_count: int = 0
    gap: int = 0
    gap_example: dict | None = None
    failure_mode_counts: dict[str, int] = field(default_factory=dict)
    all_failure_modes: list[dict] = field(default_factory=list)


FAILURE_MODE_TAXONOMY = [
    "wrong_tool",
    "hallucinated_args",
    "wrong_arg_source",
    "extra_steps",
    "skipped_tool",
    "loop",
]


class TrajectoryRecorder:
    """on_step callback that collects tool_call and tool_result events."""

    def __init__(self):
        self.steps: list[ToolStep] = []
        self._pending: dict[str, dict] = {}

    def __call__(self, event: dict):
        if event.get("type") == "tool_call":
            tool = event.get("tool", "")
            args = event.get("args", {})
            self._pending[tool] = {"tool": tool, "args": args}
        elif event.get("type") == "tool_result":
            tool = event.get("tool", "")
            result = event.get("result", {})
            pending = self._pending.pop(tool, None)
            if pending:
                self.steps.append(ToolStep(
                    tool=pending["tool"],
                    args=pending["args"],
                    result=result,
                    valid_args=True,
                ))
            else:
                self.steps.append(ToolStep(tool=tool, args={}, result=result))

    def get_tool_sequence(self) -> list[str]:
        return [s.tool for s in self.steps]


def _validate_args(step: ToolStep, ticket_id: str, resolved_context: dict) -> bool:
    """Check if the tool call args reference real/expected entities."""
    tool = step.tool
    args = step.args

    if tool == "get_ticket":
        return args.get("ticket_id") == ticket_id

    if tool == "get_order":
        ticket_data = TICKETS.get(ticket_id, {})
        expected_order = ticket_data.get("order_id", "")
        actual_order = args.get("order_id", "")
        if actual_order == expected_order:
            return True
        if ticket_id == "T008" and actual_order == "O208-ALT":
            return True
        return False

    if tool == "get_customer_tier":
        ticket_data = TICKETS.get(ticket_id, {})
        expected_customer = ticket_data.get("customer_id", "")
        actual_customer = args.get("customer_id", "")
        return actual_customer == expected_customer

    if tool == "search_knowledge_base":
        return bool(args.get("query", "").strip())

    return True


def _check_sequence_match(actual: list[str], expected_set: list[list[str]]) -> bool:
    """Check if actual tool sequence matches any expected sequence."""
    for expected in expected_set:
        if actual == expected:
            return True
    return False


def _classify_failures(
    ticket_id: str,
    actual_sequence: list[str],
    expected_sequences: list[list[str]],
    steps: list[ToolStep],
) -> list[FailureMode]:
    """Classify trajectory failures into taxonomy modes."""
    failures: list[FailureMode] = []

    required_tools = {"get_ticket", "get_order", "get_customer_tier"}
    called_tools = set(actual_sequence)

    for req in required_tools:
        if req not in called_tools:
            failures.append(FailureMode("skipped_tool", ticket_id, f"Never called {req}"))

    for i, tool in enumerate(actual_sequence):
        if i == 0 and tool != "get_ticket":
            failures.append(FailureMode("wrong_tool", ticket_id, f"Step {i+1}: called {tool} instead of get_ticket"))
        elif i == 1 and tool not in ("get_order", "get_ticket"):
            failures.append(FailureMode("wrong_tool", ticket_id, f"Step {i+1}: called {tool} instead of get_order"))

    for step in steps:
        if not step.valid_args:
            if step.tool in ("get_ticket", "get_order", "get_customer_tier"):
                expected_args = EXPECTED_ARGS.get(ticket_id, {}).get(step.tool, {})
                actual_val = list(step.args.values())[0] if step.args else ""
                expected_val = list(expected_args.values())[0] if expected_args else ""

                all_known_ids = set(TICKETS.keys()) | set(ORDERS.keys()) | set(CUSTOMERS.keys())
                if actual_val and actual_val not in all_known_ids and actual_val != "O208-ALT":
                    failures.append(FailureMode("hallucinated_args", ticket_id,
                        f"{step.tool} called with invented ID '{actual_val}'"))
                else:
                    failures.append(FailureMode("wrong_arg_source", ticket_id,
                        f"{step.tool} called with '{actual_val}' instead of '{expected_val}'"))

    seen_calls: list[tuple[str, str]] = []
    for step in steps:
        call_sig = (step.tool, json.dumps(step.args, sort_keys=True))
        if call_sig in seen_calls:
            failures.append(FailureMode("loop", ticket_id,
                f"Repeated call: {step.tool}({step.args})"))
        seen_calls.append(call_sig)

    best_optimal = min(len(seq) for seq in expected_sequences)
    if len(actual_sequence) > best_optimal + 1:
        extra = len(actual_sequence) - best_optimal
        unexpected = [t for t in actual_sequence if t == "search_knowledge_base"]
        if unexpected:
            failures.append(FailureMode("extra_steps", ticket_id,
                f"{extra} extra steps including {len(unexpected)} search_knowledge_base calls"))
        elif extra > 1:
            failures.append(FailureMode("extra_steps", ticket_id,
                f"{extra} extra tool calls beyond the optimal {best_optimal}"))

    return failures


def run_single_trajectory(
    ticket_id: str,
    dispatch_override=None,
    system_prompt_override=None,
    on_progress=None,
) -> TrajectoryResult:
    """Run the agent on one ticket and evaluate its trajectory."""
    from agent.agent_loop import run_agent

    expected_verdict = EXPECTED.get(ticket_id, "")
    expected_seqs = EXPECTED_SEQUENCES.get(ticket_id, [["get_ticket", "get_order", "get_customer_tier"]])

    recorder = TrajectoryRecorder()

    def combined_on_step(event):
        recorder(event)

    result = run_agent(
        ticket_id=ticket_id,
        expected_verdict=expected_verdict,
        verbose=False,
        on_step=combined_on_step,
        dispatch_override=dispatch_override,
        system_prompt_override=system_prompt_override,
    )

    for step in recorder.steps:
        step.valid_args = _validate_args(step, ticket_id, {})

    actual_sequence = recorder.get_tool_sequence()
    seq_matched = _check_sequence_match(actual_sequence, expected_seqs)

    all_args_valid = all(s.valid_args for s in recorder.steps)
    total_calls = len(recorder.steps)
    valid_calls = sum(1 for s in recorder.steps if s.valid_args)

    best_optimal = min(len(seq) for seq in expected_seqs)
    step_efficiency = best_optimal / max(len(actual_sequence), 1)
    step_efficiency = min(step_efficiency, 1.0)

    tool_choice_correct = seq_matched

    failures = _classify_failures(ticket_id, actual_sequence, expected_seqs, recorder.steps)

    trajectory_passed = seq_matched and all_args_valid and not failures

    traj_result = TrajectoryResult(
        ticket_id=ticket_id,
        expected_verdict=expected_verdict,
        outcome_passed=result.passed,
        reply=result.reply[:500],
        tool_steps=[ToolStep(s.tool, s.args, s.result, s.valid_args) for s in recorder.steps],
        expected_sequences=expected_seqs,
        sequence_matched=seq_matched,
        tool_choice_correct=tool_choice_correct,
        all_args_valid=all_args_valid,
        step_count=len(actual_sequence),
        optimal_step_count=best_optimal,
        step_efficiency=round(step_efficiency, 3),
        cost_usd=round(result.cost_usd, 6),
        latency_s=round(result.latency_s, 3),
        total_tokens=result.total_tokens,
        laps=result.laps,
        failure_modes=failures,
        trajectory_passed=trajectory_passed,
        trace_url=result.trace_url,
    )

    return traj_result


def run_full_eval(
    dispatch_override=None,
    system_prompt_override=None,
    on_progress=None,
) -> TrajectoryEvalReport:
    """Run trajectory eval on all tickets and compute aggregate metrics."""
    run_id = str(uuid.uuid4())[:8]
    run_at = datetime.now().isoformat()

    results: list[TrajectoryResult] = []

    for i, ticket_id in enumerate(TICKET_IDS):
        if on_progress:
            on_progress({"type": "ticket_start", "ticket_id": ticket_id, "index": i, "total": len(TICKET_IDS)})

        traj = run_single_trajectory(ticket_id, dispatch_override=dispatch_override, system_prompt_override=system_prompt_override)
        results.append(traj)

        if on_progress:
            on_progress({"type": "ticket_done", "ticket_id": ticket_id, "index": i,
                         "outcome_passed": traj.outcome_passed, "trajectory_passed": traj.trajectory_passed})

        time.sleep(3)

    tickets_with_correct_tools = sum(1 for r in results if r.tool_choice_correct)
    tool_choice_accuracy = tickets_with_correct_tools / len(results)

    total_calls = sum(len(r.tool_steps) for r in results)
    valid_calls = sum(sum(1 for s in r.tool_steps if s.valid_args) for r in results)
    argument_validity_rate = valid_calls / max(total_calls, 1)

    step_efficiency_mean = statistics.mean(r.step_efficiency for r in results)

    costs = [r.cost_usd for r in results]
    cost_p50 = statistics.median(costs) if costs else 0.0
    cost_max = max(costs) if costs else 0.0

    outcome_pass_count = sum(1 for r in results if r.outcome_passed)
    trajectory_pass_count = sum(1 for r in results if r.trajectory_passed)
    gap = outcome_pass_count - trajectory_pass_count

    gap_example = None
    for r in results:
        if r.outcome_passed and not r.trajectory_passed:
            mode_names = [f.mode for f in r.failure_modes]
            actual_seq = [s.tool for s in r.tool_steps]
            gap_example = GapExample(
                ticket_id=r.ticket_id,
                expected_verdict=r.expected_verdict,
                reply_snippet=r.reply[:200],
                actual_sequence=actual_seq,
                expected_sequences=r.expected_sequences,
                failure_modes=mode_names,
                explanation=(
                    f"Ticket {r.ticket_id} got the right answer ({r.expected_verdict}) "
                    f"but took a wrong path: {', '.join(mode_names)}. "
                    f"Actual tools called: {' -> '.join(actual_seq)}."
                ),
            )
            break

    all_failures: list[FailureMode] = []
    failure_mode_counts: dict[str, int] = {m: 0 for m in FAILURE_MODE_TAXONOMY}
    for r in results:
        for f in r.failure_modes:
            all_failures.append(f)
            failure_mode_counts[f.mode] = failure_mode_counts.get(f.mode, 0) + 1

    result_dicts = []
    for r in results:
        rd = {
            "ticket_id": r.ticket_id,
            "expected_verdict": r.expected_verdict,
            "outcome_passed": r.outcome_passed,
            "reply": r.reply,
            "tool_steps": [{"tool": s.tool, "args": s.args, "result": s.result, "valid_args": s.valid_args} for s in r.tool_steps],
            "expected_sequences": r.expected_sequences,
            "sequence_matched": r.sequence_matched,
            "tool_choice_correct": r.tool_choice_correct,
            "all_args_valid": r.all_args_valid,
            "step_count": r.step_count,
            "optimal_step_count": r.optimal_step_count,
            "step_efficiency": r.step_efficiency,
            "cost_usd": r.cost_usd,
            "latency_s": r.latency_s,
            "total_tokens": r.total_tokens,
            "laps": r.laps,
            "failure_modes": [{"mode": f.mode, "ticket_id": f.ticket_id, "detail": f.detail} for f in r.failure_modes],
            "trajectory_passed": r.trajectory_passed,
            "trace_url": r.trace_url,
        }
        result_dicts.append(rd)

    report = TrajectoryEvalReport(
        run_id=run_id,
        run_at=run_at,
        results=result_dicts,
        tool_choice_accuracy=round(tool_choice_accuracy, 3),
        argument_validity_rate=round(argument_validity_rate, 3),
        step_efficiency_mean=round(step_efficiency_mean, 3),
        cost_p50=round(cost_p50, 6),
        cost_max=round(cost_max, 6),
        outcome_pass_count=outcome_pass_count,
        trajectory_pass_count=trajectory_pass_count,
        gap=gap,
        gap_example=asdict(gap_example) if gap_example else None,
        failure_mode_counts=failure_mode_counts,
        all_failure_modes=[{"mode": f.mode, "ticket_id": f.ticket_id, "detail": f.detail} for f in all_failures],
    )

    return report
