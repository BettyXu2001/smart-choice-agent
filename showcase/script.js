const runButton = document.querySelector("#runDemo");
const pauseButton = document.querySelector("#pauseDemo");
const resetButton = document.querySelector("#resetDemo");
const queryInput = document.querySelector("#queryInput");
const chatQuery = document.querySelector("#chatQuery");
const aiQuestion = document.querySelector("#aiQuestion p");
const stageTitle = document.querySelector("#stageTitle");
const runState = document.querySelector("#runState");
const progressFill = document.querySelector("#progressFill");
const extractedPills = document.querySelector("#extractedPills");
const mustConfirm = document.querySelector("#mustConfirm");
const canInfer = document.querySelector("#canInfer");
const defaults = document.querySelector("#defaults");
const toolList = document.querySelector("#toolList");
const candidateList = document.querySelector("#candidateList");
const conflictList = document.querySelector("#conflictList");
const resultPanel = document.querySelector("#resultPanel");
const timeline = document.querySelector("#timeline");
const planTitle = document.querySelector("#planTitle");
const planBudget = document.querySelector("#planBudget");
const planReason = document.querySelector("#planReason");
const keptDropped = document.querySelector("#keptDropped");
const savedState = document.querySelector("#savedState");
const switchPlan = document.querySelector("#switchPlan");
const savePlan = document.querySelector("#savePlan");
const caseButtons = Array.from(document.querySelectorAll(".chip[data-case]"));

