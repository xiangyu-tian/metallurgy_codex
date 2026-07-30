import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = process.cwd();
const pilotDir = path.join(projectRoot, "Tools", "core_freeze", "pilot_v1");
const outputDir = path.join(
  projectRoot,
  "outputs",
  "cf01_annotation_20260728",
);

const taskPayload = JSON.parse(
  await fs.readFile(path.join(pilotDir, "track_a_tasks.json"), "utf8"),
);
const aiAPayload = JSON.parse(
  await fs.readFile(
    path.join(pilotDir, "track_a_annotator_a_AI-A.json"),
    "utf8",
  ),
);
const aiBPayload = JSON.parse(
  await fs.readFile(
    path.join(pilotDir, "track_a_annotator_b_AI-B.json"),
    "utf8",
  ),
);

const tasks = taskPayload.tasks;
const aiA = new Map(aiAPayload.annotations.map((row) => [row.task_id, row]));
const aiB = new Map(aiBPayload.annotations.map((row) => [row.task_id, row]));

const colors = {
  navy: "#17365D",
  blue: "#1F4E78",
  teal: "#0F6B6D",
  paleBlue: "#D9EAF7",
  paleYellow: "#FFF2CC",
  paleGreen: "#E2F0D9",
  paleRed: "#FCE4D6",
  paleGray: "#F2F2F2",
  text: "#1F2937",
  border: "#CBD5E1",
  white: "#FFFFFF",
};

const coreFields = [
  {
    key: "evidence_requirement",
    label: "证据需求",
    values: ["none", "optional", "required"],
  },
  {
    key: "answerability",
    label: "可回答性",
    values: [
      "answerable",
      "ambiguous_request",
      "missing_task_information",
    ],
  },
  {
    key: "information_status",
    label: "执行信息",
    values: [
      "sufficient",
      "missing_execution_input",
      "ambiguous_execution_input",
    ],
  },
  {
    key: "capability_status",
    label: "能力状态",
    values: ["available", "unavailable", "uncertain"],
  },
  {
    key: "risk_status",
    label: "风险状态",
    values: ["normal", "review_required"],
  },
];

const auditTaskIds = new Set([
  "TA-PILOT-001",
  "TA-PILOT-002",
  "TA-PILOT-006",
]);

const labelDictionary = [
  ["evidence_requirement", "none", "可靠回答不需要外部专业计算证据"],
  ["evidence_requirement", "optional", "直接推导与工具计算均可能合理"],
  ["evidence_requirement", "required", "必须依赖专业数据、模型、复杂计算或审计证据"],
  ["answerability", "answerable", "对象、目标和语义完整"],
  ["answerability", "ambiguous_request", "存在多个合理意图或对象，需要用户选择"],
  [
    "answerability",
    "missing_task_information",
    "缺少对象、指代或任务目标，无法可靠理解",
  ],
  ["information_status", "sufficient", "粗粒度执行输入充分"],
  [
    "information_status",
    "missing_execution_input",
    "任务明确，但缺少执行所需工况或参数",
  ],
  [
    "information_status",
    "ambiguous_execution_input",
    "输入单位、相态、材料或条件解释存在歧义",
  ],
  ["capability_status", "available", "冻结能力目录明确包含该能力"],
  ["capability_status", "unavailable", "冻结能力目录明确不包含该能力"],
  ["capability_status", "uncertain", "需进一步检索或人工确认"],
  ["risk_status", "normal", "不触发额外人工审核"],
  [
    "risk_status",
    "review_required",
    "涉及工程控制、安全、权限或显著现实损失",
  ],
  ["allowed_actions", "answer", "直接回答"],
  ["allowed_actions", "call", "调用或进入候选工具检索"],
  ["allowed_actions", "clarify", "向用户追问"],
  ["allowed_actions", "refuse", "拒绝执行"],
  ["allowed_actions", "escalate", "升级人工复核"],
  ["annotation_confidence", "high", "规则和边界明确"],
  ["annotation_confidence", "medium", "存在可解释的不确定性"],
  ["annotation_confidence", "low", "无法稳定判断，需要重点裁决"],
];

const boundaryFlags = [
  "missing_object",
  "missing_parameter",
  "missing_task_info",
  "missing_execution_info",
  "ambiguous_material",
  "ambiguous_phase",
  "ambiguous_condition",
  "capability_unavailable",
  "tool_unavailable",
  "out_of_domain",
  "unsupported_system",
  "unsupported_phase",
  "unsupported_database",
  "high_risk",
  "permission_required",
  "conflicting_requirements",
];

function setTitle(sheet, range, text) {
  sheet.getRange(range).merge();
  const cell = sheet.getRange(range.split(":")[0]);
  cell.values = [[text]];
  cell.format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 16 },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  sheet.getRange(range).format.rowHeight = 30;
}

function styleHeader(range) {
  range.format = {
    fill: colors.blue,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "inside", style: "thin", color: colors.border },
  };
  range.format.rowHeight = 32;
}

function styleTableBody(range) {
  range.format = {
    font: { color: colors.text, size: 10 },
    verticalAlignment: "top",
    wrapText: true,
    borders: {
      insideHorizontal: { style: "thin", color: "#E5E7EB" },
    },
  };
}

function joinSet(value) {
  return [...new Set(value || [])].sort().join(" | ");
}

function sameSet(left, right) {
  return joinSet(left) === joinSet(right);
}

function jaccard(left, right) {
  const l = new Set(left || []);
  const r = new Set(right || []);
  const union = new Set([...l, ...r]);
  if (union.size === 0) return 1;
  let intersection = 0;
  for (const item of l) if (r.has(item)) intersection += 1;
  return intersection / union.size;
}

function cohenKappa(left, right, labels) {
  const n = left.length;
  const observed =
    left.reduce((total, value, index) => total + (value === right[index]), 0) /
    n;
  const expected = labels.reduce((total, label) => {
    const lc = left.filter((value) => value === label).length / n;
    const rc = right.filter((value) => value === label).length / n;
    return total + lc * rc;
  }, 0);
  if (Math.abs(1 - expected) < 1e-12) return observed === 1 ? 1 : 0;
  return (observed - expected) / (1 - expected);
}

