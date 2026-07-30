import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const projectRoot = process.cwd();
const pilotDir = path.join(projectRoot, "Tools", "core_freeze", "pilot_v1");
const outputDir = path.join(
  projectRoot,
  "outputs",
  "cf01_annotation_20260728",
);
const workbookPath = path.join(
  outputDir,
  "track_a_ai_consensus_human_adjudication.xlsx",
);
const silverPath = path.join(pilotDir, "track_a_provisional_silver.json");
const reportPath = path.join(
  outputDir,
  "track_a_provisional_silver_validation.json",
);
const policyPath = path.join(
  projectRoot,
  "docs",
  "experiments",
  "dataset_v2_annotation_policy_v1.0.md",
);

const coreFields = [
  "evidence_requirement",
  "answerability",
  "information_status",
  "capability_status",
  "risk_status",
];
const enumValues = {
  evidence_requirement: new Set(["none", "optional", "required"]),
  answerability: new Set([
    "answerable",
    "ambiguous_request",
    "missing_task_information",
  ]),
  information_status: new Set([
    "sufficient",
    "missing_execution_input",
    "ambiguous_execution_input",
  ]),
  capability_status: new Set(["available", "unavailable", "uncertain"]),
  risk_status: new Set(["normal", "review_required"]),
  annotation_confidence: new Set(["high", "medium", "low"]),
};
const allowedActionValues = new Set([
  "answer",
  "call",
  "clarify",
  "refuse",
  "escalate",
]);
const expectedSelectedIds = new Set([
  "TA-PILOT-001",
  "TA-PILOT-002",
  "TA-PILOT-003",
  "TA-PILOT-004",
  "TA-PILOT-006",
  "TA-PILOT-013",
  "TA-PILOT-015",
  "TA-PILOT-016",
  "TA-PILOT-017",
  "TA-PILOT-018",
  "TA-PILOT-019",
  "TA-PILOT-020",
]);
const explicitPolicyOverrides = new Map([
  [
    "TA-PILOT-020",
    {
      default_actions: ["clarify"],
      accepted_actions: ["refuse"],
      override_reason:
        "0 K is an explicit Arrhenius applicability-domain violation; supplying A and Ea cannot make an exact 0 K execution valid.",
    },
  ],
]);

function splitSet(value) {
  if (value === null || value === undefined || String(value).trim() === "") {
    return [];
  }
  return [...new Set(String(value).split("|").map((item) => item.trim()).filter(Boolean))]
    .sort();
}

function sameSet(left, right) {
  return JSON.stringify([...left].sort()) === JSON.stringify([...right].sort());
}

