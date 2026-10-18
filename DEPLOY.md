# 上线与自动刷新（DEPLOY）

这一页只讲**机制**：成品页怎么上线、上线后怎么保持最新、为什么不会自己循环触发。
它由 `python tools\deploy_audit.py` 离线核对（纯标准库、不联网），所以下面每一条都是断言，不是说法。

## 一、三种触发方式

| 触发 | 什么时候 | 做什么 |
| --- | --- | --- |
| `push` 到 `main` | 你推送后约 1 分钟 | **立刻**重新部署一次，不用等第二天 |
| `schedule` | 每天 22:10 UTC = **次日 06:10 马来西亚时间**（UTC+8） | 抓最新数据 → 重算 → 重建页面 → 提交回仓库 → 重新部署 |
| `workflow_dispatch` | 你在仓库 Actions 页点 **Run workflow** | 手动补跑一次（同上） |

时间换算写在 `.github/workflows/daily_refresh.yml` 的注释里；`tools/deploy_audit.py` 会把 cron `10 22 * * *`
换算回 `06:10`，再与成品页和各材料里「每天 06:10（马来西亚时间）」的声明对账。

## 二、为什么必须有 push 触发

本仓库的 Pages 源是 **GitHub Actions**（不是分支目录）：**推分支本身不会上线，只有这个工作流部署才会上线**。
2026-10-18 之前的版本只有 `schedule`，于是「推完想看新版」最长要等满 24 小时（下一次 06:10）——
如果推送发生在 10-19 06:10 之后，新版要等到 10-20 06:10，**已过提交截止 2026-10-19 24:00（CST）**。
现在 push 一进 `main` 就立刻部署，这条时间风险被消掉了。

## 三、为什么不会自己循环触发

工作流在刷新后会自己提交并 `git push`。如果这次 push 又能触发工作流，就会无限循环。两层保险：

1. **GitHub 的既有行为**：由仓库自带的 `GITHUB_TOKEN` 触发的 `push` 事件不会再触发新的工作流运行
   （官方文档「Automatic token authentication」）。本仓库不需要也不使用任何 PAT，工作流里没有 `secrets.`。
2. **deploy 作业的 actor 判断**：`github.event_name != 'push' || github.actor != 'github-actions[bot]'`。
   即便第 1 条哪天不成立，机器人自己推的那次也只会跳过部署，不会滚起来。

## 四、为什么部署不依赖刷新是否成功

`deploy` 作业的条件是 `always() && needs.refresh.result != 'cancelled' && …`：

- 刷新成功 → 新页面已提交回 `main`，部署的就是它（checkout 钉了 `ref: main`，取的是刷新后的最新提交）；
- 刷新失败（上游接口抽风、数据格式变化）→ **不会有任何提交**（提交是刷新的下一个步骤，刷新非零就跳过），
  `main` 上仍然是推送时那一版，deploy 照常把这一版上线。

也就是说：**上游出错最多让数据旧一天，不会让页面消失**。工作流运行会标红（提示你去看），但站点是好的。

## 五、怎么推、怎么确认

```bash
cd 珊瑚哨兵/ai4climate
git fetch origin
git push --force-with-lease origin editorial-layer:main
```

**为什么不能只写 `git push origin editorial-layer:main`。** `main` 不是静止的：工作流自己每天 06:10 往 `main`
提交一次 `daily refresh YYYY-MM-DD`（第二节、第三节讲的就是这条链）。本地分支 `editorial-layer` 是在某次
`origin/main` 之上做出来的，做完之后机器人又推过，于是 `origin/main` 上多出一个**不在本分支里**的提交 ——
普通推送会被直接拒掉（本机实测原文）：

```
 ! [rejected]        editorial-layer -> main (non-fast-forward)
error: failed to push some refs to 'https://github.com/sloilmarve/reef-sentinel'
hint: Updates were rejected because a pushed branch tip is behind its remote
hint: counterpart. If you want to integrate the remote changes, use 'git pull'
```

`--force-with-lease` 在这里是**正确的**，而不是「危险的强推」：

- 被覆盖的只是**一个自动化数据刷新提交**（`git log --oneline origin/main -1` → `daily refresh 2026-10-17`），
  它改的是 `demo/index.html` 与 `data/`；下一次定时运行会在约 2 分钟内把这天的数据重新抓回来，
  而且那时它是在**新页面**的生成器上重算的（本分支带着新的 `pipeline/`）。