function validateInputs() {
  const errors = [];
  const taskIds = tasks.map((task) => task.task_id);
  if (taskIds.length !== 20 || new Set(taskIds).size !== taskIds.length) {
    errors.push("Track A任务必须恰好包含20个唯一ID");
  }
  for (const [label, source] of [
    ["AI-A", aiA],
    ["AI-B", aiB],
  ]) {
    if (source.size !== taskIds.length) {
      errors.push(`${label}记录数不是20`);
    }
    for (const taskId of taskIds) {
      const row = source.get(taskId);
      if (!row) {
        errors.push(`${label}缺少${taskId}`);
        continue;
      }
      for (const field of coreFields) {
        if (!field.values.includes(row[field.key])) {
          errors.push(`${label}/${taskId}/${field.key}枚举非法`);
        }
      }
      if (!Array.isArray(row.allowed_actions) || row.allowed_actions.length === 0) {
        errors.push(`${label}/${taskId}/allowed_actions为空`);
      }
      if (!Array.isArray(row.boundary_flags)) {
        errors.push(`${label}/${taskId}/boundary_flags不是数组`);
      }
    }
  }
  if (errors.length) throw new Error(errors.join("\n"));
}

validateInputs();
await fs.mkdir(outputDir, { recursive: true });

async function buildHumanWorkbook() {
  const workbook = Workbook.create();
  workbook.comments.setSelf({ displayName: "Codex" });
  const instructions = workbook.worksheets.add("填写说明");
  const annotation = workbook.worksheets.add("人工盲标");
  const dictionary = workbook.worksheets.add("标签字典");

  instructions.showGridLines = false;
  annotation.showGridLines = false;
  dictionary.showGridLines = false;

  setTitle(instructions, "A1:F1", "CF-01 Track A 人工首轮盲标工作簿");
  instructions.getRange("A3:F3").merge();
  instructions.getRange("A3").values = [[
    "本工作簿不包含AI答案。请先独立完成20题，完成前不要打开AI复核工作簿。",
  ]];
  instructions.getRange("A3:F3").format = {
    fill: colors.paleYellow,
    font: { bold: true, color: "#7C5700" },
    wrapText: true,
  };
  instructions.getRange("A5:B10").values = [
    ["元数据", "填写值"],
    ["标注者姓名", ""],
    ["标注者角色", ""],
    ["开始时间（含时区）", ""],
    ["完成时间（含时区）", ""],
    ["独立完成声明", "完成后填写：是"],
  ];
  styleHeader(instructions.getRange("A5:B5"));
  instructions.getRange("B6:B10").format = {
    fill: colors.paleYellow,
    borders: { preset: "outside", style: "thin", color: "#D6B656" },
  };
  instructions.getRange("D5:E9").values = [
    ["进度", "值"],
    ["任务总数", 20],
    ["已完成", null],
    ["待填写", null],
    ["完成率", null],
  ];
  styleHeader(instructions.getRange("D5:E5"));
  instructions.getRange("E7").formulas = [[
    "=COUNTIF('人工盲标'!Q2:Q21,\"已完成\")",
  ]];
  instructions.getRange("E8").formulas = [["=E6-E7"]];
  instructions.getRange("E9").formulas = [["=E7/E6"]];
  instructions.getRange("E9").format.numberFormat = "0%";
  instructions.getRange("A12:F18").values = [
    ["填写规则", "", "", "", "", ""],
    ["1", "黄色列为人工填写区；题号、问题和上下文不得修改。", "", "", "", ""],
    ["2", "D—H与O列使用下拉框；I—L多值字段用“ | ”分隔。", "", "", "", ""],
    ["3", "allowed_actions必须至少有一个动作。", "", "", "", ""],
    ["4", "不回答题目，也不计算题目数值，只做标签判断。", "", "", "", ""],
    ["5", "信息不足时如实填写missing_inputs，并降低置信度。", "", "", "", ""],
    ["6", "全部完成后保存原始文件，再进入AI差异复核。", "", "", "", ""],
  ];
  instructions.getRange("A12:F12").merge();
  instructions.getRange("A12").format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
  };
  for (let row = 13; row <= 18; row += 1) {
    instructions.getRange(`B${row}:F${row}`).merge();
  }
  instructions.getRange("A13:F18").format.wrapText = true;
  instructions.getRange("A1:F18").format.font = { name: "Microsoft YaHei" };
  instructions.getRange("A:A").format.columnWidth = 18;
  instructions.getRange("B:B").format.columnWidth = 42;
  instructions.getRange("C:C").format.columnWidth = 4;
  instructions.getRange("D:D").format.columnWidth = 18;
  instructions.getRange("E:E").format.columnWidth = 16;
  instructions.getRange("F:F").format.columnWidth = 8;

  const headers = [
    "task_id",
    "问题",
    "上下文",
    "evidence_requirement",
    "answerability",
    "information_status",
    "capability_status",
    "risk_status",
    "boundary_flags（|分隔）",
    "allowed_actions（|分隔）",
    "required_inputs（|分隔）",
    "missing_inputs（|分隔）",
    "coarse_capability",
    "action_reason",
    "annotation_confidence",
    "disagreement_notes",
    "完成状态",
  ];
  annotation.getRange("A1:Q1").values = [headers];
  styleHeader(annotation.getRange("A1:Q1"));
  const dataRows = tasks.map((task) => [
    task.task_id,
    task.question,
    task.context ?? "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    null,
  ]);
  annotation.getRange("A2:Q21").values = dataRows;
  annotation.getRange("Q2").formulas = [[
    '=IF(AND(D2<>"",E2<>"",F2<>"",G2<>"",H2<>"",J2<>"",N2<>"",O2<>""),"已完成","待填写")',
  ]];
  annotation.getRange("Q2:Q21").fillDown();
  styleTableBody(annotation.getRange("A2:Q21"));
  annotation.getRange("D2:P21").format.fill = colors.paleYellow;
  annotation.getRange("A2:C21").format.fill = colors.paleGray;
  annotation.getRange("Q2:Q21").format.fill = colors.paleBlue;
  annotation.getRange("Q2:Q21").conditionalFormats.add("containsText", {
    text: "已完成",
    format: { fill: colors.paleGreen, font: { color: "#375623", bold: true } },
  });
  annotation.getRange("D2:D21").dataValidation = {
    rule: { type: "list", values: coreFields[0].values },
  };
  annotation.getRange("E2:E21").dataValidation = {
    rule: { type: "list", values: coreFields[1].values },
  };
  annotation.getRange("F2:F21").dataValidation = {
    rule: { type: "list", values: coreFields[2].values },
  };
  annotation.getRange("G2:G21").dataValidation = {
    rule: { type: "list", values: coreFields[3].values },
  };
  annotation.getRange("H2:H21").dataValidation = {
    rule: { type: "list", values: coreFields[4].values },
  };
  annotation.getRange("O2:O21").dataValidation = {
    rule: { type: "list", values: ["high", "medium", "low"] },
  };
  annotation.freezePanes.freezeRows(1);
  annotation.freezePanes.freezeColumns(3);
  annotation.tables.add("A1:Q21", true, "HumanBlindAnnotationTable");
  const widths = [16, 44, 36, 19, 22, 24, 20, 18, 30, 27, 28, 28, 24, 48, 22, 30, 14];
  widths.forEach((width, index) => {
    annotation.getRangeByIndexes(0, index, 21, 1).format.columnWidth = width;
  });
  annotation.getRange("A2:Q21").format.rowHeight = 54;

  setTitle(dictionary, "A1:D1", "标签字典与多值填写规则");
  dictionary.getRange("A3:D3").values = [["字段", "允许值", "含义", "填写方式"]];
  styleHeader(dictionary.getRange("A3:D3"));
  const dictRows = labelDictionary.map((row) => [
    row[0],
    row[1],
    row[2],
    ["boundary_flags", "allowed_actions"].includes(row[0])
      ? "多个值用 | 分隔"
      : "单选",
  ]);
  const start = 4;
  dictionary.getRange(`A${start}:D${start + dictRows.length - 1}`).values = dictRows;
  styleTableBody(dictionary.getRange(`A${start}:D${start + dictRows.length - 1}`));
  const flagStart = start + dictRows.length + 2;
  dictionary.getRange(`A${flagStart}:D${flagStart}`).values = [[
    "boundary_flags允许值",
    "",
    "",
    "多个值用 | 分隔；没有则留空",
  ]];
  dictionary.getRange(`A${flagStart}:C${flagStart}`).merge();
  dictionary.getRange(`A${flagStart}:D${flagStart}`).format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
  };
  const flagRows = boundaryFlags.map((flag) => [flag, "", "", ""]);
  dictionary.getRange(
    `A${flagStart + 1}:D${flagStart + flagRows.length}`,
  ).values = flagRows;
  dictionary.getRange("A:D").format.wrapText = true;
  dictionary.getRange("A:A").format.columnWidth = 28;
  dictionary.getRange("B:B").format.columnWidth = 30;
  dictionary.getRange("C:C").format.columnWidth = 58;
  dictionary.getRange("D:D").format.columnWidth = 26;
  dictionary.freezePanes.freezeRows(3);

  return workbook;
}

