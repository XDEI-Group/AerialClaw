# recognize_speech -- 语音识别

## 使用时机
需要将音频指令转换为文本时使用。用于语音控制场景。

## 参数
- audio_id: str, 音频数据ID
- language: str, 语言代码, 默认 zh-CN

## 前提条件
- 电池 > 10%
- 麦克风正常工作

## 注意事项
- 当前使用 mock 数据
- 嘈杂环境识别率下降
- 支持中英文

## 输出
- text: str, 识别出的文本指令
- confidence: float, 识别置信度
- language: str, 实际识别语言