- 它**不是** `--force`：如果远端 `main` 在你 `git fetch` 之后又被别人推过，`--force-with-lease` 会拒绝执行并提示
  `stale info` —— 那时重新 `git fetch origin` 再跑一次这条命令即可，不会静默覆盖别人的提交。
- **不要用 rebase 消掉分歧**：这 43 个提交里每一个都改过 `demo/index.html`，把整条分支 rebase 到那个机器人提交上
  会逐个提交撞同一处冲突（本机实测：普通推送被拒，`--force-with-lease` 一次通过，
  `+ c0dcb2b...2d48e66 editorial-layer -> main (forced update)`）。分歧只有 1 个提交，覆盖它是最短路径。
- 本分支只多不少地包含**新版页面与新版工作流**；推送后 `push` 触发立刻部署（第二节），所以线上几分钟内就是新版。

确认三件事：

1. `git ls-remote origin main` 的 sha 与你本地 `git rev-parse HEAD` 一致（推送到位）；
2. 仓库 Actions 页出现一次 `daily-refresh` 运行，`deploy` 作业变绿（部署成功）；
3. 打开 <https://sloilmarve.github.io/reef-sentinel/>，页面顶部「更新 YYYY-MM-DD」变成推送那一版的数据快照日期。

如果 `deploy` 作业红了，就在 Actions 页点 **Run workflow** 手动补一次（`workflow_dispatch`）。
命令与理由由 `python tools\push_audit.py` 离线核对（它同时把「文档说的」与「本机 git 引用里的真实分歧」对账）。

## 六、云端跑的到底是什么

`python pipeline/refresh.py`：25 步 —— 抓数 → 重算特征与阈值 → 重训岭回归 → 复现型审计
（因果性 / λ 敏感性 / 区间标定 / 消融 / 驱动误差 / 指数定义 / 复合标签 / S2 回溯）→ 重建唯一成品页 →
**最后一步 `pipeline/verify_demo.py` 全量核验成品页**。
所以云端每次刷新都自带一次全量自检；核验不过就不会提交，也就不会部署。

云端解释器**钉在 Python 3.10**：Python 3.12 起内置 `sum()` 改用 Neumaier 补偿求和，同一份数据末位会变
（成品页 λ=6400 的四时效平均 AUC 0.659 会变成 0.658）。钉版本是为了让云端与本地逐位同解。

## 七、本机等价演练（评审视角）

- `python tools\preflight.py`：6 步离线自检（含把提交包解到临时目录、逐字节比对复算出的页面）；
- `python tools\reviewer_repro.py`：只从提交包出发重跑并逐字节比对，打印「逐字节一致」。

## 八、已知的正常现象

- **线上页比材料新**：材料（docs/01–06、演示视频）冻结在**数据快照 2026-10-16**，线上页每天 06:10 自动前推一天。
  这是设计使然（页面是活的作品，不是截图），材料里已写明（`docs/04` 的录制说明、`00_提交包说明.md`）。
- **线上刷新后本机的 sha 前缀会过期**：`README.md` 与 `README.en.md` 里的页面 sha 前缀是本机冻结快照的；
  云端日更后线上页字节会变，而提交材料保持冻结不动。
- **`tools/consistency_audit.py` 会因数据推进而报差异**：它拿本机 `data/processed` 现算并与材料里的冻结数字对账，
  数据一推进就会提示差异 —— 这是预期的，不要为了让它变绿去改材料里的冻结数字。
- **分享卡片 `demo/og.jpg` 不随每日刷新变**：它是随包提交的静态图，卡片文案里刻意不含日期，
  所以线上页每天前推一天时，那条链接的预览仍是同一张卡片、同一段文案 —— 不会出现「页面是今天的、卡片写着快照日」的自相矛盾。
  云端刷新只改 `demo/index.html` 与 `data/`，不碰 `demo/og.jpg`；页面自身也不加载它（单文件规则不变），
  只有分享标签引用它：`https://sloilmarve.github.io/reef-sentinel/og.jpg`。核对方式是 `python tools\social_audit.py`。