function buildComparisonRows() {
  return tasks.map((task) => {
    const a = aiA.get(task.task_id);
    const b = aiB.get(task.task_id);
    return {
      task,
      a,
      b,
      differences: [
        ...coreFields
          .filter((field) => a[field.key] !== b[field.key])
          .map((field) => field.key),
        ...(sameSet(a.allowed_actions, b.allowed_actions)
          ? []
          : ["allowed_actions"]),
        ...(sameSet(a.boundary_flags, b.boundary_flags)
          ? []
          : ["boundary_flags"]),
      ],
    };
  });
}

function substantiveDifferences(a, b) {
  return [
    ...coreFields
      .filter((field) => a[field.key] !== b[field.key])
      .map((field) => field.key),
    ...(sameSet(a.allowed_actions, b.allowed_actions)
      ? []
      : ["allowed_actions"]),
  ];
}

async function buildReviewWorkbook() {
  const workbook = Workbook.create();
  workbook.comments.setSelf({ displayName: "Codex" });
  const summary = workbook.worksheets.add("一致性摘要");
  const differences = workbook.worksheets.add("核心分歧审查");
  const comparison = workbook.worksheets.add("AI逐题对比");
  const rawA = workbook.worksheets.add("AI-A原始");
  const rawB = workbook.worksheets.add("AI-B原始");
  for (const sheet of [summary, differences, comparison, rawA, rawB]) {
    sheet.showGridLines = false;
  }
  const compared = buildComparisonRows();

  setTitle(summary, "A1:H1", "CF-01 AI-A / AI-B 辅助标注复核");
  summary.getRange("A3:H3").merge();
  summary.getRange("A3").values = [[
    "仅在人类首轮盲标完成并保存后使用。本工作簿不能替代两名人类标注者的一致性证据。",
  ]];
  summary.getRange("A3:H3").format = {
    fill: colors.paleRed,
    font: { bold: true, color: "#9C0006" },
    wrapText: true,
  };
  summary.getRange("A5:B10").values = [
    ["数据质量检查", "结果"],
    ["AI-A记录数", aiA.size],
    ["AI-B记录数", aiB.size],
    ["AI-A元数据", aiAPayload.annotator_name ? "完整" : "缺失"],
    ["AI-B元数据", aiBPayload.annotator_name ? "完整" : "缺失"],
    [
      "核心/动作/边界存在分歧任务数",
      compared.filter((row) => row.differences.length).length,
    ],
  ];
  styleHeader(summary.getRange("A5:B5"));
  summary.getRange("B9").format.fill = aiBPayload.annotator_name
    ? colors.paleGreen
    : colors.paleYellow;
  summary.getRange("D5:H5").values = [[
    "字段",
    "一致数",
    "总数",
    "原始一致率",
    "Cohen κ / 平均Jaccard",
  ]];
  styleHeader(summary.getRange("D5:H5"));
  const metricRows = coreFields.map((field) => {
    const left = compared.map((row) => row.a[field.key]);
    const right = compared.map((row) => row.b[field.key]);
    const agreements = left.filter((value, index) => value === right[index]).length;
    return [
      field.label,
      agreements,
      compared.length,
      agreements / compared.length,
      cohenKappa(left, right, field.values),
    ];
  });
  const actionAgreement = compared.filter((row) =>
    sameSet(row.a.allowed_actions, row.b.allowed_actions),
  ).length;
  metricRows.push([
    "allowed_actions集合",
    actionAgreement,
    compared.length,
    actionAgreement / compared.length,
    compared.reduce(
      (total, row) =>
        total + jaccard(row.a.allowed_actions, row.b.allowed_actions),
      0,
    ) / compared.length,
  ]);
  const flagAgreement = compared.filter((row) =>
    sameSet(row.a.boundary_flags, row.b.boundary_flags),
  ).length;
  metricRows.push([
    "boundary_flags集合",
    flagAgreement,
    compared.length,
    flagAgreement / compared.length,
    compared.reduce(
      (total, row) =>
        total + jaccard(row.a.boundary_flags, row.b.boundary_flags),
      0,
    ) / compared.length,
  ]);
  summary.getRange(`D6:H${5 + metricRows.length}`).values = metricRows;
  styleTableBody(summary.getRange(`D6:H${5 + metricRows.length}`));
  summary.getRange(`G6:H${5 + metricRows.length}`).format.numberFormat = "0.000";
  summary.getRange("A14:H19").values = [
    ["重要说明", "", "", "", "", "", "", ""],
    ["1", "上述κ和Jaccard是AI—AI诊断值，不是双人类一致性。", "", "", "", "", "", ""],
    ["2", "AI-A模型记录为deepseek-v4-pro；AI-B模型身份已补录。时间字段不作为本轮AI辅助试标门槛。", "", "", "", "", "", ""],
    ["3", "AI-A对20题全部标为high置信度，应由人类重点检查其置信度校准。", "", "", "", "", "", ""],
    ["4", "人类应先完成盲标，再查看“核心分歧审查”工作表。", "", "", "", "", "", ""],
    ["5", "最终金标准必须由人类确认，并登记为AI辅助单专家流程。", "", "", "", "", "", ""],
  ];
  summary.getRange("A14:H14").merge();
  summary.getRange("A14").format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
  };
  for (let row = 15; row <= 19; row += 1) {
    summary.getRange(`B${row}:H${row}`).merge();
  }
  summary.getRange("A15:H19").format.wrapText = true;
  summary.getRange("A:A").format.columnWidth = 20;
  summary.getRange("B:B").format.columnWidth = 24;
  summary.getRange("C:C").format.columnWidth = 4;
  summary.getRange("D:D").format.columnWidth = 25;
  summary.getRange("E:H").format.columnWidth = 18;

  const diffHeaders = [
    "task_id",
    "问题",
    "分歧字段",
    "AI-A核心结论",
    "AI-B核心结论",
    "AI-A理由",
    "AI-B理由",
    "人工最终决定",
    "人工裁决理由",
  ];
  differences.getRange("A1:I1").values = [diffHeaders];
  styleHeader(differences.getRange("A1:I1"));
  const diffRows = compared
    .filter((row) => row.differences.length)
    .map((row) => [
      row.task.task_id,
      row.task.question,
      row.differences.join(" | "),
      coreFields
        .map((field) => `${field.label}:${row.a[field.key]}`)
        .concat(`动作:${joinSet(row.a.allowed_actions)}`)
        .join("\n"),
      coreFields
        .map((field) => `${field.label}:${row.b[field.key]}`)
        .concat(`动作:${joinSet(row.b.allowed_actions)}`)
        .join("\n"),
      row.a.action_reason,
      row.b.action_reason,
      "",
      "",
    ]);
  differences.getRange(`A2:I${1 + diffRows.length}`).values = diffRows;
  styleTableBody(differences.getRange(`A2:I${1 + diffRows.length}`));
  differences.getRange(`H2:I${1 + diffRows.length}`).format.fill =
    colors.paleYellow;
  differences.tables.add(
    `A1:I${1 + diffRows.length}`,
    true,
    "AiDifferenceReviewTable",
  );
  differences.freezePanes.freezeRows(1);
  differences.freezePanes.freezeColumns(2);
  const diffWidths = [16, 46, 34, 38, 38, 48, 48, 34, 48];
  diffWidths.forEach((width, index) => {
    differences
      .getRangeByIndexes(0, index, 1 + diffRows.length, 1)
      .format.columnWidth = width;
  });
  differences.getRange(`A2:I${1 + diffRows.length}`).format.rowHeight = 88;

  const comparisonHeaders = [
    "task_id",
    "问题",
    ...coreFields.flatMap((field) => [
      `${field.label}_AI-A`,
      `${field.label}_AI-B`,
      `${field.label}_一致`,
    ]),
    "动作_AI-A",
    "动作_AI-B",
    "动作一致",
    "边界标志_AI-A",
    "边界标志_AI-B",
    "边界标志一致",
    "置信度_AI-A",
    "置信度_AI-B",
    "理由_AI-A",
    "理由_AI-B",
  ];
  comparison.getRange("A1:AA1").values = [comparisonHeaders];
  styleHeader(comparison.getRange("A1:AA1"));
  const compareRows = compared.map((row) => {
    const coreCells = coreFields.flatMap((field) => [
      row.a[field.key],
      row.b[field.key],
      row.a[field.key] === row.b[field.key] ? "一致" : "分歧",
    ]);
    return [
      row.task.task_id,
      row.task.question,
      ...coreCells,
      joinSet(row.a.allowed_actions),
      joinSet(row.b.allowed_actions),
      sameSet(row.a.allowed_actions, row.b.allowed_actions) ? "一致" : "分歧",
      joinSet(row.a.boundary_flags),
      joinSet(row.b.boundary_flags),
      sameSet(row.a.boundary_flags, row.b.boundary_flags) ? "一致" : "分歧",
      row.a.annotation_confidence,
      row.b.annotation_confidence,
      row.a.action_reason,
      row.b.action_reason,
    ];
  });
  comparison.getRange("A2:AA21").values = compareRows;
  styleTableBody(comparison.getRange("A2:AA21"));
  for (const col of ["E", "H", "K", "N", "Q", "T", "W"]) {
    comparison.getRange(`${col}2:${col}21`).conditionalFormats.add(
      "containsText",
      {
        text: "分歧",
        format: { fill: colors.paleRed, font: { color: "#9C0006", bold: true } },
      },
    );
    comparison.getRange(`${col}2:${col}21`).conditionalFormats.add(
      "containsText",
      {
        text: "一致",
        format: { fill: colors.paleGreen, font: { color: "#375623" } },
      },
    );
  }
  comparison.tables.add("A1:AA21", true, "AiAnnotationComparisonTable");
  comparison.freezePanes.freezeRows(1);
  comparison.freezePanes.freezeColumns(2);
  comparison.getRange("A:A").format.columnWidth = 16;
  comparison.getRange("B:B").format.columnWidth = 44;
  comparison.getRange("C:W").format.columnWidth = 19;
  comparison.getRange("X:Y").format.columnWidth = 16;
  comparison.getRange("Z:AA").format.columnWidth = 48;
  comparison.getRange("A2:AA21").format.rowHeight = 64;

  const rawHeaders = [
    "task_id",
    "evidence_requirement",
    "answerability",
    "information_status",
    "capability_status",
    "risk_status",
    "boundary_flags",
    "allowed_actions",
    "required_inputs",
    "missing_inputs",
    "coarse_capability",
    "action_reason",
    "annotation_confidence",
    "disagreement_notes",
  ];
  for (const [sheet, source, tableName] of [
    [rawA, aiA, "AiARawAnnotationTable"],
    [rawB, aiB, "AiBRawAnnotationTable"],
  ]) {
    sheet.getRange("A1:N1").values = [rawHeaders];
    styleHeader(sheet.getRange("A1:N1"));
    const rows = tasks.map((task) => {
      const row = source.get(task.task_id);
      return [
        row.task_id,
        row.evidence_requirement,
        row.answerability,
        row.information_status,
        row.capability_status,
        row.risk_status,
        joinSet(row.boundary_flags),
        joinSet(row.allowed_actions),
        joinSet(row.required_inputs),
        joinSet(row.missing_inputs),
        row.coarse_capability ?? "",
        row.action_reason,
        row.annotation_confidence,
        row.disagreement_notes ?? "",
      ];
    });
    sheet.getRange("A2:N21").values = rows;
    styleTableBody(sheet.getRange("A2:N21"));
    sheet.tables.add("A1:N21", true, tableName);
    sheet.freezePanes.freezeRows(1);
    sheet.freezePanes.freezeColumns(1);
    const rawWidths = [16, 20, 24, 25, 21, 19, 32, 28, 34, 34, 25, 58, 22, 28];
    rawWidths.forEach((width, index) => {
      sheet.getRangeByIndexes(0, index, 21, 1).format.columnWidth = width;
    });
    sheet.getRange("A2:N21").format.rowHeight = 58;
  }

  return workbook;
}

