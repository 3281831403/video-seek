# video-seek

## 题面

播放器加上进度条拖动后，跳转开始花屏和偏移：关键帧查找用线性扫描，跳转耗时随片长增长；precise 策略只落到关键帧，画面对不上时间码；目标不钳制，超过 duration 后解码器报错；pts_to_frame 用浮点 fps，29.97 时帧号偏 1；往返换算不闭合，frame_to_pts(pts_to_frame(x)) 差 33 ms；区间合并只合并重叠，相接区间漏合并；解码代价按区间长度估算，忽略关键帧密度；批量跳转按输入顺序执行，倒序跳转重复解码；时间基不是最新 timescale，缩放后整体偏移；批量遇非法目标只跳过，输出里留下部分结果。playback/seek.py 是核心，tests/test_seek.py 15个红。要修的是：find_keyframe 用二分查找，seek_plan 的 precise 解码到目标、fast 落到关键帧，clamp_target 钳制到 [0, duration] 且负值抛 SeekError，pts_to_frame 与 frame_to_pts 按索引 timescale 用整数有理数换算并在 1 ms 内往返闭合，merge_ranges 同时合并重叠与相接区间，estimate_decode_cost 按关键帧到目标的距离估算，seek_batch 按升序执行并在任一目标非法时整体回滚。

## 运行方式

```bash
cd D:\gsb-20261119\video-seek
python -m pytest tests -q
```

初始状态应恰好输出：

```text
15 failed
```

15 条测试全部因桩函数 `raise NotImplementedError` 而失败；收集、导入和语法检查必须通过，不能出现 `error`。实现后测试应全部通过。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 音视频处理 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 测试约束

`tests/` 是验收测试，不得修改、删除或新增；修复只能落在 `playback/seek.py`。所有时间单位为毫秒（ms），断言允许 1 ms 容差。