const cases = {
  offer: {
    label: "Offer 选择",
    query: "我在纠结 A 公司和 B 公司，A 做 AI 产品更匹配，B 更稳定但通勤要两小时，想看长期发展",
    aiIntro: "这是 Offer 选择 case。系统会先确认通勤是否为硬约束，再比较岗位匹配、成长空间、稳定性和薪酬回报。",
    extracted: ["领域：职业选择", "候选：A 公司 / B 公司", "目标：长期发展", "风险：通勤两小时", "偏好：AI 产品方向", "约束：稳定性不能太差"],
    must: ["通勤两小时是否不可接受", "薪酬是否有最低线", "长期发展更看重方向还是平台稳定"],
    infer: ["AI 产品方向是强偏好", "不希望为了成长承担过高生活成本", "需要解释为什么不是简单选稳定"],
    defaults: ["默认以 2-3 年成长为判断周期", "默认把通勤作为高权重风险", "默认先不使用真实公司外部信息"],
    tools: [
      ["资料注入", "读取长期偏好，但作为未确认假设而非硬条件", "完成"],
      ["候选比较", "把两个 Offer 映射到同一组评分维度", "完成"],
      ["硬约束过滤", "如果通勤被确认不可接受，B 公司会被排除", "待确认"],
      ["What-if", "模拟稳定性权重提高后的结论变化", "可用"]
    ],
    candidates: [
      { name: "A 公司", score: 87, tag: "当前首推", detail: "AI 产品方向匹配度高，成长空间更强。", trade: "业务阶段较早，稳定性弱于 B。" },
      { name: "B 公司", score: 74, tag: "条件备选", detail: "平台成熟、回报稳定。", trade: "通勤两小时和岗位方向偏传统会消耗长期投入。" }
    ],
    conflicts: [
      ["方向匹配 vs 稳定性", "A 更贴近 AI 产品目标，B 的组织和收入确定性更强。", "先按长期方向优先，要求用户确认风险承受度。"],
      ["成长空间 vs 通勤成本", "B 即使稳定，也可能因通勤降低可持续性。", "把通勤从普通偏好上升为潜在硬约束。"],
      ["当前收益 vs 未来路径", "薪酬差异如果很大，结论可能改变。", "追问最低薪酬线并保留 What-if。"]
    ],
    plan: {
      title: "当前建议优先 A 公司",
      budget: "置信：中高",
      reason: "推荐 A 公司，因为用户最强目标是长期发展且明确偏好 AI 产品方向。B 公司稳定性更好，但通勤两小时会持续消耗时间和精力；除非用户把稳定性或薪酬设为压倒性条件，否则 A 更符合主目标。",
      timeline: [["现在", "确认薪酬最低线和通勤是否为硬约束。"], ["比较", "保留 A 的方向匹配和成长优势，同时记录业务阶段风险。"], ["备选", "如果用户把稳定性权重提高，切换到 B 公司并提示通勤代价。"], ["执行", "保存当前判断，后续补充真实薪酬、团队和上级信息后重排。"]],
      summary: [["保留", "AI 产品方向、成长空间、长期路径一致性。"], ["放弃", "更高组织确定性和更稳定平台资源。"], ["风险", "A 的业务稳定性需要继续核实。"]]
    },
    alternative: {
      title: "备选：稳定性优先时选择 B 公司",
      budget: "置信：中",
      reason: "如果用户明确把稳定性和现金回报放在第一位，B 公司会成为更稳选择。但必须承认通勤两小时是长期体验风险，需要用远程办公、搬家或弹性制度来抵消。"
    }
  },
  travel: {
    label: "周末旅行",
    query: "周末从上海出发两天一夜，想放松一下，不想太累，预算别太高",
    aiIntro: "这是旅行选择 case。系统会围绕交通时长、路线强度、预算、人流和天气风险比较候选。",
    extracted: ["领域：旅行决策", "出发地：上海", "时长：两天一夜", "节奏：轻松", "预算：中低", "目的：放松"],
    must: ["具体周末日期", "是否接受高铁后转车", "下雨是否仍保留户外路线"],
    infer: ["优先 1.5-3 小时交通圈", "每天 2 个核心点位以内", "住宿和餐饮价格稳定优先"],
    defaults: ["默认公共交通", "默认舒适型住宿", "默认不安排高强度打卡"],
    tools: [
      ["领域 fixture", "生成上海周边候选", "完成"],
      ["搜索能力", "配置后可查交通、天气、票务和酒店", "可选"],
      ["证据目录", "区分演示数据和实时来源", "完成"],
      ["排序引擎", "按硬约束过滤后计算维度得分", "完成"]
    ],
    candidates: [
      { name: "绍兴", score: 84, tag: "当前首推", detail: "交通近、预算稳定、城市慢逛压力低。", trade: "自然景观不如山野目的地。" },
      { name: "莫干山", score: 80, tag: "备选", detail: "自然放松感强，适合慢节奏。", trade: "热门民宿区周末价格可能上浮。" },
      { name: "苏州", score: 73, tag: "不优先", detail: "距离最近、安排稳定。", trade: "核心区域周末人流压力高。" }
    ],
    conflicts: [
      ["放松感 vs 预算", "莫干山更放松，但住宿成本波动更大。", "首版优先选择预算更稳的绍兴。"],
      ["交通便利 vs 人少", "苏州最近，但周末热门点拥挤。", "降低距离权重，提高体验舒适度。"],
      ["自然景观 vs 可执行性", "山野目的地更依赖天气和转车。", "保留雨天切换策略。"]
    ],
    plan: {
      title: "当前建议：绍兴两天一夜轻松版",
      budget: "人均约 700-1100",
      reason: "推荐绍兴，因为用户最强约束是轻松和预算可控。绍兴交通近、住宿餐饮稳定，城市慢逛路线可以随时缩短；代价是自然风景不如莫干山。",
      timeline: [["Day 1 上午", "上海高铁到绍兴，入住鲁迅故里或仓桥直街周边。"], ["Day 1 下午", "鲁迅故里和仓桥直街慢逛，中途安排茶歇。"], ["Day 1 晚上", "本地菜晚餐，避免跨城区移动。"], ["Day 2 上午", "东湖或书圣故里二选一。"], ["Day 2 下午", "提前返程，避免晚高峰和体力透支。"]],
      summary: [["保留", "交通近、预算稳定、低强度。"], ["放弃", "强自然景观和网红度。"], ["备选", "如果更想山野放空，切换莫干山。"]]
    },
    alternative: {
      title: "备选：莫干山放空版",
      budget: "人均约 1000-1600",
      reason: "如果用户愿意接受更高预算和天气不确定性，莫干山更符合自然放松感，但需要控制住宿区域和转车成本。"
    }
  },
  shopping: {
    label: "轻便电脑",
    query: "想买一台适合通勤带着写文档和轻量开发的电脑，预算别太夸张，续航要稳",
    aiIntro: "这是购物选择 case。系统会把需求拆成重量、续航、性能、预算和售后风险，并避免只按热门榜单推荐。",
    extracted: ["领域：消费选择", "用途：文档 + 轻量开发", "场景：通勤携带", "偏好：续航稳定", "预算：不要太高", "风险：性能不足"],
    must: ["预算上限是多少", "是否需要本地跑大型模型", "屏幕尺寸可接受范围"],
    infer: ["重量和续航是高权重", "性能需要够用但不是游戏本级别", "售后和稳定性比极致参数更重要"],
    defaults: ["默认 13-14 英寸", "默认 1.4kg 以下优先", "默认不选择重型性能本"],
    tools: [
      ["候选准备", "从用户目标生成轻薄本、全能本和性价比本候选", "完成"],
      ["实时搜索", "配置后可拉取价格和规格", "可选"],
      ["硬筛选", "过滤明显超重或预算超标选项", "完成"],
      ["Evidence", "把价格、重量、续航 claim 关联来源", "模拟"]
    ],
    candidates: [
      { name: "轻薄本 A", score: 88, tag: "当前首推", detail: "重量轻、续航稳，适合高频通勤。", trade: "重度开发性能余量有限。" },
      { name: "全能本 B", score: 79, tag: "备选", detail: "性能更强，适合本地开发。", trade: "重量、价格和续航压力更大。" },
      { name: "性价比本 C", score: 72, tag: "预算优先", detail: "价格低，基础办公足够。", trade: "便携、屏幕和续航体验一般。" }
    ],
    conflicts: [
      ["便携 vs 性能", "全能本性能更强，但通勤负担更高。", "当前目标以每天携带为主，便携优先。"],
      ["预算 vs 长期体验", "最低价候选可能牺牲屏幕和续航。", "不把价格最低等同于最适合。"],
      ["续航 claim vs 真实使用", "厂商标称不等于实际轻量开发续航。", "需要真实评测或用户反馈来源。"]
    ],
    plan: {
      title: "当前建议：轻薄本 A",
      budget: "预算：中等",
      reason: "推荐轻薄本 A，因为通勤携带和稳定续航是最强条件。全能本 B 的性能更强，但重量和续航会影响日常使用；性价比本 C 价格低，但长期体验不够稳。",
      timeline: [["确认", "补充预算上限、屏幕尺寸和是否本地重开发。"], ["筛选", "排除超重、续航弱或售后风险高的型号。"], ["比较", "保留轻薄本 A 与全能本 B 做最终对照。"], ["执行", "用实时价格和评测来源更新 Evidence 后保存选择。"]],
      summary: [["保留", "便携、续航、日常稳定性。"], ["放弃", "更强性能和最低价格。"], ["风险", "真实价格和续航需要外部来源确认。"]]
    },
    alternative: {
      title: "备选：全能本 B",
      budget: "预算：偏高",
      reason: "如果用户明确需要本地开发性能，全能本 B 更合适；但要接受重量、价格和续航的代价。"
    }
  }
};