async function buildAdjudicationWorkbook() {
  const workbook = Workbook.create();
  workbook.comments.setSelf({ displayName: "Codex" });
  const instructions = workbook.worksheets.add("使用说明");
  const review = workbook.worksheets.add("裁决任务");
  const finalLabels = workbook.worksheets.add("最终标签");
  const differences = workbook.worksheets.add("差异明细");
  const sources = workbook.worksheets.add("AI来源明细");
  const dictionary = workbook.worksheets.add("标签字典");
  for (const sheet of [
    instructions,
    review,
    finalLabels,
    differences,
    sources,
    dictionary,
  ]) {
    sheet.showGridLines = false;
  }

  const compared = buildComparisonRows();
  const selected = compared
    .map((row) => ({
      ...row,
      substantive: substantiveDifferences(row.a, row.b),
      sampleType: auditTaskIds.has(row.task.task_id)
        ? "一致性抽查"
        : "实质性分歧",
    }))
    .filter(
      (row) =>
        row.substantive.length > 0 || auditTaskIds.has(row.task.task_id),
    );
  const substantiveCount = selected.filter(
    (row) => row.sampleType === "实质性分歧",
  ).length;
  const auditCount = selected.filter(
    (row) => row.sampleType === "一致性抽查",
  ).length;
  if (selected.length !== 12 || substantiveCount !== 9 || auditCount !== 3) {
    throw new Error(
      `裁决样本应为9道实质性分歧和3道抽查，实际为${substantiveCount}+${auditCount}`,
    );
  }
  for (const row of selected.filter(
    (item) => item.sampleType === "一致性抽查",
  )) {
    if (
      row.substantive.length > 0 ||
      !sameSet(row.a.boundary_flags, row.b.boundary_flags)
    ) {
      throw new Error(`${row.task.task_id}不是全字段AI共识样本`);
    }
  }

  setTitle(instructions, "A1:H1", "CF-01 AI共识预标＋人工精简裁决");
  instructions.getRange("A3:H3").merge();
  instructions.getRange("A3").values = [[
    "本工作簿跳过20题人工盲标：人工裁决9道实质性分歧，并抽查3道AI完全一致样本。结果属于provisional silver，不构成双人类标注证据。",
  ]];
  instructions.getRange("A3:H3").format = {
    fill: colors.paleYellow,
    font: { bold: true, color: "#7C5700" },
    wrapText: true,
  };
  instructions.getRange("A5:B12").values = [
    ["执行信息", "值"],
    ["AI-A模型", aiAPayload.annotator_name ?? "unknown"],
    ["AI-B模型", aiBPayload.annotator_name ?? "unknown"],
    ["实质性分歧", substantiveCount],
    ["一致性抽查", auditCount],
    ["总裁决任务", selected.length],
    ["完成任务", null],
    ["待完成任务", null],
  ];
  styleHeader(instructions.getRange("A5:B5"));
  instructions.getRange("B11").formulas = [[
    '=COUNTIF(\'最终标签\'!P2:P13,"已完成")',
  ]];
  instructions.getRange("B12").formulas = [["=B10-B11"]];
  instructions.getRange("D5:E10").values = [
    ["质量控制", "结果"],
    ["需专业复核", null],
    ["低置信裁决", null],
    ["标签等级", "provisional_silver"],
    ["人工盲标", "false"],
    ["CF-01通过", "false"],
  ];
  styleHeader(instructions.getRange("D5:E5"));
  instructions.getRange("E6").formulas = [[
    '=COUNTIF(\'最终标签\'!L2:L13,"需要")',
  ]];
  instructions.getRange("E7").formulas = [[
    '=COUNTIF(\'最终标签\'!K2:K13,"low")',
  ]];
  instructions.getRange("A14:H21").values = [
    ["操作顺序", "", "", "", "", "", "", ""],
    ["1", "先查看“裁决任务”的问题、分歧字段和两份AI理由。", "", "", "", "", "", ""],
    ["2", "在“最终标签”中确认预填共识值，只填写橙色空白分歧单元格。", "", "", "", "", "", ""],
    ["3", "allowed_actions必须由最终核心标签和政策矩阵决定，不能简单多数投票。", "", "", "", "", "", ""],
    ["4", "boundary_flags是解释性多标签，不要求AI完全一致；可留空或用“ | ”分隔。", "", "", "", "", "", ""],
    ["5", "无法确认冶金适用域时，将“需专业复核”设为“需要”，不要强行判断。", "", "", "", "", "", ""],
    ["6", "三道抽查由固定种子CF01-AUDIT-V1按none/optional/required分层选取。", "", "", "", "", "", ""],
    ["7", "所有任务完成后保存原始Excel，再由程序转换为正式JSON和裁决记录。", "", "", "", "", "", ""],
  ];
  instructions.getRange("A14:H14").merge();
  instructions.getRange("A14").format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
  };
  for (let row = 15; row <= 21; row += 1) {
    instructions.getRange(`B${row}:H${row}`).merge();
  }
  instructions.getRange("A1:H21").format.font = { name: "Microsoft YaHei" };
  instructions.getRange("A:A").format.columnWidth = 18;
  instructions.getRange("B:B").format.columnWidth = 42;
  instructions.getRange("C:C").format.columnWidth = 4;
  instructions.getRange("D:D").format.columnWidth = 18;
  instructions.getRange("E:E").format.columnWidth = 24;
  instructions.getRange("F:H").format.columnWidth = 8;
  instructions.getRange("A3:H3").format.rowHeight = 44;
  instructions.getRange("A15:H21").format.rowHeight = 30;

  const reviewHeaders = [
    "task_id",
    "样本类型",
    "问题",
    "上下文",
    "需裁决字段",
    "AI-A核心结论",
    "AI-B核心结论",
    "AI-A理由",
    "AI-B理由",
    "人工任务",
  ];
  review.getRange("A1:J1").values = [reviewHeaders];
  styleHeader(review.getRange("A1:J1"));
  const coreSummary = (row) =>
    coreFields
      .map((field) => `${field.label}:${row[field.key]}`)
      .concat(`动作:${joinSet(row.allowed_actions)}`)
      .concat(`边界:${joinSet(row.boundary_flags) || "无"}`)
      .join("\n");
  const reviewRows = selected.map((row) => [
    row.task.task_id,
    row.sampleType,
    row.task.question,
    row.task.context ?? "",
    row.sampleType === "一致性抽查"
      ? "AI全字段一致，抽查正确性"
      : row.substantive.join(" | "),
    coreSummary(row.a),
    coreSummary(row.b),
    row.a.action_reason,
    row.b.action_reason,
    row.sampleType === "一致性抽查"
      ? "独立判断AI共识是否合理"
      : "判断分歧字段，并核对其余共识值",
  ]);
  review.getRange(`A2:J${selected.length + 1}`).values = reviewRows;
  styleTableBody(review.getRange(`A2:J${selected.length + 1}`));
  review.getRange(`B2:B${selected.length + 1}`).conditionalFormats.add(
    "containsText",
    {
      text: "实质性分歧",
      format: { fill: colors.paleRed, font: { color: "#9C0006", bold: true } },
    },
  );
  review.getRange(`B2:B${selected.length + 1}`).conditionalFormats.add(
    "containsText",
    {
      text: "一致性抽查",
      format: { fill: colors.paleBlue, font: { color: colors.blue, bold: true } },
    },
  );
  review.tables.add(
    `A1:J${selected.length + 1}`,
    true,
    "AdjudicationTaskTable",
  );
  review.freezePanes.freezeRows(1);
  review.freezePanes.freezeColumns(2);
  [16, 16, 44, 28, 30, 38, 38, 52, 52, 32].forEach((width, index) => {
    review
      .getRangeByIndexes(0, index, selected.length + 1, 1)
      .format.columnWidth = width;
  });
  review.getRange(`A2:J${selected.length + 1}`).format.rowHeight = 100;

  const finalHeaders = [
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
    "裁决日期",
    "补充说明",
    "完成状态",
  ];
  finalLabels.getRange("A1:P1").values = [finalHeaders];
  styleHeader(finalLabels.getRange("A1:P1"));
  const finalRows = selected.map((row) => {
    const consensusValue = (key) =>
      row.a[key] === row.b[key] ? row.a[key] : "";
    return [
      row.task.task_id,
      row.sampleType,
      consensusValue("evidence_requirement"),
      consensusValue("answerability"),
      consensusValue("information_status"),
      consensusValue("capability_status"),
      consensusValue("risk_status"),
      sameSet(row.a.allowed_actions, row.b.allowed_actions)
        ? joinSet(row.a.allowed_actions)
        : "",
      sameSet(row.a.boundary_flags, row.b.boundary_flags)
        ? joinSet(row.a.boundary_flags)
        : "",
      "",
      "",
      "",
      "",
      "",
      "",
      null,
    ];
  });
  finalLabels.getRange(`A2:P${selected.length + 1}`).values = finalRows;
  finalLabels.getRange("P2").formulas = [[
    '=IF(AND(C2<>"",D2<>"",E2<>"",F2<>"",G2<>"",H2<>"",J2<>"",K2<>"",L2<>""),"已完成","待填写")',
  ]];
  finalLabels.getRange(`P2:P${selected.length + 1}`).fillDown();
  styleTableBody(finalLabels.getRange(`A2:P${selected.length + 1}`));
  finalLabels.getRange(`A2:B${selected.length + 1}`).format.fill =
    colors.paleGray;
  finalLabels.getRange(`C2:O${selected.length + 1}`).format.fill =
    colors.paleYellow;
  for (let rowIndex = 0; rowIndex < selected.length; rowIndex += 1) {
    const row = selected[rowIndex];
    const excelRow = rowIndex + 2;
    coreFields.forEach((field, fieldIndex) => {
      if (row.a[field.key] !== row.b[field.key]) {
        finalLabels.getCell(excelRow - 1, fieldIndex + 2).format.fill =
          colors.paleRed;
      }
    });
    if (!sameSet(row.a.allowed_actions, row.b.allowed_actions)) {
      finalLabels.getCell(excelRow - 1, 7).format.fill = colors.paleRed;
    }
  }
  finalLabels.getRange(`P2:P${selected.length + 1}`).format.fill =
    colors.paleBlue;
  finalLabels.getRange(`P2:P${selected.length + 1}`).conditionalFormats.add(
    "containsText",
    {
      text: "已完成",
      format: { fill: colors.paleGreen, font: { color: "#375623", bold: true } },
    },
  );
  coreFields.forEach((field, index) => {
    finalLabels.getRangeByIndexes(1, index + 2, selected.length, 1).dataValidation = {
      rule: { type: "list", values: field.values },
    };
  });
  finalLabels.getRange(`K2:K${selected.length + 1}`).dataValidation = {
    rule: { type: "list", values: ["high", "medium", "low"] },
  };
  finalLabels.getRange(`L2:L${selected.length + 1}`).dataValidation = {
    rule: { type: "list", values: ["需要", "不需要", "无法判断"] },
  };
  finalLabels.tables.add(
    `A1:P${selected.length + 1}`,
    true,
    "FinalAdjudicationLabelTable",
  );
  finalLabels.freezePanes.freezeRows(1);
  finalLabels.freezePanes.freezeColumns(2);
  [16, 16, 20, 24, 25, 21, 18, 27, 32, 52, 18, 18, 18, 20, 34, 14].forEach(
    (width, index) => {
      finalLabels
        .getRangeByIndexes(0, index, selected.length + 1, 1)
        .format.columnWidth = width;
    },
  );
  finalLabels.getRange(`A2:P${selected.length + 1}`).format.rowHeight = 58;

  const diffHeaders = [
    "task_id",
    "样本类型",
    "字段",
    "字段类别",
    "AI-A",
    "AI-B",
    "一致状态",
    "是否需人工判断",
  ];
  differences.getRange("A1:H1").values = [diffHeaders];
  styleHeader(differences.getRange("A1:H1"));
  const diffRows = selected.flatMap((row) => {
    const fieldRows = coreFields.map((field) => [
      row.task.task_id,
      row.sampleType,
      field.key,
      "核心标签",
      row.a[field.key],
      row.b[field.key],
      row.a[field.key] === row.b[field.key] ? "一致" : "分歧",
      row.a[field.key] === row.b[field.key] ? "核对" : "需要",
    ]);
    fieldRows.push([
      row.task.task_id,
      row.sampleType,
      "allowed_actions",
      "动作标签",
      joinSet(row.a.allowed_actions),
      joinSet(row.b.allowed_actions),
      sameSet(row.a.allowed_actions, row.b.allowed_actions) ? "一致" : "分歧",
      sameSet(row.a.allowed_actions, row.b.allowed_actions) ? "核对" : "需要",
    ]);
    fieldRows.push([
      row.task.task_id,
      row.sampleType,
      "boundary_flags",
      "解释性标签",
      joinSet(row.a.boundary_flags),
      joinSet(row.b.boundary_flags),
      sameSet(row.a.boundary_flags, row.b.boundary_flags) ? "一致" : "不同",
      "不强制",
    ]);
    return fieldRows;
  });
  differences.getRange(`A2:H${diffRows.length + 1}`).values = diffRows;
  styleTableBody(differences.getRange(`A2:H${diffRows.length + 1}`));
  differences.getRange(`G2:G${diffRows.length + 1}`).conditionalFormats.add(
    "containsText",
    {
      text: "分歧",
      format: { fill: colors.paleRed, font: { color: "#9C0006", bold: true } },
    },
  );
  differences.tables.add(
    `A1:H${diffRows.length + 1}`,
    true,
    "FieldDifferenceTable",
  );
  differences.freezePanes.freezeRows(1);
  differences.freezePanes.freezeColumns(2);
  [16, 16, 25, 18, 34, 34, 16, 18].forEach((width, index) => {
    differences
      .getRangeByIndexes(0, index, diffRows.length + 1, 1)
      .format.columnWidth = width;
  });
  differences.getRange(`A2:H${diffRows.length + 1}`).format.rowHeight = 36;

  const sourceHeaders = [
    "task_id",
    "样本类型",
    "AI角色",
    "模型",
    "evidence_requirement",
    "answerability",
    "information_status",
    "capability_status",
    "risk_status",
    "boundary_flags",
    "allowed_actions",
    "required_inputs",
    "missing_inputs",
    "coarse_capability",
    "action_reason",
    "annotation_confidence",
    "disagreement_notes",
  ];
  sources.getRange("A1:Q1").values = [sourceHeaders];
  styleHeader(sources.getRange("A1:Q1"));
  const sourceRows = selected.flatMap((row) =>
    [
      ["AI-A", aiAPayload.annotator_name ?? "unknown", row.a],
      ["AI-B", aiBPayload.annotator_name ?? "unknown", row.b],
    ].map(([role, model, source]) => [
      row.task.task_id,
      row.sampleType,
      role,
      model,
      source.evidence_requirement,
      source.answerability,
      source.information_status,
      source.capability_status,
      source.risk_status,
      joinSet(source.boundary_flags),
      joinSet(source.allowed_actions),
      joinSet(source.required_inputs),
      joinSet(source.missing_inputs),
      source.coarse_capability ?? "",
      source.action_reason,
      source.annotation_confidence,
      source.disagreement_notes ?? "",
    ]),
  );
  sources.getRange(`A2:Q${sourceRows.length + 1}`).values = sourceRows;
  styleTableBody(sources.getRange(`A2:Q${sourceRows.length + 1}`));
  sources.tables.add(
    `A1:Q${sourceRows.length + 1}`,
    true,
    "AiAdjudicationSourceTable",
  );
  sources.freezePanes.freezeRows(1);
  sources.freezePanes.freezeColumns(2);
  [16, 16, 13, 24, 20, 24, 25, 21, 18, 34, 28, 30, 30, 24, 58, 18, 28].forEach(
    (width, index) => {
      sources
        .getRangeByIndexes(0, index, sourceRows.length + 1, 1)
        .format.columnWidth = width;
    },
  );
  sources.getRange(`A2:Q${sourceRows.length + 1}`).format.rowHeight = 56;

  setTitle(dictionary, "A1:D1", "裁决标签字典");
  dictionary.getRange("A3:D3").values = [["字段", "允许值", "含义", "裁决要求"]];
  styleHeader(dictionary.getRange("A3:D3"));
  const dictRows = labelDictionary.map((row) => [
    row[0],
    row[1],
    row[2],
    ["boundary_flags"].includes(row[0]) ? "解释性，可多选" : "按指南裁决",
  ]);
  dictionary.getRange(`A4:D${dictRows.length + 3}`).values = dictRows;
  styleTableBody(dictionary.getRange(`A4:D${dictRows.length + 3}`));
  const flagStart = dictRows.length + 5;
  dictionary.getRange(`A${flagStart}:D${flagStart}`).values = [[
    "boundary_flags允许值",
    "",
    "解释性多标签，不纳入完全一致门槛",
    "多个值用 | 分隔；可留空",
  ]];
  dictionary.getRange(`A${flagStart}:B${flagStart}`).merge();
  dictionary.getRange(`A${flagStart}:D${flagStart}`).format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
  };
  dictionary
    .getRange(`A${flagStart + 1}:D${flagStart + boundaryFlags.length}`)
    .values = boundaryFlags.map((flag) => [flag, "", "", ""]);
  dictionary.getRange("A:A").format.columnWidth = 30;
  dictionary.getRange("B:B").format.columnWidth = 32;
  dictionary.getRange("C:C").format.columnWidth = 58;
  dictionary.getRange("D:D").format.columnWidth = 30;
  dictionary.getRange("A:D").format.wrapText = true;
  dictionary.freezePanes.freezeRows(3);

  return workbook;
}

