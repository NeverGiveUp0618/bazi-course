# 八字精讲 · bazi-course

实用八字的系统教材、笔记与命例题库。五术堂导航第 6 个入口。

线上：https://nevergiveup0618.github.io/bazi-course/

## ⭐ 最重要的一条：内容源在 Obsidian，不在这里

和其他几个 App **反过来**——那些是 `data.js` 为唯一内容源，这个项目里
`data/*.js` **全是产物**，改了会在下次构建时被覆盖。

```
Obsidian（唯一内容源）                     本仓库
~/…/MyNotes/学习/
  实用八字教材/01-16*.md      ──┐
  实用八字教材/99-命例题库.md   ├─ build.py ─→  data/data-course.js
  八字01-14*.md               │                data/data-notes.js
  00-问题清单.md              ─┘                data/data-quiz.js
                                                data/data-meta.js
```

这么设计是因为这套内容还在持续改。若分叉成两份，早晚对不上——
bazi-game 和 liuren-game 都踩过「知识说明与 JS 数据结构不一致」的坑。

## 改内容的流程

1. 在 Obsidian 里正常写 markdown
2. `python3 build.py`
3. 看输出的自检结果（数量对不上会直接报错退出）
4. `node smoke.js` 跑一遍功能
5. commit + push，GitHub Pages 自动更新

```bash
python3 build.py && node smoke.js
```

零依赖：`build.py` 只用标准库，markdown 转换器是自带的 `mdlite.py`。
（系统 Python 是 externally-managed，装 python-markdown 要么破坏系统环境
要么建 venv，两者都会让脚本换台机器就跑不起来。）

`smoke.js` 需要 jsdom：`npm i --no-save jsdom`

## 构建自检

`build.py` 会在数量对不上时**报错退出**，避免站里默默少内容：

- 教材 16 章 / 笔记 14 篇 / 题库 92 题
- 有完整四柱的题 75 道
- 有 🔍 拆解的题 86 道
- 反推题恰为 `[19, 20, 53, 67, 77, 90]`
- 不存在「既无解、又没标反推」的题

## 三个模式

| | 内容 | 交互 |
|---|---|---|
| **学** | 教材 16 章 | 线性阅读、目录跳转、滚动记进度、上下章 |
| **查** | 笔记 14 篇 + 问题清单四张索引表 | `[[wiki链接]]` 站内互跳、全文搜索 |
| **练** | 命例 92 道 | 三层递进展开 + 吸顶四柱盘 + 上下题 + 考点筛选 |

### 吸顶四柱盘

讲解与拆解里满是「卯戌合」「日支巳」这种指代盘上具体字的话，盘一滚出视野
就得来回翻。所以滚过题头后，盘会缩成一条钉在顶栏下方（约 60px），**日柱高亮**。

双命对照题（题21/35 等 9 道）两个盘并排、各带命A/命B 标签——那 9 道恰恰是
最需要对照的，比如题21 的全部关窍就在「卯在日支还是在月令」这一个字的位置差。

数据来自 `charts` 字段（全部盘，含标签）；`chart` 仍只给单盘题做题头大盘。

### 练习的三层递进

刻意做成逐层展开，保住题库「遮解自推」的价值：

```
题面（四柱＋断语＋反馈）
   ↓ 点「对答案」
原文的解（引文带页码）
   ↓ 点「还是不懂 · 看拆解」
🔍 拆解（我补的推理，开头明写"非原文，可推翻"）
```

**反推题**（原书没给解那 6 道）按钮显示「看提示方向」，展开后首行明确
标注「原书未给解」——不给假答案。

⭐ **刻意不做 SRS／错题本／自评打分**（2026-08-08 按要求简化）。命例是主观题，
本来也无法客观判分；只留一个「看过」标记，让列表能看出做到哪了，不制造复习压力。

## localStorage 键

⚠️ **这些键会被五术堂导航首页的学习看板读取，改名要同步改看板。**

| 键 | 结构 |
|---|---|
| `bazi_course_read` | `{章id: 阅读百分比 0-100}`，≥90 视为已读 |
| `bazi_course_seen` | `{题号: 时间戳}` —— 看过答案的题 |
| `bazi_course_last` | `{scr, id}` 供「继续上次」 |
| `bazi_course_theme` | `null`(跟随系统) / `'light'` / `'dark'` |

## 套壳适配（三个坑，别拆）

1. **history 路由包装** —— 套壳 `view.html` 的 iframe 与顶层共享同一条
   session history。若本站不碰 history，做题深处一次侧滑会直接退出整个
   App 退回导航首页。`show()` 前进时 pushState，回到栈上已有的屏用
   `history.go(-n)` 折叠，`popstate` 只移动指针**绝不截断栈**（截断会让
   forward 找不到原来那屏，这个 bug 已被 smoke 测试锁住）。
2. **`wst-frame-guard`** —— 在 iframe 内给 `<html>` 加此 class，隐藏自带
   返回入口，交给套壳顶栏。
3. **sw.js 网络优先** —— 微信 X5 内核缓存极顽固，会无视 URL 的 `?query`
   按路径缓存。其余几个 App 都因此改成网络优先。

## 文件

```
index.html      页面骨架
style.css       竹纸靛青主题（含深色模式）
app.js          路由 / 渲染 / SRS / 搜索
build.py        markdown → data/*.js  ⭐入口
mdlite.py       零依赖 markdown 转换器
smoke.js        jsdom 冒烟测试（34 项）
data/*.js       产物，勿手改
sw.js           Service Worker（网络优先）
manifest.json   PWA
icon180/192/512.png
```