const demoSteps = [
  { title: "理解目标", state: "抽取用户条件", progress: 18, render: renderUnderstanding },
  { title: "准备候选", state: "调用能力与证据目录", progress: 42, render: renderTools },
  { title: "比较候选", state: "执行硬筛选与排序", progress: 66, render: renderCandidates },
  { title: "解释取舍", state: "生成冲突说明", progress: 82, render: renderConflicts },
  { title: "输出首版决策", state: "可保存、可调整", progress: 100, render: finishPlan }
];

let activeCaseKey = "offer";
let currentStep = 0;
let isRunning = false;
let isPaused = false;
let timers = [];

function data() {
  return cases[activeCaseKey];
}

function clearTimers() {
  timers.forEach((timer) => window.clearTimeout(timer));
  timers = [];
}

function scheduleNextStep() {
  if (!isRunning || isPaused || currentStep >= demoSteps.length) return;
  const step = demoSteps[currentStep];
  const timer = window.setTimeout(() => {
    setStage(step.title, step.state, step.progress);
    step.render();
    currentStep += 1;
    scheduleNextStep();
  }, currentStep === 0 ? 260 : 850);
  timers.push(timer);
}

function setStage(title, state, progress) {
  stageTitle.textContent = title;
  runState.textContent = state;
  progressFill.style.width = `${progress}%`;
}

function listItems(target, items) {
  target.innerHTML = items.map((item) => `<li>${item}</li>`).join("");
}

function renderPills(items) {
  extractedPills.innerHTML = items.map((item) => `<span>${item}</span>`).join("");
}