async function verifyAndExport(workbook, filename, renderPlans) {
  const inspect = await workbook.inspect({
    kind: "sheet,table",
    include: "id,name",
    maxChars: 5000,
    tableMaxRows: 4,
    tableMaxCols: 8,
  });
  console.log(inspect.ndjson);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: `${filename} formula error scan`,
  });
  console.log(errors.ndjson);
  for (const plan of renderPlans) {
    const preview = await workbook.render({
      sheetName: plan.sheetName,
      range: plan.range,
      scale: plan.scale ?? 0.85,
      format: "png",
    });
    await fs.writeFile(
      path.join(outputDir, `${filename}-${plan.sheetName}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
  const file = await SpreadsheetFile.exportXlsx(workbook);
  const outputPath = path.join(outputDir, `${filename}.xlsx`);
  await file.save(outputPath);
  return outputPath;
}

const humanWorkbook = await buildHumanWorkbook();
const reviewWorkbook = await buildReviewWorkbook();
const adjudicationWorkbook = await buildAdjudicationWorkbook();

const humanPath = await verifyAndExport(
  humanWorkbook,
  "track_a_human_blind_annotation",
  [
    { sheetName: "填写说明", range: "A1:F18", scale: 1 },
    { sheetName: "人工盲标", range: "A1:Q8", scale: 0.6 },
    { sheetName: "标签字典", range: "A1:D44", scale: 0.8 },
  ],
);
const reviewPath = await verifyAndExport(
  reviewWorkbook,
  "track_a_ai_comparison_review",
  [
    { sheetName: "一致性摘要", range: "A1:H19", scale: 0.9 },
    { sheetName: "核心分歧审查", range: "A1:I10", scale: 0.55 },
    { sheetName: "AI逐题对比", range: "A1:AA7", scale: 0.42 },
    { sheetName: "AI-A原始", range: "A1:N7", scale: 0.52 },
    { sheetName: "AI-B原始", range: "A1:N7", scale: 0.52 },
  ],
);
const adjudicationPath = await verifyAndExport(
  adjudicationWorkbook,
  "track_a_ai_consensus_human_adjudication",
  [
    { sheetName: "使用说明", range: "A1:H21", scale: 0.9 },
    { sheetName: "裁决任务", range: "A1:J7", scale: 0.45 },
    { sheetName: "最终标签", range: "A1:P8", scale: 0.45 },
    { sheetName: "差异明细", range: "A1:H22", scale: 0.7 },
    { sheetName: "AI来源明细", range: "A1:Q7", scale: 0.4 },
    { sheetName: "标签字典", range: "A1:D44", scale: 0.8 },
  ],
);

console.log(
  JSON.stringify({ humanPath, reviewPath, adjudicationPath }, null, 2),
);