function defaultAllowedActions(row) {
  if (row.risk_status === "review_required") return ["escalate"];
  if (
    row.answerability === "ambiguous_request" ||
    row.answerability === "missing_task_information"
  ) {
    return ["clarify"];
  }
  if (row.evidence_requirement === "none" && row.answerability === "answerable") {
    return ["answer"];
  }
  if (row.evidence_requirement === "optional") {
    if (row.capability_status === "unavailable") return ["answer"];
    if (row.information_status === "sufficient") return ["answer", "call"];
    return ["answer", "clarify"];
  }
  if (row.evidence_requirement === "required") {
    if (row.capability_status === "unavailable") return ["refuse"];
    if (row.information_status === "sufficient") return ["call"];
    return ["clarify"];
  }
  throw new Error(`Cannot derive actions for ${row.task_id}`);
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function sha256(filePath) {
  const bytes = await fs.readFile(filePath);
  return crypto.createHash("sha256").update(bytes).digest("hex").toUpperCase();
}

const taskPath = path.join(pilotDir, "track_a_tasks.json");
const aiAPath = path.join(pilotDir, "track_a_annotator_a_AI-A.json");
const aiBPath = path.join(pilotDir, "track_a_annotator_b_AI-B.json");
const taskPayload = await readJson(taskPath);
const aiAPayload = await readJson(aiAPath);
const aiBPayload = await readJson(aiBPath);
const aiA = new Map(aiAPayload.annotations.map((row) => [row.task_id, row]));
const aiB = new Map(aiBPayload.annotations.map((row) => [row.task_id, row]));

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const finalSheet = workbook.worksheets.getItem("最终标签");
const matrix = finalSheet.getRange("A1:P13").values;
const headers = matrix[0].map((value) => String(value ?? ""));
const index = new Map(headers.map((header, column) => [header, column]));
const requiredHeaders = [
  "task_id",
  "样本类型",
  "evidence_requirement",
  "answerability",
  "information_status",
  "capability_status",
  "risk_status",
  "allowed_actions（|分隔）",
  "boundary_flags（可选，|分隔）",
  "最终裁决理由",
  "裁决置信度",
  "需专业复核",
  "裁决者",
  "完成状态",
];
for (const header of requiredHeaders) {
  if (!index.has(header)) throw new Error(`Workbook is missing column: ${header}`);
}

const reviewed = new Map();
for (const cells of matrix.slice(1)) {
  const get = (header) => cells[index.get(header)];
  const taskId = String(get("task_id") ?? "").trim();
  if (!taskId) continue;
  if (reviewed.has(taskId)) throw new Error(`Duplicate reviewed task: ${taskId}`);
  const row = {
    task_id: taskId,
    sample_type: String(get("样本类型") ?? "").trim(),
    evidence_requirement: String(get("evidence_requirement") ?? "").trim(),
    answerability: String(get("answerability") ?? "").trim(),
    information_status: String(get("information_status") ?? "").trim(),
    capability_status: String(get("capability_status") ?? "").trim(),
    risk_status: String(get("risk_status") ?? "").trim(),
    allowed_actions: splitSet(get("allowed_actions（|分隔）")),
    boundary_flags: splitSet(get("boundary_flags（可选，|分隔）")),
    action_reason: String(get("最终裁决理由") ?? "").trim(),
    annotation_confidence: String(get("裁决置信度") ?? "").trim(),
    professional_review:
      String(get("需专业复核") ?? "").trim() === "需要"
        ? "required"
        : String(get("需专业复核") ?? "").trim() === "无法判断"
          ? "uncertain"
          : "not_required",
    adjudicator: String(get("裁决者") ?? "").trim(),
    completion_status: String(get("完成状态") ?? "").trim(),
  };
  reviewed.set(taskId, row);
}

if (reviewed.size !== 12) {
  throw new Error(`Expected 12 reviewed rows, found ${reviewed.size}`);
}
if (!sameSet(reviewed.keys(), expectedSelectedIds)) {
  throw new Error("Reviewed task IDs do not match the frozen 9+3 selection");
}

const errors = [];
const warnings = [];
const overrides = [];
const adjudicators = new Set();
const outputLabels = [];
let humanAdjudicated = 0;
let humanAuditConfirmed = 0;
let aiConsensusUnreviewed = 0;

for (const task of taskPayload.tasks) {
  const taskId = task.task_id;
  const a = aiA.get(taskId);
  const b = aiB.get(taskId);
  if (!a || !b) {
    errors.push(`${taskId}: missing AI source annotation`);
    continue;
  }
  const human = reviewed.get(taskId);
  let label;
  let provenance;
  if (human) {
    label = human;
    provenance =
      human.sample_type === "一致性抽查"
        ? "human_audit_confirmed"
        : "human_adjudicated";
    if (provenance === "human_audit_confirmed") humanAuditConfirmed += 1;
    else humanAdjudicated += 1;
    if (human.completion_status !== "已完成") {
      errors.push(`${taskId}: workbook row is not completed`);
    }
    if (!human.adjudicator) errors.push(`${taskId}: adjudicator is empty`);
    else adjudicators.add(human.adjudicator);
    if (!human.action_reason) errors.push(`${taskId}: action reason is empty`);
    if (!enumValues.annotation_confidence.has(human.annotation_confidence)) {
      errors.push(`${taskId}: invalid annotation confidence`);
    }
  } else {
    const differing = coreFields.filter((field) => a[field] !== b[field]);
    if (!sameSet(a.allowed_actions, b.allowed_actions)) {
      differing.push("allowed_actions");
    }
    if (differing.length) {
      errors.push(
        `${taskId}: unreviewed task is not AI consensus (${differing.join(", ")})`,
      );
    }
    label = {
      task_id: taskId,
      evidence_requirement: a.evidence_requirement,
      answerability: a.answerability,
      information_status: a.information_status,
      capability_status: a.capability_status,
      risk_status: a.risk_status,
      allowed_actions: [...a.allowed_actions].sort(),
      boundary_flags: [],
      action_reason: null,
      annotation_confidence: null,
      professional_review: "not_assessed",
      adjudicator: null,
    };
    provenance = "ai_consensus_unreviewed";
    aiConsensusUnreviewed += 1;
  }

  for (const field of coreFields) {
    if (!enumValues[field].has(label[field])) {
      errors.push(`${taskId}: invalid ${field}=${label[field]}`);
    }
  }
  if (!label.allowed_actions.length) {
    errors.push(`${taskId}: allowed_actions is empty`);
  }
  const unexpectedActions = label.allowed_actions.filter(
    (action) => !allowedActionValues.has(action),
  );
  if (unexpectedActions.length) {
    errors.push(
      `${taskId}: invalid allowed actions ${unexpectedActions.join(", ")}`,
    );
  }

  const defaultActions = defaultAllowedActions(label).sort();
  if (!sameSet(defaultActions, label.allowed_actions)) {
    const override = explicitPolicyOverrides.get(taskId);
    if (
      override &&
      sameSet(override.default_actions, defaultActions) &&
      sameSet(override.accepted_actions, label.allowed_actions)
    ) {
      overrides.push({ task_id: taskId, ...override });
    } else {
      errors.push(
        `${taskId}: actions ${label.allowed_actions.join("|")} do not match policy default ${defaultActions.join("|")}`,
      );
    }
  }

  const boundaryStatus = label.boundary_flags.length
    ? provenance.startsWith("human")
      ? "human_adjudicated"
      : "ai_consensus"
    : "not_adjudicated";
  outputLabels.push({
    task_id: taskId,
    label_provenance: provenance,
    evidence_requirement: label.evidence_requirement,
    answerability: label.answerability,
    information_status: label.information_status,
    capability_status: label.capability_status,
    risk_status: label.risk_status,
    allowed_actions: [...label.allowed_actions].sort(),
    boundary_flags: [...label.boundary_flags].sort(),
    boundary_flags_status: boundaryStatus,
    action_reason: label.action_reason,
    annotation_confidence: label.annotation_confidence,
    professional_review: label.professional_review,
    adjudicator: label.adjudicator,
    source_ai_models: {
      ai_a: aiAPayload.annotator_name,
      ai_b: aiBPayload.annotator_name,
    },
    source_ai_boundary_flags: {
      ai_a: [...a.boundary_flags].sort(),
      ai_b: [...b.boundary_flags].sort(),
    },
    non_adjudicated_fields: [
      "required_inputs",
      "missing_inputs",
      "coarse_capability",
    ],
  });
}

if (humanAdjudicated !== 9) errors.push("Human adjudicated count is not 9");
if (humanAuditConfirmed !== 3) errors.push("Human audit count is not 3");
if (aiConsensusUnreviewed !== 8) errors.push("AI consensus count is not 8");
if (adjudicators.size !== 1) {
  errors.push(`Expected one adjudicator, found ${[...adjudicators].join(", ")}`);
}
if (outputLabels.length !== 20) errors.push("Output label count is not 20");

warnings.push(
  "boundary_flags were optional in the adjudication workbook and remain not_adjudicated when blank",
  "required_inputs, missing_inputs, and coarse_capability were not adjudicated",
  "the workbook uses Chinese-sheet COUNTIF formulas that the artifact-tool evaluator reports as #NAME? after Excel save; cached Excel values are not used by this conversion",
  "this output is provisional silver and is not eligible to pass CF-01 or CF-03",
);

const hashes = {
  task_file_sha256: await sha256(taskPath),
  ai_a_file_sha256: await sha256(aiAPath),
  ai_b_file_sha256: await sha256(aiBPath),
  adjudication_workbook_sha256: await sha256(workbookPath),
  annotation_policy_sha256: await sha256(policyPath),
};
const generatedAt = new Date().toISOString();
const status = errors.length ? "failed" : "passed";
const payload = {
  schema_version: "1.0-silver",
  pilot_id: taskPayload.pilot_id,
  status,
  label_tier: "provisional_silver",
  annotation_design: "dual_ai_consensus_with_human_adjudication",
  human_blind_annotation: false,
  formal_cf01_eligible: false,
  formal_cf03_eligible: false,
  generated_at: generatedAt,
  adjudicator: adjudicators.size === 1 ? [...adjudicators][0] : null,
  task_count: outputLabels.length,
  human_adjudicated_count: humanAdjudicated,
  human_audit_confirmed_count: humanAuditConfirmed,
  ai_consensus_unreviewed_count: aiConsensusUnreviewed,
  explicit_policy_overrides: overrides,
  source_hashes: hashes,
  labels: outputLabels,
};
const report = {
  schema_version: "1.0",
  pilot_id: taskPayload.pilot_id,
  generated_at: generatedAt,
  status,
  checks: {
    expected_task_count: outputLabels.length === 20,
    expected_human_adjudicated_count: humanAdjudicated === 9,
    expected_human_audit_count: humanAuditConfirmed === 3,
    expected_ai_consensus_count: aiConsensusUnreviewed === 8,
    one_adjudicator: adjudicators.size === 1,
    enums_valid: !errors.some((error) => error.includes("invalid")),
    policy_actions_valid: !errors.some((error) =>
      error.includes("do not match policy"),
    ),
    source_hashes_recorded: Object.values(hashes).every(
      (value) => /^[A-F0-9]{64}$/.test(value),
    ),
  },
  counts: {
    tasks: outputLabels.length,
    human_adjudicated: humanAdjudicated,
    human_audit_confirmed: humanAuditConfirmed,
    ai_consensus_unreviewed: aiConsensusUnreviewed,
    explicit_policy_overrides: overrides.length,
    errors: errors.length,
    warnings: warnings.length,
  },
  errors,
  warnings,
  source_hashes: hashes,
  output_file: path.relative(projectRoot, silverPath).replaceAll("\\", "/"),
};

await fs.writeFile(silverPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

console.log(JSON.stringify({ silverPath, reportPath, status, errors }, null, 2));
if (errors.length) process.exitCode = 1;
