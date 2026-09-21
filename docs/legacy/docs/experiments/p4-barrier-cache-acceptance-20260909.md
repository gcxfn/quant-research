# P4 流式障碍缓存来源绑定运行前审核

日期：2026-09-09

审核来源：主对话最终审核。Sol 负责实现与测试；本记录不是 Sol 自签独立 PASS，也不是最终研究工件 PASS。

主对话针对前次唯一阻断项审核了 `experiments/p4_stream_barrier.py` 的来源绑定：流式 manifest 保存规范化 `round_dir`、完整因子分区 manifest 与完整 B1 结果；`run` 在全缓存路径也先核对当前来源，worker 处理新列时再次核对，合并时逐列核对保存的同一绑定；生成前后来源不一致时不写 manifest。

审核时现场运行原 6 项 `tests.test_p4_stream_barrier` 均通过，并审读上述 run、worker、merge 与 generation 路径，结论为前次来源混用阻断已关闭。Sol 随后补充第 7 项生成期间来源变化反例；本地 7/7 通过。反例覆盖：`source_state` 变化、B1 内容变化、已完成列自身绑定变化、相同配置改传其他 `round_dir` 均拒绝，未改变输入可正常续跑，生成前后变化拒绝且不写 manifest。

实现验证不改变 12 候选、4 止损、费用、方向、48 检验或选择窗。Gate D 继续冻结。主对话授权使用已验收来源 `revised-r1-20260908`、2 workers 和全新输出目录 `revised-r1-stream-20260909` 执行选择窗全池；最终工件仍须主对话审核。