function renderUnderstanding() {
  const current = data();
  aiQuestion.textContent = current.aiIntro;
  renderPills(current.extracted);
  listItems(mustConfirm, current.must);
  listItems(canInfer, current.infer);
  listItems(defaults, current.defaults);
}

function renderTools() {
  toolList.innerHTML = data().tools.map(([name, detail, status]) => `
    <div class="tool-item"><strong>${name}</strong><span>${detail}</span><b>${status}</b></div>
  `).join("");
}

function renderCandidates() {
  candidateList.innerHTML = data().candidates.map((candidate, index) => {
    const selected = index === 0 ? " selected" : "";
    return `
      <button class="candidate-item${selected}" type="button" data-index="${index}">
        <span>${candidate.tag}</span>
        <div><strong>${candidate.name}</strong><p>${candidate.detail}</p><small>${candidate.trade}</small></div>
        <b>${candidate.score}</b>
      </button>
    `;
  }).join("");
}

function renderConflicts() {
  conflictList.innerHTML = data().conflicts.map(([title, conflict, handling]) => `
    <article><span>${title}</span><p>${conflict}</p><strong>${handling}</strong></article>
  `).join("");
}

function renderPlan(plan) {
  planTitle.textContent = plan.title;
  planBudget.textContent = plan.budget;
  planReason.textContent = plan.reason;
  timeline.innerHTML = (plan.timeline || []).map(([time, text]) => `<div><time>${time}</time><p>${text}</p></div>`).join("");
  keptDropped.innerHTML = data().plan.summary.map(([label, text]) => `<li><strong>${label}</strong><span>${text}</span></li>`).join("");
}

function finishPlan() {
  renderPlan(data().plan);
  resultPanel.classList.remove("hidden");
  runButton.disabled = false;
  pauseButton.disabled = true;
  isRunning = false;
  isPaused = false;
  pauseButton.textContent = "暂停";
}

function clearOutput() {
  renderPills([]);
  [mustConfirm, canInfer, defaults, toolList, candidateList, conflictList, timeline, keptDropped].forEach((target) => {
    target.innerHTML = "";
  });
  resultPanel.classList.add("hidden");
  savedState.textContent = "";
}

function applyCase(key) {
  if (!cases[key]) return;
  activeCaseKey = key;
  const current = data();
  queryInput.value = current.query;
  chatQuery.textContent = current.query;
  aiQuestion.textContent = "已选择典型案例。点击生成决策，查看系统如何从模糊约束走到可采用方案。";
  caseButtons.forEach((button) => button.classList.toggle("active", button.dataset.case === key));
  resetDemo();
}

function resetDemo() {
  clearTimers();
  currentStep = 0;
  isRunning = false;
  isPaused = false;
  clearOutput();
  setStage("等待生成", "未开始", 0);
  runButton.disabled = false;
  pauseButton.disabled = true;
  pauseButton.textContent = "暂停";
}

function runDemo() {
  if (isRunning) return;
  resetDemo();
  isRunning = true;
  runButton.disabled = true;
  pauseButton.disabled = false;
  setStage("启动决策", "读取输入", 6);
  scheduleNextStep();
}

function togglePause() {
  if (!isRunning) return;
  isPaused = !isPaused;
  pauseButton.textContent = isPaused ? "继续" : "暂停";
  runState.textContent = isPaused ? "已暂停" : "继续生成";
  if (!isPaused) scheduleNextStep();
}

caseButtons.forEach((button) => {
  button.addEventListener("click", () => applyCase(button.dataset.case));
});

candidateList.addEventListener("click", (event) => {
  const candidate = event.target.closest(".candidate-item");
  if (!candidate) return;
  document.querySelectorAll(".candidate-item").forEach((item) => item.classList.remove("selected"));
  candidate.classList.add("selected");
});

savePlan.addEventListener("click", () => {
  savedState.textContent = "已保存：这条决策可进入历史记录，后续补充条件时按同一状态继续。";
});

switchPlan.addEventListener("click", () => {
  const alt = data().alternative;
  renderPlan({ ...data().plan, title: alt.title, budget: alt.budget, reason: alt.reason });
  savedState.textContent = "已切换：保留当前用户约束，只替换推荐候选和取舍说明。";
});

runButton.addEventListener("click", runDemo);
pauseButton.addEventListener("click", togglePause);
resetButton.addEventListener("click", resetDemo);

applyCase("offer");
